# Changelog

## [0.1.0] - 2026-05-10

### Added
- Agentic RAG pipeline with LangGraph for stateful multi-step clinical reasoning
- Multi-tenant document vault with team-based isolation at vector and database layers
- Real-time research chat with inline source citations
- Smart Research — auto-fetch, index, and answer from PubMed papers in one flow
- Hybrid search combining dense semantic vectors and sparse BM25 keyword matching
- Cross-encoder reranking (ms-marco-MiniLM) for high-precision chunk selection
- Literature review synthesis across the full document vault
- Document comparison with structured agreement/contradiction analysis
- Guideline reference with Grade of Evidence extraction
- Protocol reference with step-by-step procedure lookup
- Analytics dashboard — token usage, cost, faithfulness scores, query history
- JWT-based authentication with multi-tenant user isolation
- Redis exact-match cache and Qdrant semantic cache for repeated queries
- Faithfulness scoring to verify answers are grounded in source documents
- Audit trail (TraceLog) logging every query and ingestion event
- Real-time SSE token streaming with progress state
- Layout-aware PDF extraction via Docling with Tesseract OCR fallback
- Production deployment stack — Docker Compose, Nginx, Gunicorn, Certbot SSL
- Full end-to-end test suite covering all eight feature surfaces
- GitHub Actions CI pipeline with full Docker stack integration tests

### Tech Stack
- **Backend**: FastAPI + LangGraph
- **Search**: Qdrant (hybrid dense + sparse vectors) + Redis (cache)
- **Data**: PostgreSQL + SQLite
- **LLM**: OpenAI GPT-4o-mini + text-embedding-3-small
- **Infrastructure**: Docker Compose, Nginx, Gunicorn
- **Frontend**: Streamlit
- **Observability**: LangSmith
