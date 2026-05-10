import operator
import sqlite3
from typing import Annotated, List, TypedDict, Union, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.services.tools import arxiv_search_tool, python_repl_tool, list_vault_papers_tool, rag_tool, auto_ingest_paper_tool
from app.core.config import GENERATION_MODEL, GENERATION_TEMP
from guardrails.guardrails import pre_retrieval_guardrail, post_generation_guardrail
from langsmith import traceable

# explanation of the code is present in code_understanding.md



# Define the state of the graph
class ResearchState(TypedDict):
    # messages: The history of the conversation, with add_messages-like behavior
    messages: Annotated[List[BaseMessage], operator.add]
    # tenant_id: To ensure isolation across tools
    tenant_id: str
    # Guardrail and metadata
    is_out_of_scope: bool
    faithfulness_score: float

# Initialize the LLM
llm = ChatOpenAI(model=GENERATION_MODEL, temperature=GENERATION_TEMP, streaming=True)

# Define the tools
tools = [list_vault_papers_tool, rag_tool, arxiv_search_tool, python_repl_tool, auto_ingest_paper_tool]
# Bind tools to the LLM
llm_with_tools = llm.bind_tools(tools)

# Define the nodes
@traceable(name="Pre-Retrieval Guardrail")
async def run_guardrail(state: ResearchState):
    """Checks if the query is in scope for clinical research."""
    messages = state["messages"]
    last_user_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    
    if not last_user_msg:
        return {"is_out_of_scope": False}
        
    res = await pre_retrieval_guardrail(last_user_msg, llm)
    if not res.get("is_in_scope", True):
        return {
            "messages": [AIMessage(content=res.get("reason", "I am sorry, but I can only assist with clinical guidelines and research related to the documents in your vault."))],
            "is_out_of_scope": True
        }
    return {"is_out_of_scope": False}

@traceable(name="MedVault Agent")
async def call_model(state: ResearchState):
    """
    The main brain of the research agent. 
    It takes the context and decides whether to query the vault, search Arxiv, or just answer.
    """
    messages = state["messages"]
    # Inject system instruction if it's the first message in this thread
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_msg = SystemMessage(content=(
            "You are MedVault, a specialized AI assistant for doctors and clinical researchers. "
            "Your role is to ASSIST clinicians — not replace their judgment. Always remind users that clinical decisions rest with the treating clinician. "
            "You have access to: (1) a local clinical vault with ALL documents the user has uploaded, "
            "(2) Arxiv for finding research papers, and (3) a Python sandbox for calculations. "
            "The vault contains whatever the user uploaded: blood work reports, lab results, patient records, "
            "pathology reports, imaging reports, clinical guidelines, research papers, and PDFs. "
            "CRITICAL RULE: When the user asks about a patient, their health, lab results, blood work, or anything "
            "like 'what is wrong with this patient', 'analyze this report', 'interpret these results', or "
            "'what do these values mean' — you MUST call rag_tool FIRST. Do not guess or answer from memory. "
            "NEVER ask the user to re-upload or provide more details if they say they already uploaded a file. "
            "If unsure which file to search, call list_vault_papers_tool first to see what is in the vault. "
            "If a first search returns no results, try a SECOND rag_tool call with more specific clinical keywords "
            "(e.g. 'CBC hemoglobin', 'lipid cholesterol', 'patient name', 'ferritin iron deficiency'). "
            "If a retrieved chunk contains [IMAGE_REFERENCE: URL], display it as: ![Figure](URL). "
            "\n\nCITATION RULES (MANDATORY):\n"
            "Every rag_tool result includes [SOURCE N] headers with title, authors, year, and filename. "
            "You MUST use inline citations like [1], [2] whenever you use information from a source. "
            "At the end of EVERY response that uses vault sources, add a '---\\n**References**' section listing:\n"
            "  [N] Title — Authors (Year) — File: filename\n"
            "If a source has no authors, write 'Clinical Document'. "
            "If you use Arxiv search results, cite them inline as [Arxiv: Paper Title] — NEVER as [N] numbers. "
            "List Arxiv papers in a SEPARATE '**External Sources (Arxiv)**' section, never inside the vault References section. "
            "Arxiv results are external web search results and must NEVER be attributed to the user's uploaded documents or reports. "
            "NEVER fabricate citations. Only cite sources that appeared in the tool output."
        ))
        messages = [system_msg] + messages
    
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}

@traceable(name="Post-Generation Guardrail")
async def check_faithfulness(state: ResearchState):
    """Verifies the grounding of the AI's response."""
    messages = state["messages"]
    last_ai_msg = messages[-1]
    
    if not isinstance(last_ai_msg, AIMessage) or not last_ai_msg.content:
        return {}

    # Gather context from ToolMessages (RAG results)
    context = ""
    for m in reversed(messages):
        if isinstance(m, ToolMessage):
            context += f"\n{m.content}"
    
    # If no tools were used, we assume general knowledge or skip
    if not context:
        return {"faithfulness_score": 1.0}

    last_user_query = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    
    res = await post_generation_guardrail(last_user_query, last_ai_msg.content, context, llm)
    score = res.get("faithfulness_score", 1.0)
    
    from app.core.logging import logger
    logger.info(f"FAITHFULNESS: Score = {score}")
    
    if score < 0.7:
        disclaimer = "\n\n⚠️ This answer may contain information not found in the source documents. Please verify."
        return {"messages": [AIMessage(content=f"Guardrail Note: {disclaimer}")], "faithfulness_score": score}
    
    return {"faithfulness_score": score}

def scope_condition(state: ResearchState):
    """Router for the guardrail."""
    if state.get("is_out_of_scope"):
        return END
    return "agent"

# Define the Tool Node
tool_node = ToolNode(tools, handle_tool_errors=True)

# Build the Graph
workflow = StateGraph(ResearchState)

# Add Nodes
workflow.add_node("guardrail", run_guardrail)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_node("faithfulness", check_faithfulness)

# Add Edges
workflow.add_edge(START, "guardrail")

# Guardrail Router
workflow.add_conditional_edges(
    "guardrail",
    scope_condition,
)

# Use tools_condition to decide whether to continue to tools or go to faithfulness
workflow.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "tools",
        "__end__": "faithfulness"
    }
)

# After tools, always return to the agent
workflow.add_edge("tools", "agent")

# After faithfulness, end
workflow.add_edge("faithfulness", END)

# Function to compile graph (called by lifespan)
def compile_graph(checkpointer):
    return workflow.compile(checkpointer=checkpointer)

