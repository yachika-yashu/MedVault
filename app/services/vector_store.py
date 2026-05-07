from typing import List, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from fastembed import SparseTextEmbedding
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun, AsyncCallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain.retrievers.ensemble import EnsembleRetriever

from app.core.config import (
    QDRANT_COLLECTION, VECTOR_NAME_DENSE, VECTOR_NAME_SPARSE,
    RERANKER_MODEL, ENABLE_RERANKING, RERANK_TOP_K, RERANK_FINAL_K,
    EMBEDDING_DIMENSIONS, COHERE_API_KEY
)
from app.schemas.models import QueryFilters
from app.core.globals import openai_client
from app.core.qdrant import get_qdrant_client

# Global instances for singleton-like access
_sparse_encoder: Optional[SparseTextEmbedding] = None
_text_reranker: Optional[Any] = None

def get_qdrant() -> QdrantClient:
    return get_qdrant_client()

def get_sparse_encoder() -> SparseTextEmbedding:
    global _sparse_encoder
    if _sparse_encoder is None:
        print("QDRANT: Loading Sparse Encoder (BM25)...")
        _sparse_encoder = SparseTextEmbedding(model_name="Qdrant/bm25")
    return _sparse_encoder

def get_reranker() -> Any:
    global _text_reranker
    if COHERE_API_KEY:
        try:
            from langchain_cohere import CohereRerank
            return CohereRerank(cohere_api_key=COHERE_API_KEY, model="rerank-english-v3.0")
        except ImportError:
            pass

    if _text_reranker is None:
        print(f"RERANKER: Loading {RERANKER_MODEL}...")
        from sentence_transformers import CrossEncoder
        _text_reranker = CrossEncoder(RERANKER_MODEL)
    return _text_reranker

class QdrantCustomRetriever(BaseRetriever):
    """Custom Retriever wrapper for Qdrant to be used with EnsembleRetriever."""
    client: Any
    collection_name: str
    tenant_id: str
    vector_name: str
    filter: Any
    limit: int
    is_sparse: bool = False

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> List[Document]:
        # Sync fallback — uses a one-shot sync OpenAI client because openai_client is AsyncOpenAI
        # and cannot be called without await in a thread executor context.
        if self.is_sparse:
            s_encoder = get_sparse_encoder()
            sparse_vector = list(s_encoder.query_embed(query))[0]
            query_vector = rest.SparseVector(indices=sparse_vector.indices.tolist(), values=sparse_vector.values.tolist())
        else:
            from app.core.config import EMBEDDING_MODEL
            import openai as _openai, os as _os
            _sync = _openai.OpenAI(api_key=_os.getenv("OPENAI_API_KEY"))
            resp = _sync.embeddings.create(input=[query], model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS)
            query_vector = resp.data[0].embedding

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=self.vector_name,
            query_filter=self.filter,
            limit=self.limit,
            with_payload=True
        ).points

        docs = []
        for res in results:
            docs.append(Document(
                page_content=res.payload.get("text", ""),
                metadata={**res.payload.get("metadata", {}), "score": res.score, "id": res.id}
            ))
        return docs

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> List[Document]:
        # Async path — called by EnsembleRetriever.ainvoke(). Uses AsyncOpenAI correctly.
        if self.is_sparse:
            s_encoder = get_sparse_encoder()
            sparse_vector = list(s_encoder.query_embed(query))[0]
            query_vector = rest.SparseVector(indices=sparse_vector.indices.tolist(), values=sparse_vector.values.tolist())
        else:
            from app.core.config import EMBEDDING_MODEL
            resp = await openai_client.embeddings.create(input=[query], model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS)
            query_vector = resp.data[0].embedding

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=self.vector_name,
            query_filter=self.filter,
            limit=self.limit,
            with_payload=True
        ).points

        docs = []
        for res in results:
            docs.append(Document(
                page_content=res.payload.get("text", ""),
                metadata={**res.payload.get("metadata", {}), "score": res.score, "id": res.id}
            ))
        return docs


# Connects to Qdrant and creates the medvault collection with hybrid vectors and metadata indexes if it doesn't already exist.
async def init_db():
    """Connects to Qdrant"""
    client = get_qdrant()
    collections = client.get_collections().collections
    
    exists = any(c.name == QDRANT_COLLECTION for c in collections)

    if not exists:
        print(f"Creating Hybrid Qdrant collection: {QDRANT_COLLECTION}...")
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                VECTOR_NAME_DENSE: rest.VectorParams(size=EMBEDDING_DIMENSIONS, distance=rest.Distance.COSINE),
            },
            sparse_vectors_config={
                VECTOR_NAME_SPARSE: rest.SparseVectorParams()
            }
        )
        
        print("QDRANT: Creating Metadata Indexes...")
        client.create_payload_index(QDRANT_COLLECTION, "tenant_id", rest.PayloadSchemaType.KEYWORD)
        client.create_payload_index(QDRANT_COLLECTION, "metadata.year", rest.PayloadSchemaType.INTEGER)
        client.create_payload_index(QDRANT_COLLECTION, "metadata.authors", rest.PayloadSchemaType.KEYWORD)
        client.create_payload_index(QDRANT_COLLECTION, "metadata.journal", rest.PayloadSchemaType.KEYWORD)
        client.create_payload_index(QDRANT_COLLECTION, "chunk_type", rest.PayloadSchemaType.KEYWORD)
        client.create_payload_index(QDRANT_COLLECTION, "metadata.ingested_at", rest.PayloadSchemaType.KEYWORD)
        
        print(f"Qdrant collection '{QDRANT_COLLECTION}' initialized.")
    else:
        print(f"Qdrant collection '{QDRANT_COLLECTION}' already exists.")

async def search_vdb(
    query: str,
    tenant_id: str,
    limit: int = 5,
    filters: Optional[QueryFilters] = None
) -> List[dict]:
    """Hybrid Search (Ensemble) + Reranking."""
    
    client = get_qdrant()
    
    # Construct Filters
    filter_conditions = [rest.FieldCondition(key="tenant_id", match=rest.MatchValue(value=tenant_id))]
    if filters:
        if filters.year_min:
            filter_conditions.append(rest.FieldCondition(key="metadata.year", range=rest.Range(gte=filters.year_min)))
        if filters.year_max:
            filter_conditions.append(rest.FieldCondition(key="metadata.year", range=rest.Range(lte=filters.year_max)))
        if filters.authors:
            for author in filters.authors:
                filter_conditions.append(rest.FieldCondition(key="metadata.authors", match=rest.MatchValue(value=author)))
        if filters.journal:
            filter_conditions.append(rest.FieldCondition(key="metadata.journal", match=rest.MatchValue(value=filters.journal)))
        if filters.chunk_type and filters.chunk_type != "all":
            filter_conditions.append(rest.FieldCondition(key="chunk_type", match=rest.MatchValue(value=filters.chunk_type)))
        if filters.filename:
            filter_conditions.append(rest.FieldCondition(key="metadata.filename", match=rest.MatchValue(value=filters.filename)))

    qdrant_filter = rest.Filter(must=filter_conditions)

    # Initialize Retrievers
    dense_retriever = QdrantCustomRetriever(
        client=client, collection_name=QDRANT_COLLECTION, tenant_id=tenant_id,
        vector_name=VECTOR_NAME_DENSE, filter=qdrant_filter, limit=RERANK_TOP_K
    )
    sparse_retriever = QdrantCustomRetriever(
        client=client, collection_name=QDRANT_COLLECTION, tenant_id=tenant_id,
        vector_name=VECTOR_NAME_SPARSE, filter=qdrant_filter, limit=RERANK_TOP_K, is_sparse=True
    )

    # Ensemble: 0.6 Dense, 0.4 Sparse
    ensemble_retriever = EnsembleRetriever(
        retrievers=[dense_retriever, sparse_retriever],
        weights=[0.6, 0.4]
    )

    print(f"ENSEMBLE: Retrieving top {RERANK_TOP_K} candidates...")
    docs = await ensemble_retriever.ainvoke(query)
    
    if not docs:
        return []

    # Prepare for reranking
    initial_hits = []
    passages = []
    for d in docs:
        hit = {"text": d.page_content, **d.metadata}
        initial_hits.append(hit)
        passages.append(d.page_content)

    # Reranking
    if ENABLE_RERANKING:
        if COHERE_API_KEY:
            # Cohere Reranker
            try:
                import cohere
                co = cohere.Client(COHERE_API_KEY)
                response = co.rerank(query=query, documents=passages, top_n=RERANK_FINAL_K, model="rerank-english-v3.0")
                final_hits = []
                for r in response.results:
                    hit = initial_hits[r.index]
                    hit["precision_score"] = r.relevance_score
                    final_hits.append(hit)
                return final_hits
            except Exception as e:
                print(f"RERANKER: Cohere failed: {e}. Falling back to initial hits.")
        
        # Local Cross-Encoder Fallback (sentence_transformers CrossEncoder)
        reranker = get_reranker()
        pairs = [[query, p] for p in passages]
        rerank_scores = reranker.predict(pairs)
        for idx, score in enumerate(rerank_scores):
            initial_hits[idx]["precision_score"] = round(float(score), 4)
        initial_hits = sorted(initial_hits, key=lambda x: x.get("precision_score", 0), reverse=True)
        return initial_hits[:RERANK_FINAL_K]

    return initial_hits[:limit]

async def list_unique_papers(tenant_id: str) -> List[dict]:
    """Returns a list of unique papers in the user's vault."""
    client = get_qdrant()
    results, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=rest.Filter(must=[rest.FieldCondition(key="tenant_id", match=rest.MatchValue(value=tenant_id))]),
        limit=5000,
        with_payload=True,
        with_vectors=False
    )
    unique_papers = {}
    for point in results:
        meta = point.payload.get("metadata", {})
        filename = meta.get("filename")
        if not filename: continue
        ingested_at = meta.get("ingested_at", "Legacy")
        if filename not in unique_papers or ingested_at > unique_papers[filename]["ingested_at"]:
            unique_papers[filename] = {"filename": filename, "title": meta.get("title", "Unknown"), "ingested_at": ingested_at}
    return sorted(unique_papers.values(), key=lambda x: x["ingested_at"], reverse=True)
