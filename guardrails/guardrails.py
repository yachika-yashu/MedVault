import json
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import GENERATION_MODEL

# all functions explanation can be found in code_understand.md

async def pre_retrieval_guardrail(query: str, llm: ChatOpenAI) -> Dict[str, Any]:
    """
    Checks if the user's question is answerable from clinical guidelines or medical research.
    Returns a dict with 'is_in_scope' (bool) and 'reason' (str).
    """
    system_prompt = (
        "You are a scope-checking guardrail for MedVault, an AI assistant used by doctors and researchers. "
        "Mark a query as IN SCOPE if it relates to ANY of the following: "
        "medical guidelines, clinical research, health protocols, patient reports, blood work, lab results, "
        "pathology reports, imaging reports, drug information, diagnoses, symptoms, treatment plans, "
        "clinical calculations, or any question about documents the user has uploaded. "
        "Mark a query OUT OF SCOPE ONLY if it is clearly unrelated to healthcare or medicine entirely "
        "(e.g. stock prices, recipes, sports scores, coding homework, general trivia). "
        "When in doubt, mark it IN SCOPE. "
        "Return ONLY raw JSON — no markdown, no explanation: "
        "{\"is_in_scope\": true} or {\"is_in_scope\": false, \"reason\": \"polite one-sentence refusal\"}."
    )
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"QUERY: {query}")
    ]
    
    try:
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        # Strip markdown code fences if present
        if "```" in content:
            content = content.split("```")[-2] if content.count("```") >= 2 else content
            content = content.replace("json", "", 1).strip()
        data = json.loads(content)
        return data
    except Exception as e:
        # Fail safe: if guardrail fails, assume in scope but log it
        print(f"Pre-retrieval guardrail error: {e}")
        return {"is_in_scope": True, "reason": ""}

async def post_generation_guardrail(query: str, answer: str, context: str, llm: ChatOpenAI) -> Dict[str, Any]:
    """
    Verifies if the generated answer is grounded in the retrieved chunks.
    Returns a dict with 'faithfulness_score' (float) and 'is_faithful' (bool).
    """
    system_prompt = (
        "You are a faithfulness evaluator. Given the following context, query, and answer, "
        "determine if every factual claim in the answer is supported by the context. "
        "Return a confidence score between 0 and 1, where 1 is perfectly grounded and 0 is completely hallucinated. "
        "Return JSON: {\"faithfulness_score\": 0.XX, \"reasoning\": \"...\"}"
    )
    
    user_prompt = f"CONTEXT:\n{context}\n\nQUERY: {query}\n\nANSWER: {answer}"
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    try:
        response = await llm.ainvoke(messages)
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        data = json.loads(content)
        return data
    except Exception as e:
        print(f"Post-generation guardrail error: {e}")
        return {"faithfulness_score": 1.0, "reasoning": "Bypassed due to error"}
