"""
MedVault - Full End-to-End Feature Test Suite
Run from project root: python test_all_features.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import requests
import json
import time
from pathlib import Path

BASE = "http://localhost:8000/api/v1"
PDF_PATH = Path(__file__).parent / "dummy_blood_report.pdf"

results = []

def log(name, ok, detail=""):
    icon = "[PASS]" if ok else "[FAIL]"
    results.append((name, ok, detail))
    print(f"  {icon}  {name}")
    if detail:
        print(f"          {detail}")

def section(title):
    print(f"\n--- {title} {'-' * (50 - len(title))}")

def sse_collect(resp):
    tokens, tools, metrics, status_ev = [], [], None, None
    for line in resp.iter_lines():
        if not line:
            continue
        text = line.decode() if isinstance(line, bytes) else line
        if not text.startswith("data:"):
            continue
        raw = text[5:].strip()
        if raw == "[DONE]":
            break
        try:
            ev = json.loads(raw)
            ev_type = ev.get("type")
            ev_status = ev.get("status")
            if ev_type == "metrics":
                metrics = ev
            elif ev_status in ("agent_started", "cache_hit"):
                status_ev = ev
                # cache_hit events carry content — capture it as a token too
                if ev_status == "cache_hit" and ev.get("content"):
                    tokens.append(ev["content"])
            elif ev_type == "token":
                tokens.append(ev["content"])
            elif ev_type in ("tool_start", "tool_end"):
                tools.append(ev)
        except Exception:
            pass
    return "".join(tokens), tools, metrics, status_ev

print("\n" + "=" * 60)
print("  MEDVAULT - END-TO-END TEST SUITE")
print("=" * 60)

# -------------------------------------------------------
# 1. HEALTH CHECK
# -------------------------------------------------------
section("1. HEALTH CHECK")
try:
    r = requests.get(f"{BASE}/health", timeout=5)
    data = r.json()
    ok = r.status_code == 200 and data.get("status") == "healthy"
    log("Health endpoint", ok, json.dumps(data))
except Exception as e:
    log("Health endpoint", False, str(e))

# -------------------------------------------------------
# 2. AUTH
# -------------------------------------------------------
section("2. AUTH")
TOKEN = None
test_user = f"testrunner_{int(time.time())}"
test_pass = "SecurePass@123"

try:
    r = requests.post(f"{BASE}/auth/register",
        json={"username": test_user, "password": test_pass, "team_code": "testteam"}, timeout=5)
    ok = r.status_code == 200 and "tenant_id" in r.json()
    log("Register new user", ok, f"user={test_user}, status={r.status_code}")
except Exception as e:
    log("Register new user", False, str(e))

try:
    r = requests.post(f"{BASE}/auth/register",
        json={"username": test_user, "password": test_pass, "team_code": "testteam"}, timeout=5)
    ok = r.status_code == 400
    log("Duplicate register blocked", ok, f"status={r.status_code}")
except Exception as e:
    log("Duplicate register blocked", False, str(e))

try:
    r = requests.post(f"{BASE}/auth/token",
        data={"username": test_user, "password": test_pass}, timeout=5)
    ok = r.status_code == 200 and "access_token" in r.json()
    if ok:
        TOKEN = r.json()["access_token"]
    log("Login - get token", ok, f"status={r.status_code}, token_ok={TOKEN is not None}")
except Exception as e:
    log("Login - get token", False, str(e))

try:
    r = requests.post(f"{BASE}/auth/token",
        data={"username": test_user, "password": "wrongpassword"}, timeout=5)
    ok = r.status_code in (400, 401)
    log("Wrong password rejected", ok, f"status={r.status_code}")
except Exception as e:
    log("Wrong password rejected", False, str(e))

try:
    r = requests.get(f"{BASE}/vault/papers", timeout=5)
    ok = r.status_code == 401
    log("Unauthenticated access blocked", ok, f"status={r.status_code}")
except Exception as e:
    log("Unauthenticated access blocked", False, str(e))

if not TOKEN:
    print("\n[FATAL] No auth token - cannot continue.\n")
    sys.exit(1)

HDR = {"Authorization": f"Bearer {TOKEN}"}

# -------------------------------------------------------
# 3. INGEST
# -------------------------------------------------------
section("3. INGEST")

try:
    with open(PDF_PATH, "rb") as f:
        r = requests.post(f"{BASE}/ingest", headers=HDR,
            files={"file": ("dummy_blood_report.pdf", f, "application/pdf")},
            timeout=120)
    raw = r.text
    ok = "completed" in raw and "success" in raw
    chunks = None
    for line in raw.split("\n"):
        if line.startswith("data:") and "completed" in line:
            try:
                ev = json.loads(line[5:])
                chunks = ev.get("result", {}).get("chunking", {}).get("total_chunks")
            except Exception:
                pass
    log("Upload PDF (dummy_blood_report.pdf)", ok, f"chunks={chunks}")
except Exception as e:
    log("Upload PDF", False, str(e))

# Upload a second copy for compare/literature tests
try:
    with open(PDF_PATH, "rb") as f:
        content = f.read()
    r = requests.post(f"{BASE}/ingest", headers=HDR,
        files={"file": ("cbc_report_v2.pdf", content, "application/pdf")},
        timeout=120)
    raw = r.text
    ok = "completed" in raw and "success" in raw
    log("Upload 2nd PDF (cbc_report_v2.pdf)", ok, "needed for compare/literature tests")
except Exception as e:
    log("Upload 2nd PDF", False, str(e))

time.sleep(2)

# -------------------------------------------------------
# 4. VAULT MANAGEMENT
# -------------------------------------------------------
section("4. VAULT MANAGEMENT")

try:
    r = requests.get(f"{BASE}/vault/papers", headers=HDR, timeout=10)
    data = r.json()
    papers = data.get("papers", [])
    ok = r.status_code == 200 and len(papers) >= 2
    log("List vault papers", ok, f"count={len(papers)}, files={[p['filename'] for p in papers]}")
except Exception as e:
    log("List vault papers", False, str(e))

try:
    r = requests.get(f"{BASE}/debug/stats", headers=HDR, timeout=10)
    data = r.json()
    ok = r.status_code == 200 and data.get("points_in_vault", 0) > 0
    log("Debug stats (multi-tenant isolation)", ok,
        f"tenant_points={data.get('points_in_vault')}, collection_total={data.get('total_points_in_collection')}")
except Exception as e:
    log("Debug stats", False, str(e))

# -------------------------------------------------------
# 5. RAG QUERIES
# -------------------------------------------------------
section("5. RAG QUERIES")
THREAD_ID = None

# 5a. Clinical RAG query — unique timestamp makes it cache-miss guaranteed
unique_platelet_q = f"Platelet count analysis {int(time.time())}: what is the platelet count and is there a bleeding risk in this CBC report?"
try:
    r = requests.post(f"{BASE}/query", headers=HDR,
        json={"query": unique_platelet_q},
        stream=True, timeout=90)
    answer, tools, metrics, status_ev = sse_collect(r)
    ok = len(answer) > 30 and ("platelet" in answer.lower() or "95" in answer or "thrombocytopenia" in answer.lower())
    if status_ev and status_ev.get("thread_id"):
        THREAD_ID = status_ev.get("thread_id")
    tool_names = [t["tool"] for t in tools if t.get("type") == "tool_start"]
    log("RAG query - platelet / bleeding risk", ok,
        f"tools={tool_names}, len={len(answer)}, preview={answer[:80]!r}")
except Exception as e:
    log("RAG query - platelet / bleeding risk", False, str(e))

# 5b. RAG query - hemoglobin
try:
    r = requests.post(f"{BASE}/query", headers=HDR,
        json={"query": "What does the hemoglobin level indicate and what follow-up is needed?"},
        stream=True, timeout=90)
    answer, tools, metrics, _ = sse_collect(r)
    ok = len(answer) > 30 and ("hemoglobin" in answer.lower() or "hb" in answer.lower() or "8.2" in answer)
    log("RAG query - hemoglobin follow-up", ok,
        f"len={len(answer)}, preview={answer[:80]!r}")
except Exception as e:
    log("RAG query - hemoglobin follow-up", False, str(e))

# 5c. Filename-filtered query
try:
    r = requests.post(f"{BASE}/query", headers=HDR,
        json={"query": "Summarize the key abnormal findings in this patient report",
              "filename": "dummy_blood_report.pdf"},
        stream=True, timeout=90)
    answer, tools, metrics, _ = sse_collect(r)
    ok = len(answer) > 30
    log("RAG query - filename filtered", ok, f"len={len(answer)}, preview={answer[:80]!r}")
except Exception as e:
    log("RAG query - filename filtered", False, str(e))

# 5d. Metrics check — unique query ensures no cache hit
try:
    unique_q = f"Explain the MCV value {int(time.time())} fL in the CBC report uploaded"
    r = requests.post(f"{BASE}/query", headers=HDR,
        json={"query": unique_q},
        stream=True, timeout=90)
    answer, tools, metrics, _ = sse_collect(r)
    ok = metrics is not None and metrics.get("latency_ms") is not None
    log("SSE metrics in response", ok,
        f"latency={metrics.get('latency_ms') if metrics else None}ms, tokens_out={metrics.get('tokens_out') if metrics else None}")
except Exception as e:
    log("SSE metrics in response", False, str(e))

# 5e. Out-of-scope query (guardrail)
try:
    r = requests.post(f"{BASE}/query", headers=HDR,
        json={"query": "Write me a poem about the moon and tell me a pasta recipe"},
        stream=True, timeout=90)
    answer, tools, metrics, _ = sse_collect(r)
    ok = len(answer) > 0  # Should not crash - guardrail or redirect
    log("Out-of-scope guardrail (no crash)", ok,
        f"len={len(answer)}, preview={answer[:80]!r}")
except Exception as e:
    log("Out-of-scope guardrail", False, str(e))

# 5f. Cache hit test — repeat the exact same unique query from 5a
try:
    time.sleep(1)
    r = requests.post(f"{BASE}/query", headers=HDR,
        json={"query": unique_platelet_q},
        stream=True, timeout=30)
    answer, tools, metrics, status_ev = sse_collect(r)
    cache_hit = status_ev and status_ev.get("status") == "cache_hit"
    ok = len(answer) > 10 and cache_hit
    log("Cache hit (repeat query)", ok,
        f"cache_hit_detected={cache_hit}, len={len(answer)}")
except Exception as e:
    log("Cache hit (repeat query)", False, str(e))

# -------------------------------------------------------
# 6. CHAT THREADS + HISTORY
# -------------------------------------------------------
section("6. CHAT THREADS & HISTORY")

try:
    r = requests.get(f"{BASE}/chat/threads", headers=HDR, timeout=10)
    data = r.json()
    ok = r.status_code == 200 and isinstance(data.get("threads"), list)
    log("List chat threads", ok, f"thread_count={len(data.get('threads', []))}")
except Exception as e:
    log("List chat threads", False, str(e))

if THREAD_ID:
    print(f"          [DEBUG] THREAD_ID={THREAD_ID!r}")
    try:
        r = requests.get(f"{BASE}/chat/history/{THREAD_ID}", headers=HDR, timeout=10)
        raw_body = r.text
        print(f"          [DEBUG] history status={r.status_code} body={raw_body[:300]!r}")
        data = r.json()
        msgs = data.get("messages", [])
        ok = r.status_code == 200 and len(msgs) >= 1
        roles = [m["role"] for m in msgs]
        log("Chat history for thread", ok,
            f"thread={THREAD_ID[:16]}..., msgs={len(msgs)}, roles={roles}")
    except Exception as e:
        log("Chat history for thread", False, f"status={r.status_code if 'r' in dir() else '?'} body={r.text[:200]!r if 'r' in dir() else '?'} err={e}")
else:
    log("Chat history for thread", False, "No thread_id captured")

try:
    r = requests.get(f"{BASE}/chat/history/nonexistent-thread-id", headers=HDR, timeout=10)
    data = r.json()
    ok = r.status_code == 200 and data.get("messages") == []
    log("Chat history - unknown thread returns empty", ok,
        f"status={r.status_code}, messages={data.get('messages')}")
except Exception as e:
    log("Chat history - unknown thread", False, str(e))

# -------------------------------------------------------
# 7. USAGE STATS + TRACE
# -------------------------------------------------------
section("7. USAGE STATS & TRACE")

usage_id = None
try:
    r = requests.get(f"{BASE}/stats/usage", headers=HDR, timeout=10)
    data = r.json()
    ok = r.status_code == 200 and "total_tokens" in data
    history = data.get("history", [])
    if history:
        usage_id = history[-1].get("id")
    log("Usage metrics", ok,
        f"total_tokens={data.get('total_tokens')}, cost=${data.get('total_cost_usd')}, events={len(history)}")
except Exception as e:
    log("Usage metrics", False, str(e))

if usage_id:
    try:
        # Try all history events to find one with a trace (cache hits don't create traces)
        trace_found = False
        for event in reversed(data.get("history", [])):
            eid = event.get("id")
            if not eid:
                continue
            r2 = requests.get(f"{BASE}/stats/trace/{eid}", headers=HDR, timeout=10)
            if r2.status_code == 200 and "prompt" in r2.json():
                trace_data = r2.json()
                ok = bool(trace_data.get("verifier"))
                log("Deep trace lookup", ok,
                    f"usage_id={eid}, has_verifier={ok}, verifier={trace_data.get('verifier')}")
                trace_found = True
                break
        if not trace_found:
            log("Deep trace lookup", False, "No trace found for any usage event")
    except Exception as e:
        log("Deep trace lookup", False, str(e))
else:
    log("Deep trace lookup", False, "No usage_id available")

try:
    r = requests.get(f"{BASE}/stats/trace/00000000-0000-0000-0000-000000000000", headers=HDR, timeout=10)
    ok = r.status_code == 404
    log("Trace - unknown ID returns 404", ok, f"status={r.status_code}")
except Exception as e:
    log("Trace - unknown ID returns 404", False, str(e))

# -------------------------------------------------------
# 8. VAULT SUMMARY
# -------------------------------------------------------
section("8. VAULT SUMMARY")

try:
    r = requests.post(f"{BASE}/vault/summary", headers=HDR,
        json={"filename": "dummy_blood_report.pdf"}, timeout=30)
    data = r.json()
    ok = r.status_code == 200 and len(data.get("summary", "")) > 50
    log("Document summary", ok,
        f"len={len(data.get('summary', ''))}, preview={data.get('summary', '')[:100]!r}")
except Exception as e:
    log("Document summary", False, str(e))

try:
    r = requests.post(f"{BASE}/vault/summary", headers=HDR, json={}, timeout=10)
    ok = r.status_code == 400
    log("Summary - missing filename -> 400", ok, f"status={r.status_code}")
except Exception as e:
    log("Summary - missing filename -> 400", False, str(e))

try:
    r = requests.post(f"{BASE}/vault/summary", headers=HDR,
        json={"filename": "nonexistent_file.pdf"}, timeout=10)
    ok = r.status_code == 404
    log("Summary - nonexistent file -> 404", ok, f"status={r.status_code}")
except Exception as e:
    log("Summary - nonexistent file -> 404", False, str(e))

# -------------------------------------------------------
# 9. VAULT COMPARE
# -------------------------------------------------------
section("9. VAULT COMPARE")

try:
    r = requests.post(f"{BASE}/vault/compare", headers=HDR,
        json={
            "file_a": "dummy_blood_report.pdf",
            "file_b": "cbc_report_v2.pdf",
            "question": "Compare the CBC findings and anemia severity."
        }, timeout=45)
    data = r.json()
    ok = r.status_code == 200 and len(data.get("comparison", "")) > 50
    log("Compare 2 documents", ok,
        f"len={len(data.get('comparison', ''))}, preview={data.get('comparison', '')[:80]!r}")
except Exception as e:
    log("Compare 2 documents", False, str(e))

try:
    r = requests.post(f"{BASE}/vault/compare", headers=HDR,
        json={"file_a": "dummy_blood_report.pdf"}, timeout=10)
    ok = r.status_code == 400
    log("Compare - missing file_b -> 400", ok, f"status={r.status_code}")
except Exception as e:
    log("Compare - missing file_b -> 400", False, str(e))

# -------------------------------------------------------
# 10. GUIDELINE SEARCH
# -------------------------------------------------------
section("10. GUIDELINE SEARCH")

try:
    r = requests.post(f"{BASE}/vault/guideline-search", headers=HDR,
        json={"condition": "iron deficiency anemia management"}, timeout=30)
    data = r.json()
    ok = r.status_code == 200 and len(data.get("result", "")) > 50
    log("Guideline search - anemia", ok,
        f"sources={data.get('sources')}, len={len(data.get('result', ''))}")
except Exception as e:
    log("Guideline search", False, str(e))

try:
    r = requests.post(f"{BASE}/vault/guideline-search", headers=HDR, json={}, timeout=10)
    ok = r.status_code == 400
    log("Guideline search - missing condition -> 400", ok, f"status={r.status_code}")
except Exception as e:
    log("Guideline search - missing condition -> 400", False, str(e))

# -------------------------------------------------------
# 11. LITERATURE REVIEW
# -------------------------------------------------------
section("11. LITERATURE REVIEW")

try:
    r = requests.post(f"{BASE}/vault/literature-review", headers=HDR,
        json={
            "topic": "anemia severity and clinical management in CBC findings",
            "filenames": ["dummy_blood_report.pdf", "cbc_report_v2.pdf"]
        }, timeout=60)
    data = r.json()
    ok = r.status_code == 200 and len(data.get("review", "")) > 100
    log("Literature review (2 papers)", ok,
        f"papers_reviewed={data.get('papers_reviewed')}, len={len(data.get('review', ''))}")
except Exception as e:
    log("Literature review", False, str(e))

try:
    r = requests.post(f"{BASE}/vault/literature-review", headers=HDR,
        json={"topic": "anemia", "filenames": ["dummy_blood_report.pdf"]}, timeout=10)
    ok = r.status_code == 400
    log("Literature review - only 1 paper -> 400", ok, f"status={r.status_code}")
except Exception as e:
    log("Literature review - only 1 paper -> 400", False, str(e))

try:
    r = requests.post(f"{BASE}/vault/literature-review", headers=HDR,
        json={"filenames": ["a.pdf", "b.pdf"]}, timeout=10)
    ok = r.status_code == 400
    log("Literature review - missing topic -> 400", ok, f"status={r.status_code}")
except Exception as e:
    log("Literature review - missing topic -> 400", False, str(e))

# -------------------------------------------------------
# 12. PROTOCOL SEARCH
# -------------------------------------------------------
section("12. PROTOCOL SEARCH")

try:
    r = requests.post(f"{BASE}/vault/protocol-search", headers=HDR,
        json={"procedure": "anemia treatment protocol"}, timeout=30)
    data = r.json()
    # 200 (found something) or 404 (no protocol doc) both acceptable
    ok = r.status_code in (200, 404)
    detail = data.get("result", data.get("detail", ""))
    log("Protocol search (200 or 404 OK)", ok,
        f"status={r.status_code}, preview={str(detail)[:80]!r}")
except Exception as e:
    log("Protocol search", False, str(e))

try:
    r = requests.post(f"{BASE}/vault/protocol-search", headers=HDR, json={}, timeout=10)
    ok = r.status_code == 400
    log("Protocol search - missing procedure -> 400", ok, f"status={r.status_code}")
except Exception as e:
    log("Protocol search - missing procedure -> 400", False, str(e))

# -------------------------------------------------------
# 13. MULTI-TENANT ISOLATION
# -------------------------------------------------------
section("13. MULTI-TENANT ISOLATION")

try:
    u2 = f"tenant2_{int(time.time())}"
    requests.post(f"{BASE}/auth/register",
        json={"username": u2, "password": "IsoTest@456", "team_code": "otherteam"}, timeout=5)
    r2 = requests.post(f"{BASE}/auth/token",
        data={"username": u2, "password": "IsoTest@456"}, timeout=5)
    tok2 = r2.json().get("access_token")
    hdr2 = {"Authorization": f"Bearer {tok2}"}

    papers2 = requests.get(f"{BASE}/vault/papers", headers=hdr2, timeout=10).json().get("papers", [])
    stats2 = requests.get(f"{BASE}/debug/stats", headers=hdr2, timeout=10).json()

    ok = len(papers2) == 0 and stats2.get("points_in_vault", 0) == 0
    log("Tenant 2 sees zero papers (isolation)", ok,
        f"papers={len(papers2)}, qdrant_points={stats2.get('points_in_vault')}")
except Exception as e:
    log("Multi-tenant isolation", False, str(e))

# -------------------------------------------------------
# 14. DELETE PAPER
# -------------------------------------------------------
section("14. DELETE PAPER")

try:
    r = requests.delete(f"{BASE}/vault/papers/cbc_report_v2.pdf", headers=HDR, timeout=10)
    data = r.json()
    ok = r.status_code == 200 and data.get("status") == "deleted"
    log("Delete paper", ok, f"status={data.get('status')}, file={data.get('filename')}")

    time.sleep(1)
    papers = requests.get(f"{BASE}/vault/papers", headers=HDR, timeout=10).json().get("papers", [])
    still_there = any(p["filename"] == "cbc_report_v2.pdf" for p in papers)
    log("Deleted paper absent from vault", not still_there,
        f"remaining={[p['filename'] for p in papers]}")
except Exception as e:
    log("Delete paper", False, str(e))

# -------------------------------------------------------
# FINAL SUMMARY
# -------------------------------------------------------
print("\n" + "=" * 60)
print("  FINAL RESULTS")
print("=" * 60)

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)

for name, ok, detail in results:
    icon = "[PASS]" if ok else "[FAIL]"
    print(f"  {icon}  {name}")

print(f"\n  Total: {total}   Passed: {passed}   Failed: {failed}")
print("=" * 60)

if failed > 0:
    print(f"\nFAILED TESTS ({failed}):")
    for name, ok, detail in results:
        if not ok:
            print(f"  [FAIL]  {name}")
            if detail:
                print(f"          {detail}")
    sys.exit(1)
else:
    print("\n** ALL TESTS PASSED! App is ready for deployment. **\n")
    sys.exit(0)
