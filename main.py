# =============================================================================
# MedVault — main.py
# =============================================================================
# VERSION: v1.1.2 (Collaborative Auth & Multi-Tenancy)
# =============================================================================

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.api.routes import router as api_router
from app.api.auth import router as auth_router
from app.services.vector_store import init_db
from app.core.cache import init_cache_db
from app.core.database import init_db as init_user_db
from app.core.config import (
    ASSETS_DIR,
    CHECKPOINTS_DB_URL,
    ALLOWED_ORIGINS,
    TRUSTED_HOSTS,
    ENABLE_DOCS,
    validate_security_config,
)
from app.core.graph import compile_graph
from app.core.logging import setup_logging
from app.core.redis import init_redis, close_redis
from fastapi.middleware.cors import CORSMiddleware
# Initialize Logging
setup_logging()
validate_security_config()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the Collaborative RAG system."""
    # 1. Initialize storage backends before the first request arrives.
    await init_db()   #create collection (if not exist) in vector database (qdrant) for vector embeddings of Clinical Documents
    init_cache_db()   #create collection (if not exist) in vector database (qdrant) for semantic cache
    init_user_db()    #create table (if not exist) in user database (postgres) for user management
    await init_redis()  #create connection to redis for exact cache
    
    # 2. Compile the graph once and attach a checkpoint backend. 
    # SQLite is used as the default checkpoint storage for LangGraph state/session memory.
    # It is lightweight, requires no external database setup, and is suitable for local development.
    # LangGraph also provides both sync and async SQLite implementations for compatibility.  
    async with AsyncSqliteSaver.from_conn_string(CHECKPOINTS_DB_URL) as memory: #The AsyncSqliteSaver.from_conn_string() creates an asynchronous SQLite-backed memory store that is used as the checkpointing layer for the compiled graph.
        app.state.graph = compile_graph(memory)
        app.state.checkpointer = memory
        try:
            yield #The yield statement allows the FastAPI lifespan context (this function) to keep the application running after initialization
        finally:
            await close_redis()
    
    print("Shutting down MedVault...")



app = FastAPI(
    title="MedVault",
    description="Enterprise-Grade Collaborative Clinical RAG with JWT Multi-Tenancy & Hybrid Search.",
    version="1.1.2",
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

# --- CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    # Restrict browser callers to known frontend origins instead of accepting
    # cross-origin credentials from every site on the internet.
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=TRUSTED_HOSTS or ["localhost", "127.0.0.1"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Apply baseline response headers that reduce common browser-side attacks."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    # HSTS should only be sent by deployments that are actually behind HTTPS.
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# --- MIDDLEWARE & ASSETS ---
os.makedirs(ASSETS_DIR, exist_ok=True) # ensure folder name(assets/images) mention in assts_dir created otherwise create it
static_abs_path = os.path.abspath("assets") # take absolute path of assets folder
app.mount("/assets", StaticFiles(directory=static_abs_path), name="assets") #serve files from the 'assets' directory at '/assets' URL endpoint

# --- ROUTERS ---
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Security"]) # include authentication related endpoints
app.include_router(api_router, prefix="/api/v1", tags=["Research Engine"])



# This runs the server only when you execute this file directly: `python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
