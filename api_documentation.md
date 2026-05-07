# API & Authentication — Code Logic Breakdown
This document provides a line-by-line and logic-block explanation of the backend routes.

---

## Table of Contents
- [auth.py: Registration & Security](#authpy-registration--security)
- [auth.py: Token & SSO Logic](#authpy-token--sso-logic)
- [routes.py: Ingestion Pipeline](#routespy-ingestion-pipeline)
- [routes.py: Query Orchestration](#routespy-query-orchestration)

---

# auth.py: Registration & Security
`app/api/auth.py`

## register_user()
This function handles the creation of new researcher accounts.
```python
db_user = db.query(User).filter(User.username == user_in.username).first()
if db_user:
    raise HTTPException(status_code=400, detail="Username already registered")
```
- **Line 37-39:** First, it queries the `users` table to see if the username already exists. If it does, it "fails fast" with a 400 error to prevent duplicate accounts.

```python
tenant_id = derive_tenant_id(user_in.team_code)
```
- **Line 41:** It converts the human-readable `team_code` (like "Cardiology_Dept") into a standardized `tenant_id`. This ID is the "glue" that keeps all data isolated.

```python
new_user = User(
    username=user_in.username,
    hashed_password=get_password_hash(user_in.password),
    team_code=user_in.team_code,
    tenant_id=tenant_id
)
```
- **Line 43-48:** It creates a new `User` object. Crucially, it calls `get_password_hash` so the actual password is never saved—only a "scrambled" version (hash) is stored for security.

---

# auth.py: Token & SSO Logic

## login_for_access_token()
This is the main login gate.
```python
access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
access_token = create_access_token(
    data={"sub": user.username, "team_code": user.team_code}, 
    expires_delta=access_token_expires
)
```
- **Line 68-72:** Once the password is verified, it creates a JWT (token). The token "claims" include the username (`sub`) and `team_code`. This means every time the user makes a request, the server knows exactly who they are and what team they belong to just by looking at the token.

## google_callback()
```python
if not user:
    default_team = "google_research_group"
    user = User(...)
```
- **Line 104-112:** If a Google user is new, the code automatically creates a record for them in the `users` table. This is called "Just-in-Time" provisioning—it saves the user from having to fill out a registration form.

---

# routes.py: Ingestion Pipeline
`app/api/routes.py`

## ingest_document()
This route handles file uploads and processes them for the vector vault.
```python
async def event_generator():
    content = await file.read()
    async for event in stream_process_ingestion(content, file.filename, current_user, db):
        yield f"data: {json.dumps(event)}\n\n"
```
- **Line 41-45:** Instead of a simple `return`, it uses an `event_generator`.
- **await file.read():** It reads the uploaded file into memory.
- **async for event in...:** It iterates over the ingestion steps one by one. Every time a step completes (like "Chunking finished"), it `yield`s a message to the frontend. This is why the dashboard can show progress in real-time.

---

# routes.py: Query Orchestration

## handle_query()
This is the most complex function, managing the AI research flow.

### 1. Unique Thread Identification
```python
thread_id = query_req.thread_id or str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}
```
- **Line 94-95:** If the user is starting a new chat, we generate a fresh UUID. This `thread_id` is used by the **SQLite checkpointer** to save and load the conversation history.

### 2. Multi-Tier Caching
```python
exact_cached_res = await exact_cache_get(current_user.tenant_id, query_req.query)
if not exact_cached_res:
    cached_res = await semantic_cache_get(current_user.tenant_id, query_req.query)
```
- **Line 102-106:** This is the "optimization" block.
- **exact_cache_get:** Checks Redis for a 1:1 string match.
- **semantic_cache_get:** If Redis misses, it asks Qdrant to find a "meaning match." 
- **Purpose:** To prevent calling the expensive OpenAI API for questions that have already been answered.

### 3. Graph Event Streaming
```python
async for event in graph.astream_events(inputs, config, version="v1"):
    kind = event["event"]
    node = event.get("metadata", {}).get("langgraph_node", "")
```
- **Line 139-141:** It executes the LangGraph.
- **on_chat_model_stream:** When the AI (agent node) starts generating text, we capture every "chunk" of text and send it immediately.
- **on_chain_end (guardrail):** If the guardrail node decides the query is "Out of Scope," it stops the process and sends the rejection message.

### 4. Background Governance (The "Cleanup" Loop)
```python
background_tasks.add_task(
    finalize_query_governance,
    current_user, query_req, full_response, thread_id
)
```
- **Line 174-180:** After the user gets their answer, the API stays busy in the background. It calls `finalize_query_governance` to:
    - **Count Tokens:** Using tiktoken to see how much the query cost.
    - **Save Audit Logs:** Writing the prompt and answer to `UsageLog` and `TraceLog` in Postgres.
    - **Update Cache:** Saving the new answer in Redis and Qdrant so the *next* user gets a cache hit.

---

## Vault Management Logic

## delete_paper()
```python
client.delete(
    collection_name=QDRANT_COLLECTION,
    points_selector=rest.FilterSelector(
        filter=rest.Filter(must=[
            rest.FieldCondition(key="tenant_id", match=rest.MatchValue(value=current_user.tenant_id)),
            rest.FieldCondition(key="metadata.filename", match=rest.MatchValue(value=filename))
        ])
    )
)
```
- **Line 374-382:** This is the "Safe Delete" logic.
- It doesn't just delete the file. It specifically filters by **both** `tenant_id` and `filename`. 
- **Why?** This ensures that even if two teams upload a file with the same name (e.g., `report.pdf`), deleting one team's file will **never** delete the other team's data.

## get_document_summary()
```python
chunks = await search_vdb("summary overview key findings", ..., limit=8)
context = "\n\n".join([c["text"] for c in chunks[:6]])
```
- **Line 400-409:** It doesn't read the whole document (which could be 100 pages). Instead, it does a "targeted search" for summary-related keywords, grabs the top 8 chunks, and uses those as the context for the AI to summarize. This saves a lot of tokens while still being highly accurate.
