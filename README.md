# MedVault

**MedVault** is an enterprise-grade research platform that enables healthcare teams to securely ingest medical literature, clinical guidelines, and pathology reports — transforming static documents into a dynamic, cited knowledge base for real-time, evidence-based decision support.

Built with FastAPI, LangGraph, Qdrant, Redis, PostgreSQL, and Streamlit. Runs entirely in Docker.

---

## What it does

You upload your PDFs (research papers, clinical guidelines, lab reports). The app reads, indexes, and stores them. Then you can:

- **Chat** with the documents — ask anything, get answers with citations pointing to the exact source
- **Search guidelines and protocols** by condition or topic
- **Run a literature review** on any topic
- **Compare two documents** side by side
- **Auto-find and ingest PubMed papers** for a clinical question and immediately get an answer from them
- **See analytics** — how many tokens used, cost, faithfulness of answers

Each team gets its own isolated vault and secure, private chat history. One deployment, many organisations.

---

## Features

### Research Chat
Ask clinical questions in natural language. The AI agent searches your vault, retrieves the most relevant chunks, and writes a cited answer.

Every response includes inline citations like [1], [2] and a References section at the bottom:
```
[1] Vitamin D Deficiency in Adults — Smith et al. (2021) — vitamin_d_study.pdf
```
The agent can also search Arxiv for papers not in your vault. Conversations are automatically saved and persist across server restarts.

### Smart Research
Type a clinical question (e.g. *"How to treat rickets in children?"*). The app:
1. Searches PubMed Central for the top 3 relevant open-access papers
2. Downloads and indexes them automatically
3. Generates an answer from those papers with citations

No manual upload needed.

### Document Vault
- Upload PDFs from the sidebar (drag and drop)
- View all indexed documents in a card grid
- Click **Summary** to get a one-paragraph AI summary of any document
- Click **Analyze** to open a chat session focused on that document
- Delete documents you no longer need

### Guideline Reference
Quickly find official medical recommendations (WHO, NICE, NHS, etc.) from your uploaded documents.
- **What it shows**: The exact recommendation text and its **Grade of Evidence** (how strong the advice is).
- **Benefit**: No more manual searching through 100-page PDF guidelines.
- **Example**: *"What is the first-line treatment for pediatric hypertension according to WHO?"*

### Literature Review
Summarize the current state of research for any clinical topic in your library.
- **What it shows**: Where different papers **agree**, where they **disagree**, and what research is still missing.
- **Benefit**: Get a high-level overview of your entire library in seconds.
- **Example**: *"Summarize the consensus on using Vitamin D for rickets across my library."*

### Protocol Reference
Fast access to hospital protocols and procedural guidelines.
- **What it shows**: Clear **step-by-step instructions** with a direct link to the original source.
- **Benefit**: Ensures you are following the latest institutional standards for any procedure.
- **Example**: *"What is the step-by-step protocol for central line insertion?"*

### Compare Documents
See how any two documents in your vault differ side-by-side.
- **What it shows**: Agreements, contradictions, and key clinical differences.
- **Benefit**: Perfect for comparing a new lab report to a baseline or comparing two different studies.
- **Example**: *"Compare the patient's CBC from Jan 2024 to their latest report from May 2024."*

### Analytics
- Total documents indexed
- Total queries run
- Tokens used and estimated cost
- Average faithfulness score (how grounded answers were in the source documents)
- Query history with per-query latency and token breakdown

---

## 🔒 Governance & Security

Designed for clinical environments where data integrity and privacy are non-negotiable:

- **Multi-Tenant Isolation**: Organisation data is strictly isolated at the database level using tenant-aware Qdrant filtering and PostgreSQL scoping.
- **JWT Authentication**: Secure access via industry-standard JSON Web Tokens.
- **Audit Trail**: Every query and ingestion event is logged (TraceLog) for governance, tracking both source grounding and faithfulness.
- **Local Sovereignty**: All document processing, vector storage, and state management can be run within your private infrastructure.
- **Secure SSE**: Real-time streaming tokens are delivered over secure encrypted channels.

---

## Quick Start (Docker)

**Prerequisites:** Docker Desktop, an OpenAI API key.

```bash
# 1. Clone the repo
git clone https://github.com/your-org/medvault.git
cd medvault

# 2. Set up environment
cp .env.example .env
```

Open `.env` and fill in at minimum:
```
OPENAI_API_KEY=sk-...
JWT_SECRET_KEY=any-long-random-string
POSTGRES_PASSWORD=choose-a-password
```

```bash
# 3. Build and start everything
docker compose up -d --build
```

That's it. Wait about 30 seconds for services to start, then open:

| Service | URL |
|---|---|
| Dashboard | http://localhost:8501 |
| API docs | http://localhost:8000/docs |

### First steps
1. Open the dashboard at **http://localhost:8501**
2. Click **Register** and create an account
3. Upload a PDF using the **Quick Ingest** panel in the sidebar
4. Go to **Research Chat** and ask a question about it

---

## How to try each feature

### Upload a document
In the sidebar, drag a PDF onto the upload box and click **Index Document**. A progress bar shows extraction → chunking → embedding → indexing. Takes 10–60 seconds depending on PDF size.

### Ask a question
Go to **Research Chat**. Type your question. The response streams in with citations. Example:
> *"What are the main risk factors for vitamin B12 deficiency according to the uploaded guidelines?"*

### Smart Research (no upload needed)
Go to **Smart Research**. Type a clinical question. The app finds PubMed papers, indexes them, and answers — all in one step. Example:
> *"What is the evidence for vitamin D supplementation in rickets?"*

### Search guidelines
Go to **Guideline Reference**. Type a condition like *"hypertension"* or *"sepsis"*. Returns the most relevant guideline excerpts from your vault.

### Literature review
Go to **Literature Review**. Type a topic. The app synthesizes findings across all matching documents.

### Compare two documents
Go to **Compare Docs**. Select two documents from the dropdowns. The AI writes a structured comparison.

### Check analytics
Go to **Analytics** to see token usage, cost, and query history.

---

## Production Deploy

For deploying on a Linux server with HTTPS:

```bash
# 1. Copy and fill in production secrets
cp .env.production.example .env.production
# Edit .env.production — set DOMAIN, OPENAI_API_KEY, JWT_SECRET_KEY, POSTGRES_PASSWORD

# 2. First deploy (builds image + gets SSL certificate from Let's Encrypt)
chmod +x deploy.sh
./deploy.sh --build --ssl-init

# 3. Future updates
./deploy.sh --build
```

The production stack uses:
- **Nginx** — handles HTTPS, rate limiting, and proxies both the dashboard and API
- **Gunicorn** — runs the API with multiple workers for concurrency
- **Let's Encrypt** — free, auto-renewable SSL certificate

After deploy, the dashboard is at `https://your.domain.com` — no port numbers.

---

## Architecture

```
Browser
   │
   ▼
Nginx (HTTPS, rate limiting)
   ├── /api/* ──► FastAPI + Gunicorn (2-4 workers)
   │                    │
   │              LangGraph Agent
   │                ├── Qdrant (vector search)
   │                ├── Redis  (exact answer cache)
   │                ├── PostgreSQL (users, usage logs)
   │                └── SQLite (persistent conversation state)
   │
   └── /* ──────► Streamlit Dashboard
```

**How a query works:**
1. Question comes in → check Redis for exact match (returns instantly if cached)
2. If not cached → guardrail checks if it's a clinical question
3. Agent searches vault using hybrid search (dense vectors + BM25 keyword)
4. Cross-encoder reranks results to pick the best chunks
5. LLM generates answer with citations
6. Faithfulness check verifies answer is grounded in sources
7. Result cached in Redis and Qdrant semantic cache

---

## 🔬 Advanced Retrieval Strategy

The platform uses a sophisticated "Multi-Stage" retrieval pipeline to ensure maximum accuracy:

1. **Hybrid Search**: Concurrent search using **Dense Vectors** (for semantic meaning) and **Sparse Vectors** (BM25 for exact medical terminology).
2. **Matryoshka Embeddings**: High-performance embeddings optimized for both speed and retrieval depth.
3. **Cross-Encoder Reranking**: A second-pass reranker (`ms-marco-MiniLM`) evaluates the top candidates to ensure the most clinically relevant chunks are sent to the LLM.
4. **Agentic Recovery**: If the initial search yields poor results, the LangGraph agent automatically reformulates the query using clinical synonyms.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Powers embeddings and generation |
| `JWT_SECRET_KEY` | Yes | Signs auth tokens — keep secret |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `DOMAIN` | Prod only | Your domain name for SSL and CORS |
| `LANGCHAIN_API_KEY` | No | LangSmith tracing (recommended) |
| `GOOGLE_CLIENT_ID` | No | Google OAuth login |

Full list in `.env.example` (development) and `.env.production.example` (production).

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn/Gunicorn |
| AI Agent | LangGraph (stateful reasoning) |
| LLM | GPT-4o-mini (OpenAI) |
| Embeddings | text-embedding-3-small |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Vector DB | Qdrant (hybrid dense + sparse search) |
| Cache | Redis (exact) + Qdrant (semantic) |
| Database | PostgreSQL |
| Conversation Store | SQLite (with persistent volume) |
| PDF Extraction | Docling + Tesseract OCR fallback |
| Dashboard | Streamlit |
| Observability | LangSmith |
| Reverse Proxy | Nginx |
| Containers | Docker Compose |

---

## ⚠️ Medical Disclaimer

**MedVault is a research assistant tool intended to support clinical decision-making by surfacing relevant medical literature and guidelines. It is NOT a medical device and does not provide medical advice, diagnosis, or treatment.**

- All AI-generated responses should be verified against the cited source documents.
- Final clinical responsibility and decision-making authority remain solely with the treating clinician.
- Users must comply with their local institutional data privacy and HIPAA/GDPR guidelines when uploading patient-related data.

---

## License

[LICENSE](LICENSE)
