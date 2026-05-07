import os
from contextvars import ContextVar
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Centralized OpenAI client to avoid circular imports and state issues
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Per-request tenant isolation — set in routes.py before graph execution
current_tenant_id: ContextVar[str] = ContextVar("current_tenant_id", default="")
