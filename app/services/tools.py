from typing import Optional
from langchain_core.tools import tool
from langchain_community.utilities import ArxivAPIWrapper
from langchain_experimental.utilities import PythonREPL
from app.services.vector_store import search_vdb
from app.core.config import BASE_URL
from app.core.globals import current_tenant_id

arxiv_wrapper = ArxivAPIWrapper()
python_repl = PythonREPL()


@tool
def arxiv_search_tool(query: str) -> str:
    """
    Search Arxiv for research papers.
    Use this to find papers by title, author, or topic when the local vault doesn't have the answer.
    Returns paper summaries, titles, and IDs.
    """
    results = arxiv_wrapper.run(query)
    return f"--- ARXIV SEARCH RESULTS (external web source, NOT from the user's vault) ---\n{results}\n--- END ARXIV RESULTS ---"


@tool
def python_repl_tool(code: str) -> str:
    """
    A Python shell. Use this to execute python commands.
    The input should be a valid python command.
    Useful for data analysis, complex math, or generating plots (though plots won't be visible, data will).
    """
    return python_repl.run(code)


@tool
async def rag_tool(
    query: str,
    limit: int = 5,
    filename: Optional[str] = None,
    filter: Optional[str] = None,  # accepted and ignored — LLM sometimes passes this
) -> str:
    """
    Search the local research vault (internal database) for content from ALL uploaded documents.
    This is the EXCLUSIVE tool for accessing ANY file the user has uploaded: papers, blood work reports,
    lab results, patient reports, pathology reports, imaging reports, clinical guidelines, and PDFs.
    ALWAYS call this tool when the user asks about a patient, their health status, lab values, or uploaded file content.
    If the user asks for a summary, query='summary of the document'.
    If the user refers to a specific file (e.g. 'the report I just uploaded'), provide its filename.
    Returns text chunks and citations.
    """
    tenant_id = current_tenant_id.get()
    if not tenant_id:
        return "Error: Vault context unavailable. Please try again."

    from app.schemas.models import QueryFilters

    visual_keywords = ["figure", "diagram", "table", "graph", "chart", "map", "illustration"]
    is_visual_query = any(k in query.lower() for k in visual_keywords)

    adj_limit = 12 if is_visual_query else limit
    adj_query = f"Research {query} Figure Table Diagram" if is_visual_query else query

    filters = QueryFilters(filename=filename) if filename else None
    try:
        results = await search_vdb(adj_query, tenant_id, limit=adj_limit, filters=filters)
    except Exception as exc:
        return f"Vault search failed: {exc}. Please try again."

    if not results:
        return f"No relevant information found in the vault for '{filename or 'all documents'}'."

    # Assign one SOURCE number per unique file so the LLM doesn't repeat the same
    # paper under multiple citation numbers in the References section.
    file_to_source_num: dict = {}
    next_source_num = 0

    formatted_context = f"--- LOCAL VAULT CONTEXT ({filename or 'Global'}) ---\n"
    for hit in results:
        text = hit["text"]
        media = hit.get("media_url")
        if media:
            text += f"\n[IMAGE_REFERENCE: {BASE_URL}{media}]"

        src_title = hit.get("title") or hit.get("filename", "Unknown")
        src_authors = hit.get("authors")
        src_year = hit.get("year", "")
        src_file = hit.get("filename", "")
        authors_str = (", ".join(src_authors) if isinstance(src_authors, list) and src_authors else "")

        if src_file not in file_to_source_num:
            file_to_source_num[src_file] = next_source_num
            next_source_num += 1
        src_num = file_to_source_num[src_file]

        citation_line = f"[SOURCE {src_num}] {src_title}"
        if authors_str:
            citation_line += f" | Authors: {authors_str}"
        if src_year:
            citation_line += f" | Year: {src_year}"
        if src_file:
            citation_line += f" | File: {src_file}"

        formatted_context += f"{citation_line}\n{text}\n\n"
    return formatted_context


@tool
async def list_vault_papers_tool() -> str:
    """
    Lists all papers and documents currently stored in your research vault.
    Use this if you are unsure which paper the user is referring to or to see the most recently uploaded files.
    Returns filenames, titles, and ingestion timestamps.
    """
    tenant_id = current_tenant_id.get()
    if not tenant_id:
        return "Error: Vault context unavailable."

    from app.services.vector_store import list_unique_papers
    papers = await list_unique_papers(tenant_id)
    if not papers:
        return "The research vault is currently empty."

    output = "--- RESEARCH VAULT CATALOG ---\n"
    for p in papers:
        output += f"- {p['filename']} (Title: {p['title']}) | Uploaded: {p['ingested_at']}\n"
    return output


@tool
async def auto_ingest_paper_tool(arxiv_id: str) -> str:
    """
    Automatically downloads a paper from Arxiv and indexes it into the local research vault.
    Use this after finding a relevant paper via arxiv_search_tool that the user wants to 'add' to their vault.
    arxiv_id should be a string like '2305.10601'.
    """
    tenant_id = current_tenant_id.get()
    if not tenant_id:
        return "Error: Vault context unavailable."

    from app.services.ingestion import download_and_ingest_arxiv
    from app.core.database import SessionLocal, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.tenant_id == tenant_id).first()
        if not user:
            return f"Error: No user found for vault."
        result = await download_and_ingest_arxiv(arxiv_id, user, db)
        return result
    finally:
        db.close()
