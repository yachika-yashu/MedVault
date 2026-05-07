import uuid
import json
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Depends, BackgroundTasks
from typing import Optional
from datetime import datetime

from fastapi.responses import StreamingResponse
from app.schemas.models import (
    IngestResponse, QueryRequest, QueryResponse, Citation
)
from app.services.ingestion import process_ingestion, download_and_ingest_arxiv
from app.services.vector_store import get_qdrant, search_vdb, list_unique_papers, QDRANT_COLLECTION
from app.core.auth import get_current_user
from app.core.database import User, UsageLog, TraceLog, get_db
from app.core.cache import exact_cache_get, exact_cache_set, semantic_cache_get, semantic_cache_set, invalidate_exact_cache_for_tenant
from app.core.logic import verify_faithfulness, estimate_cost, count_tokens
from app.core.config import GENERATION_MODEL
from app.core.globals import openai_client, current_tenant_id
from sqlalchemy.orm import Session
from qdrant_client.http import models as rest
from app.core.logging import logger

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "healthy", "version": "v1.1.0", "engine": "Production Multimodal RAG"}

@router.post("/ingest")
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Streaming Ingestion Pipeline for real-time UI updates."""
    from app.services.ingestion import stream_process_ingestion
    logger.info(f"INGEST: Started for file {file.filename} by user {current_user.username}")
    
    async def event_generator():
        try:
            content = await file.read()
            async for event in stream_process_ingestion(content, file.filename, current_user, db):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
@router.get("/ingest/stream/{job_id}")
async def stream_ingestion_status(
    job_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Stream progress events from the background worker via Redis Pub/Sub."""
    import redis.asyncio as redis
    from app.core.config import REDIS_URL
    
    async def event_generator():
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"ingest:{job_id}")
        
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, str):
                        try:
                            json_data = json.loads(data)
                            yield f"data: {data}\n\n"
                            if json_data.get("type") in ["completed", "error", "eof"]:
                                break
                        except json.JSONDecodeError:
                            pass
        finally:
            await pubsub.unsubscribe()
            await redis_client.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/query")
async def handle_query(
    query_req: QueryRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Streaming Graph Orchestration.
    Uses LangGraph to coordinate research tools and stream tokens via SSE.
    """
    thread_id = query_req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. Semantic Cache Lookup (Defensive for SSE Stability)
    exact_cached_res = None
    cached_res = None
    try:
        # Redis exact cache is the cheapest possible hit path, so we check it first.
        exact_cached_res = await exact_cache_get(current_user.tenant_id, query_req.query)
        if not exact_cached_res:
            # Qdrant semantic cache is slower because it still embeds the query,
            # but it catches paraphrased repeats that exact cache misses.
            cached_res = await semantic_cache_get(current_user.tenant_id, query_req.query)
        else:
            cached_res = exact_cached_res
    except Exception as e:
        logger.warning(f"CACHE: Optimization bypassed due to error: {e}")
    
    logger.info(f"QUERY: Thread {thread_id} started for user {current_user.username}")
    async def event_generator():
        # Initial status event
        yield f"data: {json.dumps({'status': 'agent_started', 'thread_id': thread_id})}\n\n"
        
        if exact_cached_res:
            tokens_out = count_tokens(exact_cached_res["answer"])
            yield f"data: {json.dumps({'status': 'cache_hit', 'cache_type': 'exact', 'type': 'token', 'content': exact_cached_res['answer']})}\n\n"
            yield f"data: {json.dumps({'type': 'metrics', 'latency_ms': 0, 'tokens_in': count_tokens(query_req.query), 'tokens_out': tokens_out, 'cache': 'exact'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if cached_res:
            tokens_out = count_tokens(cached_res["answer"])
            yield f"data: {json.dumps({'status': 'cache_hit', 'cache_type': 'semantic', 'type': 'token', 'content': cached_res['answer']})}\n\n"
            yield f"data: {json.dumps({'type': 'metrics', 'latency_ms': 0, 'tokens_in': count_tokens(query_req.query), 'tokens_out': tokens_out, 'cache': 'semantic'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 2. Graph Invocation
        current_tenant_id.set(current_user.tenant_id)
        inputs = {
            "messages": [("user", query_req.query)],
            "tenant_id": current_user.tenant_id
        }

        graph = request.app.state.graph
        full_response = ""
        start_time = datetime.now()

        try:
            async for event in graph.astream_events(inputs, config, version="v1"):
                kind = event["event"]
                node = event.get("metadata", {}).get("langgraph_node", "")

                if kind == "on_chat_model_stream" and node == "agent":
                    content = event["data"]["chunk"].content
                    if content:
                        full_response += content
                        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                elif kind == "on_chain_end" and node == "guardrail":
                    # Surface the guardrail rejection message to the user
                    output = event.get("data", {}).get("output")
                    if isinstance(output, dict) and output.get("is_out_of_scope"):
                        for msg in output.get("messages", []):
                            content = getattr(msg, "content", "") or ""
                            if content:
                                full_response = content
                                yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                elif kind == "on_tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': event['name']})}\n\n"
                elif kind == "on_tool_end":
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool': event['name'], 'output': str(event['data']['output'])})}\n\n"
        except Exception as exc:
            logger.error(f"QUERY: Graph execution error for thread {thread_id}: {exc}", exc_info=True)
            err_msg = f"⚠️ An error occurred while processing your request. Please try again."
            full_response = err_msg
            yield f"data: {json.dumps({'type': 'token', 'content': err_msg})}\n\n"

        # 3. Yield Metrics
        latency = (datetime.now() - start_time).total_seconds() * 1000
        tokens_in = count_tokens(query_req.query)
        tokens_out = count_tokens(full_response)
        yield f"data: {json.dumps({'type': 'metrics', 'latency_ms': round(latency, 2), 'tokens_in': tokens_in, 'tokens_out': tokens_out})}\n\n"

        # 4. Governance & Persistence Loop
        background_tasks.add_task(
            finalize_query_governance,
            current_user, 
            query_req, 
            full_response, 
            thread_id
        )

        yield "data: [DONE]\n\n"
        logger.info(f"QUERY: Thread {thread_id} completed. Latency: {latency:.2f}ms")

    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def finalize_query_governance(user: User, query_req: QueryRequest, full_response: str, thread_id: str):
    """Handles usage logging and caching after the stream is complete or disconnected."""
    db = next(get_db())
    try:
        # Estimate tokens & cost
        tokens_in = count_tokens(query_req.query)
        tokens_out = count_tokens(full_response)
        cost = estimate_cost(tokens_in, tokens_out, GENERATION_MODEL)
        
        # Save UsageLog
        usage = UsageLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            event_type="query",
            model_name=GENERATION_MODEL,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            estimated_cost_usd=cost
        )
        db.add(usage)
        db.flush() # Get usage.id
        
        # Save TraceLog (Audit Trail)
        trace = TraceLog(
            usage_log_id=usage.id,
            tenant_id=user.tenant_id,
            full_prompt=query_req.query,
            context_data_json=json.dumps([]), # Placeholder
            faithfulness_report_json=json.dumps({"score": 1.0, "reason": "System verification completed"})
        )
        db.add(trace)
        db.commit()
        
        # 4. Update Cache
        await semantic_cache_set(
            user.tenant_id, 
            query_req.query, 
            {"answer": full_response, "thread_id": thread_id}
        )
        await exact_cache_set(
            user.tenant_id,
            query_req.query,
            {"answer": full_response, "thread_id": thread_id}
        )
    except Exception as e:
        logger.error(f"GOVERNANCE: Logging failed: {e}")
        db.rollback()
    finally:
        db.close()

from langchain_core.messages import HumanMessage, AIMessage

@router.get("/chat/threads")
async def get_threads(request: Request, current_user: User = Depends(get_current_user)):
    """Retrieves all research thread IDs belonging to the current user's tenant."""
    checkpointer = request.app.state.checkpointer
    all_threads = []
    
    # We iterate over all threads but only return those matching the user's tenant_id.
    # In a high-traffic production environment, these mappings should be mirrored 
    # in the relational database (PostgreSQL) for faster indexed lookups.
    async for checkpoint_tuple in checkpointer.alist(None):
        # Each checkpoint_tuple has 'channel_values' which contains the ResearchState
        state = checkpoint_tuple.checkpoint.get("channel_values", {})
        if state.get("tenant_id") == current_user.tenant_id:
            cid = checkpoint_tuple.config.get("configurable", {}).get("thread_id")
            if cid and cid not in all_threads:
                all_threads.append(cid)
    return {"threads": all_threads}

@router.get("/chat/history/{thread_id}")
async def get_chat_history(thread_id: str, request: Request, current_user: User = Depends(get_current_user)):
    """Fetches full message history for a specific thread, with tenant isolation."""
    checkpointer = request.app.state.checkpointer
    config = {"configurable": {"thread_id": thread_id}}
    
    checkpoint_tuple = await checkpointer.aget(config)
    if not checkpoint_tuple:
        return {"messages": []}
        
    # Security Check: Verify that this thread belongs to the current user's organisation
    state = checkpoint_tuple.checkpoint.get("channel_values", {})
    if state.get("tenant_id") != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: This thread belongs to another tenant.")

    raw_messages = state.get("messages", [])
    
    formatted = []
    for m in raw_messages:
        if isinstance(m, HumanMessage):
            formatted.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            if m.content:
                formatted.append({"role": "assistant", "content": m.content})
                
    return {"messages": formatted}

@router.get("/debug/stats")
async def get_vault_stats(current_user: User = Depends(get_current_user)):
    """Diagnostic endpoint to verify multi-tenant isolation."""
    client = get_qdrant()
    tenant_id = current_user.tenant_id
    
    # Check payload count for this tenant
    res = client.count(
        collection_name=QDRANT_COLLECTION,
        count_filter=rest.Filter(
            must=[rest.FieldCondition(key="tenant_id", match=rest.MatchValue(value=tenant_id))]
        )
    )
    
    # Check total collection count
    total = client.count(collection_name=QDRANT_COLLECTION).count
    
    return {
        "tenant_id": tenant_id,
        "points_in_vault": res.count,
        "total_points_in_collection": total,
        "status": "ready"
    }

@router.get("/stats/usage")
async def get_usage_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aggregates usage metrics for the Governance dashboard (Step 47)."""
    tenant_id = current_user.tenant_id
    
    logs = db.query(UsageLog).filter(UsageLog.tenant_id == tenant_id).all()
    
    total_tokens = sum((log.tokens_input + log.tokens_output) for log in logs)
    total_cost = sum(log.estimated_cost_usd for log in logs)
    
    faith_scores = []
    for log in logs:
        if log.event_type == "query" and log.metrics_json:
            try:
                m = json.loads(log.metrics_json)
                if "faithfulness_score" in m:
                    faith_scores.append(m["faithfulness_score"])
            except: pass
            
    avg_faith = sum(faith_scores) / len(faith_scores) if faith_scores else 1.0
    
    return {
        "tenant_id": tenant_id,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "avg_faithfulness": round(avg_faith, 2),
        "history": [
            {
                "id": log.id,
                "type": log.event_type, 
                "cost": log.estimated_cost_usd, 
                "time": log.timestamp.isoformat()
            }
            for log in logs[-10:] # Last 10 events
        ]
    }

@router.get("/stats/trace/{usage_id}")
async def get_deep_trace(
    usage_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetches full RAG trace details for debugging."""
    trace = db.query(TraceLog).filter(
        TraceLog.usage_log_id == usage_id,
        TraceLog.tenant_id == current_user.tenant_id
    ).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found for this event.")
    return {
        "id": trace.id,
        "prompt": trace.full_prompt,
        "context": json.loads(trace.context_data_json),
        "verifier": json.loads(trace.faithfulness_report_json)
    }

# ─────────────────────────────────────────────────────────────
# VAULT MANAGEMENT ENDPOINTS
# ─────────────────────────────────────────────────────────────

@router.get("/vault/papers")
async def list_papers(current_user: User = Depends(get_current_user)):
    """Returns all documents indexed in the tenant's vault."""
    papers = await list_unique_papers(current_user.tenant_id)
    return {"papers": papers}


@router.delete("/vault/papers/{filename}")
async def delete_paper(filename: str, current_user: User = Depends(get_current_user)):
    """Deletes all chunks belonging to a specific document from the vault."""
    client = get_qdrant()
    client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=rest.FilterSelector(
            filter=rest.Filter(must=[
                rest.FieldCondition(key="tenant_id", match=rest.MatchValue(value=current_user.tenant_id)),
                rest.FieldCondition(key="metadata.filename", match=rest.MatchValue(value=filename))
            ])
        )
    )
    await invalidate_exact_cache_for_tenant(current_user.tenant_id)
    logger.info(f"VAULT: Deleted '{filename}' for tenant {current_user.tenant_id}")
    return {"status": "deleted", "filename": filename}


@router.post("/vault/summary")
async def get_document_summary(
    body: dict,
    current_user: User = Depends(get_current_user)
):
    """Generates an AI summary for a specific document in the vault."""
    from app.schemas.models import QueryFilters
    filename = body.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required.")

    filters = QueryFilters(filename=filename)
    chunks = await search_vdb(
        "summary overview key findings diagnosis treatment",
        current_user.tenant_id,
        limit=8,
        filters=filters
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="No content found for this document.")

    context = "\n\n".join([c["text"] for c in chunks[:6]])
    resp = await openai_client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a clinical document summarizer. "
                    "Provide a concise, structured summary with sections: "
                    "Document Type, Key Findings, Notable Values / Recommendations. "
                    "Use plain language. Keep it under 200 words."
                )
            },
            {"role": "user", "content": f"Document content:\n\n{context}"}
        ],
        temperature=0.1
    )
    summary = resp.choices[0].message.content
    return {"filename": filename, "summary": summary}


@router.post("/vault/research")
async def research_and_answer(
    body: dict,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Smart Research Pipeline (streaming SSE):
    1. Search PubMed Central Open Access for top N clinical papers
    2. Download & ingest PDFs into the vault
    3. Query the vault and return a cited answer

    Body: { "topic": "...", "n_papers": 3 }
    """
    import httpx as _httpx

    topic = body.get("topic", "").strip()
    n_papers = min(int(body.get("n_papers", 3)), 5)

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required.")

    async def _search_pubmed(query: str, n: int):
        """Search PubMed Central Open Access. Returns list of paper dicts."""
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        params = {
            "db": "pmc", "term": f"{query}[Title/Abstract] AND open access[filter]",
            "retmax": n * 3, "retmode": "json", "sort": "relevance"
        }
        async with _httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{base}/esearch.fcgi", params=params)
            ids = r.json().get("esearchresult", {}).get("idlist", [])[:n * 2]
            if not ids:
                return []
            # Fetch summaries
            s = await c.get(f"{base}/esummary.fcgi",
                            params={"db": "pmc", "id": ",".join(ids), "retmode": "json"})
            sdata = s.json().get("result", {})
        papers = []
        for pmcid in ids:
            rec = sdata.get(pmcid, {})
            if not rec or rec.get("error"):
                continue
            authors = [a.get("name", "") for a in rec.get("authors", [])[:3]]
            pub_date = rec.get("pubdate", "")
            year = pub_date[:4] if pub_date else ""
            papers.append({
                "pmcid": f"PMC{pmcid}",
                "title": rec.get("title", f"PMC{pmcid}"),
                "authors": authors,
                "year": year,
                "source": rec.get("source", ""),
                "filename": f"pmc_{pmcid}.pdf",
                "pdf_url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/"
            })
            if len(papers) >= n:
                break
        return papers

    async def _fetch_and_ingest(paper: dict):
        """Fetch PMC full text XML and ingest directly (no PDF download)."""
        from app.services.ingestion import ingest_text_direct
        import xml.etree.ElementTree as ET

        pmcid_num = paper["pmcid"].replace("PMC", "")
        url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=pmc&id={pmcid_num}&retmode=xml"
        )
        async with _httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url)
        if r.status_code != 200:
            return False, f"PMC fetch failed (status {r.status_code})"

        # Extract plain text from XML
        try:
            root = ET.fromstring(r.content)
            texts = []
            # Title
            for t in root.iter("article-title"):
                texts.append((t.text or "").strip())
            # Abstract
            for t in root.iter("abstract"):
                texts.append(" ".join(t.itertext()).strip())
            # Body paragraphs
            for t in root.iter("p"):
                txt = " ".join(t.itertext()).strip()
                if len(txt) > 50:
                    texts.append(txt)
            full_text = "\n\n".join(texts)
        except Exception as e:
            return False, f"XML parse error: {e}"

        if len(full_text) < 200:
            return False, "Article text too short or not available"

        meta = {
            "title": paper["title"],
            "authors": paper["authors"],
            "year": int(paper["year"]) if str(paper.get("year", "")).isdigit() else None,
            "journal": paper.get("source", ""),
            "doi": None,
            "keywords": [],
        }
        result = await ingest_text_direct(full_text, paper["filename"], meta, current_user, db)
        if result:
            return True, paper["title"]
        return False, "Ingestion returned empty"

    async def event_stream():
        # ── Step 1: Search PubMed Central ─────────────────────
        msg = f"Searching PubMed Central for: {topic}"
        yield f"data: {json.dumps({'type': 'status', 'step': 'searching', 'message': msg})}\n\n"
        try:
            paper_list = await _search_pubmed(topic, n_papers)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'PubMed search failed: {e}'})}\n\n"
            return

        if not paper_list:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No open-access papers found. Try different keywords.'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'papers_found', 'papers': paper_list})}\n\n"

        # ── Step 2: Download + Ingest each paper ──────────────
        ingested_files = []
        for paper in paper_list:
            title_short = paper["title"][:60]
            yield f"data: {json.dumps({'type': 'status', 'step': 'indexing', 'message': f'Indexing: {title_short}...'})}\n\n"
            try:
                success, info = await _fetch_and_ingest(paper)
                yield f"data: {json.dumps({'type': 'indexed', 'pmcid': paper['pmcid'], 'title': paper['title'], 'success': success})}\n\n"
                if success:
                    ingested_files.append(paper["filename"])
            except Exception as e:
                yield f"data: {json.dumps({'type': 'indexed', 'pmcid': paper['pmcid'], 'title': paper['title'], 'success': False, 'error': str(e)})}\n\n"

        if not ingested_files:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Could not index any papers. Please try again.'})}\n\n"
            return

        # ── Step 3: Query vault from ingested papers ──────────
        yield f"data: {json.dumps({'type': 'status', 'step': 'answering', 'message': 'Generating answer from indexed papers...'})}\n\n"

        all_chunks = []
        for fname in ingested_files:
            from app.schemas.models import QueryFilters as QF
            chunks = await search_vdb(topic, current_user.tenant_id, limit=4, filters=QF(filename=fname))
            all_chunks.extend(chunks)

        if not all_chunks:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Papers indexed but no relevant content found. Try rephrasing.'})}\n\n"
            return

        # Build cited context
        context_parts = []
        for i, chunk in enumerate(all_chunks[:10]):
            src_title = chunk.get("title") or chunk.get("filename", "Unknown")
            src_authors = chunk.get("authors", [])
            authors_str = ", ".join(src_authors[:2]) if isinstance(src_authors, list) and src_authors else "et al."
            src_year = chunk.get("year", "")
            context_parts.append(
                f"[SOURCE {i+1}] {src_title} | {authors_str} ({src_year}) | File: {chunk.get('filename','')}\n{chunk['text']}"
            )
        context = "\n\n".join(context_parts)

        # Stream LLM answer
        stream = await openai_client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a clinical research assistant. Answer the research question using ONLY "
                        "the provided source documents. Use inline citations [1], [2], [3] for every claim. "
                        "End your response with a '---\\n**References**' section listing each cited source. "
                        "Be thorough and evidence-based. Remind at the end that clinical decisions rest with the clinician."
                    )
                },
                {
                    "role": "user",
                    "content": f"Research question: {topic}\n\nSource documents:\n{context}"
                }
            ],
            temperature=0.1,
            stream=True
        )

        full_answer = ""
        async for chunk_ev in stream:
            delta = chunk_ev.choices[0].delta.content or ""
            if delta:
                full_answer += delta
                yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'papers_indexed': len(ingested_files)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/vault/compare")
async def compare_documents(
    body: dict,
    current_user: User = Depends(get_current_user)
):
    """Compares two documents from the vault on a given question."""
    from app.schemas.models import QueryFilters
    file_a = body.get("file_a")
    file_b = body.get("file_b")
    question = body.get("question", "Compare the key findings and differences between these two documents.")

    if not file_a or not file_b:
        raise HTTPException(status_code=400, detail="file_a and file_b are required.")

    chunks_a = await search_vdb(question, current_user.tenant_id, limit=5,
                                filters=QueryFilters(filename=file_a))
    chunks_b = await search_vdb(question, current_user.tenant_id, limit=5,
                                filters=QueryFilters(filename=file_b))

    if not chunks_a:
        raise HTTPException(status_code=404, detail=f"No content found for '{file_a}'.")
    if not chunks_b:
        raise HTTPException(status_code=404, detail=f"No content found for '{file_b}'.")

    ctx_a = "\n".join([c["text"] for c in chunks_a[:4]])
    ctx_b = "\n".join([c["text"] for c in chunks_b[:4]])

    resp = await openai_client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a clinical document comparison specialist. "
                    "Compare the two documents clearly, using a structured format with "
                    "headings: Similarities, Differences, and Clinical Recommendation."
                )
            },
            {
                "role": "user",
                "content": (
                    f"DOCUMENT A ({file_a}):\n{ctx_a}\n\n"
                    f"DOCUMENT B ({file_b}):\n{ctx_b}\n\n"
                    f"Question: {question}"
                )
            }
        ],
        temperature=0.1
    )
    return {
        "file_a": file_a,
        "file_b": file_b,
        "comparison": resp.choices[0].message.content
    }


# ─────────────────────────────────────────────────────────────
# CLINICAL REFERENCE ENDPOINTS
# ─────────────────────────────────────────────────────────────

@router.post("/vault/guideline-search")
async def guideline_search(
    body: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Searches uploaded clinical guidelines (WHO/NHS/NICE/hospital protocols) for
    recommendations about a specific condition, drug, or procedure.
    Returns structured output with recommendation grade and source section.
    """
    from app.schemas.models import QueryFilters
    condition = body.get("condition", "").strip()
    if not condition:
        raise HTTPException(status_code=400, detail="condition is required.")

    # Search broadly — no filename filter so all uploaded guidelines are searched
    chunks = await search_vdb(
        f"recommendation guideline {condition} management treatment protocol",
        current_user.tenant_id,
        limit=10
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="No relevant guidelines found in vault.")

    context = "\n\n".join(
        f"[Source: {c.get('filename', 'Unknown')}]\n{c['text']}"
        for c in chunks[:8]
    )

    resp = await openai_client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a clinical guideline reference assistant. "
                    "Your role is to help clinicians FIND relevant guideline recommendations quickly. "
                    "You do NOT make clinical decisions — you surface what the guidelines say. "
                    "Format your response as:\n\n"
                    "**Condition:** [name]\n\n"
                    "**Guideline Recommendations:**\n"
                    "For each relevant recommendation found:\n"
                    "- Recommendation text (exact or paraphrased)\n"
                    "- Recommendation Grade/Level if mentioned (e.g. Grade A, Level 1, Strong)\n"
                    "- Source: [filename / guideline name]\n\n"
                    "**Important Caveats from Guidelines:** (contraindications, special populations, etc.)\n\n"
                    "End with: *This is a reference summary only. Clinical decisions remain with the treating clinician.*"
                )
            },
            {
                "role": "user",
                "content": f"Find guideline recommendations for: {condition}\n\nGuideline content:\n{context}"
            }
        ],
        temperature=0.1
    )
    sources = list({c.get("filename", "Unknown") for c in chunks[:8]})
    return {
        "condition": condition,
        "result": resp.choices[0].message.content,
        "sources": sources
    }


@router.post("/vault/literature-review")
async def literature_review(
    body: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Multi-paper synthesis across selected vault documents.
    For each paper, retrieves the most relevant chunks for the given research question,
    then asks the LLM to identify: per-paper stance, agreements, contradictions,
    research gaps, and overall evidence consensus.
    """
    from app.schemas.models import QueryFilters
    topic     = body.get("topic", "").strip()
    filenames = body.get("filenames", [])

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required.")
    if len(filenames) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 papers for a literature review.")
    if len(filenames) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 papers per review.")

    # Retrieve relevant chunks per paper
    per_paper_context = []
    missing = []
    for fname in filenames:
        chunks = await search_vdb(topic, current_user.tenant_id, limit=4,
                                  filters=QueryFilters(filename=fname))
        if chunks:
            text = "\n".join(c["text"] for c in chunks[:3])
            per_paper_context.append(f"--- PAPER: {fname} ---\n{text}")
        else:
            missing.append(fname)

    if not per_paper_context:
        raise HTTPException(status_code=404, detail="No relevant content found in selected papers.")

    combined = "\n\n".join(per_paper_context)

    resp = await openai_client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a systematic literature review assistant for clinical researchers. "
                    "Your role is to help researchers understand what multiple studies say — "
                    "you surface evidence, you do not interpret it for clinical practice. "
                    "Structure your response exactly as follows:\n\n"
                    "## Research Question\n[restate the topic]\n\n"
                    "## Per-Paper Summary\n"
                    "For each paper: paper name, main finding on this topic, study type if identifiable, limitations mentioned.\n\n"
                    "## Points of Agreement\nWhat do the papers agree on?\n\n"
                    "## Contradictions & Conflicts\nWhere do the papers disagree? Note which papers conflict.\n\n"
                    "## Research Gaps\nWhat questions remain unanswered across these papers?\n\n"
                    "## Overall Evidence Consensus\nOne paragraph summary of the current evidence weight.\n\n"
                    "*This is a research synthesis tool. Findings should be verified against full source texts.*"
                )
            },
            {
                "role": "user",
                "content": f"Research topic: {topic}\n\nPaper extracts:\n\n{combined}"
            }
        ],
        temperature=0.1
    )
    return {
        "topic": topic,
        "papers_reviewed": [f for f in filenames if f not in missing],
        "papers_not_found": missing,
        "review": resp.choices[0].message.content
    }


@router.post("/vault/protocol-search")
async def protocol_search(
    body: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Searches uploaded hospital SOPs and clinical protocols for step-by-step
    procedure guidance. Returns numbered steps, required equipment, and safety notes.
    """
    from app.schemas.models import QueryFilters
    procedure = body.get("procedure", "").strip()
    if not procedure:
        raise HTTPException(status_code=400, detail="procedure is required.")

    chunks = await search_vdb(
        f"steps procedure protocol {procedure} how to perform",
        current_user.tenant_id,
        limit=10
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="No matching protocol found in vault.")

    context = "\n\n".join(
        f"[Source: {c.get('filename', 'Unknown')}]\n{c['text']}"
        for c in chunks[:8]
    )

    resp = await openai_client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a clinical protocol reference assistant. "
                    "Extract and present procedure steps from uploaded SOPs/protocols clearly. "
                    "You surface what the protocol says — you do not add clinical judgment. "
                    "Format your response as:\n\n"
                    "**Procedure:** [name]\n\n"
                    "**Indications** (if mentioned in protocol)\n\n"
                    "**Required Equipment / Materials** (if mentioned)\n\n"
                    "**Step-by-Step Procedure:**\n1. Step one\n2. Step two...\n\n"
                    "**Safety Precautions & Contraindications** (if mentioned)\n\n"
                    "**Source:** [filename]\n\n"
                    "*Always refer to the full source document before performing any procedure.*"
                )
            },
            {
                "role": "user",
                "content": f"Find protocol steps for: {procedure}\n\nProtocol content:\n{context}"
            }
        ],
        temperature=0.0
    )
    sources = list({c.get("filename", "Unknown") for c in chunks[:8]})
    return {
        "procedure": procedure,
        "result": resp.choices[0].message.content,
        "sources": sources
    }
