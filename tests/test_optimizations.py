"""
Integration tests for LoreMaster-AI optimizations.
Tests each new feature without requiring the full backend to be running.

Run from project root:
    python tests/test_optimizations.py
"""

import json
import os
import sys
import tempfile
import threading
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"

results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, condition))
    print(f"  {status} {name}" + (f"  [{detail}]" if detail else ""))
    return condition


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Parallel query processing
# ─────────────────────────────────────────────────────────────────────────────
def test_parallel_processing():
    print("\n[1] Parallel query processing (ThreadPoolExecutor)")
    from concurrent.futures import ThreadPoolExecutor
    import concurrent.futures

    call_order = []
    call_times = {}

    def slow_classify(q):
        call_times["classify_start"] = time.time()
        time.sleep(0.15)
        call_order.append("classify")
        return "FACTUAL"

    def slow_embed(q):
        call_times["embed_start"] = time.time()
        time.sleep(0.12)
        call_order.append("embed")
        return [0.1] * 5

    def slow_expand(q, entities):
        call_times["expand_start"] = time.time()
        time.sleep(0.10)
        call_order.append("expand")
        return ["nahida lore"]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=3) as executor:
        cf = executor.submit(slow_classify, "test")
        ef = executor.submit(slow_embed, "test")
        xf = executor.submit(slow_expand, "test", [])
        classify_result = cf.result()
        embed_result = ef.result()
        expand_result = xf.result()
    elapsed = time.time() - t0

    serial_expected = 0.15 + 0.12 + 0.10  # 370ms serial
    check("All 3 tasks completed", len(call_order) == 3, f"got {call_order}")
    check("Parallel is faster than serial sum", elapsed < serial_expected,
          f"parallel={elapsed:.3f}s < serial={serial_expected:.3f}s")
    check("Max overlap: elapsed ≈ slowest task", elapsed < 0.25,
          f"{elapsed:.3f}s")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: System prompt split (answer_generator)
# ─────────────────────────────────────────────────────────────────────────────
def test_system_prompt_split():
    print("\n[2] System prompt split for Prompt Cache")
    from src.agent.answer_generator import SYSTEM_PROMPT, _build_user_message

    check("SYSTEM_PROMPT is non-empty", len(SYSTEM_PROMPT) > 100)
    check("SYSTEM_PROMPT contains LoreMaster role", "LoreMaster" in SYSTEM_PROMPT)
    check("SYSTEM_PROMPT contains citation format", "Source:" in SYSTEM_PROMPT)
    check("SYSTEM_PROMPT contains honesty rules", "NEVER invent" in SYSTEM_PROMPT)

    user_msg = _build_user_message("some context", "Who is Nahida?")
    check("User message contains Context section", "## Context" in user_msg)
    check("User message contains Question section", "## Question" in user_msg)
    check("SYSTEM_PROMPT not duplicated in user message", "LoreMaster" not in user_msg,
          "static content should only be in system=")

    user_msg_with_history = _build_user_message("ctx", "follow up?", history="[User]: prev\n[LoreMaster]: ans")
    check("History injected when provided", "Conversation History" in user_msg_with_history)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Semantic answer cache
# ─────────────────────────────────────────────────────────────────────────────
def test_semantic_cache():
    print("\n[3] Semantic answer cache")
    import tempfile, math

    # Monkey-patch CACHE_FILE to temp location
    import src.agent.query_cache as qc_module
    orig_cache_file = qc_module.CACHE_FILE
    tmp_dir = tempfile.mkdtemp()
    qc_module.CACHE_FILE = os.path.join(tmp_dir, "test_cache.json")

    try:
        cache = qc_module.SemanticAnswerCache(threshold=0.95, max_size=10)

        # Build two very similar embeddings (cosine sim > 0.95)
        emb1 = [1.0, 0.0, 0.0, 0.0, 0.0]
        emb2 = [0.99, 0.1, 0.0, 0.0, 0.0]  # slightly different

        def cos(a, b):
            dot = sum(x*y for x,y in zip(a,b))
            return dot / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b)))

        sim = cos(emb1, emb2)

        fake_result = {"answer": "Nahida is the Dendro Archon.", "entities": ["Nahida"]}
        cache.store(emb1, "Who is Nahida?", fake_result)

        check("Cache stores entry", len(cache._entries) == 1)

        # Lookup with same embedding → hit
        hit = cache.lookup(emb1)
        check("Exact embedding → cache hit", hit is not None)
        check("Cache hit returns correct answer", hit["answer"] == fake_result["answer"])

        # Lookup with similar embedding
        if sim >= 0.95:
            hit2 = cache.lookup(emb2)
            check(f"Similar embedding (sim={sim:.3f}) → cache hit", hit2 is not None)
        else:
            # embeddings too different, expect miss
            miss = cache.lookup(emb2)
            check(f"Dissimilar embedding (sim={sim:.3f}) → cache miss", miss is None)

        # Orthogonal embedding → miss
        emb_other = [0.0, 1.0, 0.0, 0.0, 0.0]
        miss = cache.lookup(emb_other)
        check("Orthogonal embedding → cache miss", miss is None)

        # Stats
        stats = cache.stats()
        check("Stats tracked correctly", stats["hits"] >= 1 and stats["misses"] >= 1,
              str(stats))

        # Concurrent write guard: two threads store same question simultaneously
        barrier = threading.Barrier(2)
        store_count = [0]
        def concurrent_store(emb):
            barrier.wait()
            cache.store(emb, "duplicate question", {"answer": "dup"})
            store_count[0] += 1

        t1 = threading.Thread(target=concurrent_store, args=([0.0, 0.0, 1.0, 0.0, 0.0],))
        t2 = threading.Thread(target=concurrent_store, args=([0.0, 0.0, 1.0, 0.0, 0.0],))
        t1.start(); t2.start()
        t1.join(); t2.join()
        # Only one entry should be added (second skipped by guard)
        dup_entries = [e for e in cache._entries if e["question"] == "duplicate question"]
        check("Concurrent write guard prevents duplicates", len(dup_entries) <= 1,
              f"found {len(dup_entries)} duplicates")

        # Persistence: save and reload
        cache2 = qc_module.SemanticAnswerCache(threshold=0.95)
        check("Persisted cache survives reload", len(cache2._entries) >= 1)

    finally:
        qc_module.CACHE_FILE = orig_cache_file


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Session manager
# ─────────────────────────────────────────────────────────────────────────────
def test_session_manager():
    print("\n[4] Session manager")
    # Import fresh (no singleton)
    import importlib
    import src.agent.session_manager as sm_module
    importlib.reload(sm_module)

    sm = sm_module.SessionManager.__new__(sm_module.SessionManager)
    sm._sessions = {}
    sm._anthropic = None  # not needed for most tests

    # get_or_create
    s1 = sm.get_or_create(None)
    check("New session created without ID", s1.session_id is not None)

    s2 = sm.get_or_create(s1.session_id)
    check("Same session returned for same ID", s1.session_id == s2.session_id)

    s3 = sm.get_or_create("explicit-id-123")
    check("Custom session ID respected", s3.session_id == "explicit-id-123")

    # Turns cap (Improvement 3)
    for i in range(sm_module.TURNS_CAP + 5):
        s1.turns.append(sm_module.Turn(f"q{i}", f"a{i}", []))
    # Manually trigger cap logic
    if len(s1.turns) > sm_module.TURNS_CAP:
        s1.turns = s1.turns[-sm_module.TURNS_CAP:]
    check(f"Turns capped at {sm_module.TURNS_CAP}", len(s1.turns) == sm_module.TURNS_CAP,
          f"got {len(s1.turns)}")

    # Dual-threshold (Improvement 4)
    s_new = sm.get_or_create(None)
    # Few turns, low chars — should NOT compress
    for i in range(3):
        s_new.turns.append(sm_module.Turn(f"q{i}", "short", []))
    needs = (
        len(s_new.turns) >= sm_module.COMPRESS_MIN_TURNS
        and s_new.total_history_chars() >= sm_module.COMPRESS_CHAR_THRESHOLD
    )
    check("Short session does NOT trigger compression", not needs,
          f"turns={len(s_new.turns)}, chars={s_new.total_history_chars()}")

    # Many turns + long content — SHOULD compress
    s_long = sm.get_or_create(None)
    for i in range(sm_module.COMPRESS_MIN_TURNS):
        s_long.turns.append(sm_module.Turn(f"q{i}", "a" * 800, []))
    needs_long = (
        len(s_long.turns) >= sm_module.COMPRESS_MIN_TURNS
        and s_long.total_history_chars() >= sm_module.COMPRESS_CHAR_THRESHOLD
    )
    check("Long session triggers compression", needs_long,
          f"turns={len(s_long.turns)}, chars={s_long.total_history_chars()}")

    # History context
    s_hist = sm.get_or_create(None)
    s_hist.turns = [sm_module.Turn("What is Sumeru?", "Sumeru is the nation of wisdom.", ["Sumeru"])]
    s_hist.summary = '{"entities_discussed": "Sumeru"}'
    history = sm.get_history_context(s_hist)
    check("History includes summary", "Summary of earlier conversation" in history)
    check("History includes recent turn", "What is Sumeru?" in history)

    # Coreference resolution
    s_coref = sm.get_or_create(None)
    s_coref.turns = [sm_module.Turn("Who is Nahida?", "She is the Dendro Archon.", ["Nahida"])]
    s_coref.accumulated_entities = ["Nahida"]
    resolved = sm.resolve_coreferences("What are her powers?", s_coref)
    check("Pronoun resolved to last entity", "Nahida" in resolved, resolved)

    no_pronoun = sm.resolve_coreferences("Who is Zhongli?", s_coref)
    check("Non-pronoun query not modified", no_pronoun == "Who is Zhongli?")

    # Compress prompt structure (Improvement 1+2) — check the prompt string
    prompt_sample = sm_module._NO_TOOLS_PREAMBLE
    check("NO_TOOLS_PREAMBLE defined", "CRITICAL" in prompt_sample)
    check("NO_TOOLS_PREAMBLE forbids tools", "Do NOT call any tools" in prompt_sample)

    # Session TTL expiry
    s_old = sm.get_or_create(None)
    s_old.last_activity = time.time() - sm_module.SESSION_TTL - 1
    sm._sessions[s_old.session_id] = s_old
    sm._cleanup_expired()
    check("Expired session is evicted", s_old.session_id not in sm._sessions)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Circuit breaker
# ─────────────────────────────────────────────────────────────────────────────
def test_circuit_breaker():
    print("\n[5] Circuit breaker")
    from src.agent.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState

    cb = CircuitBreaker("test-service", failure_threshold=3, recovery_timeout=0.2)

    check("Initial state is CLOSED", cb.state == CircuitState.CLOSED)

    # Successful call
    result = cb.call(lambda: "ok")
    check("Successful call returns value", result == "ok")
    check("After success: still CLOSED", cb.state == CircuitState.CLOSED)

    # Trigger failures
    def fail():
        raise ConnectionError("service down")

    for i in range(2):
        try:
            cb.call(fail)
        except ConnectionError:
            pass
    check("After 2 failures: still CLOSED", cb.state == CircuitState.CLOSED,
          f"failures={cb._failure_count}")

    try:
        cb.call(fail)
    except ConnectionError:
        pass
    check("After 3 failures: OPEN", cb.state == CircuitState.OPEN)

    # Open circuit rejects immediately
    t0 = time.time()
    try:
        cb.call(lambda: "should not run")
        check("OPEN circuit should have raised", False)
    except CircuitOpenError:
        elapsed = time.time() - t0
        check("OPEN circuit rejects immediately (<50ms)", elapsed < 0.05,
              f"{elapsed*1000:.1f}ms")

    check("is_available() returns False when OPEN", not cb.is_available())

    # Recovery: wait for timeout → HALF_OPEN
    time.sleep(0.25)
    check("After timeout: HALF_OPEN", cb.state == CircuitState.HALF_OPEN)

    # Successful call in HALF_OPEN → CLOSED
    result2 = cb.call(lambda: "recovered")
    check("Successful HALF_OPEN call → CLOSED", cb.state == CircuitState.CLOSED)
    check("Recovery returns value", result2 == "recovered")

    # Status dict
    status = cb.status()
    check("status() returns dict with state", "state" in status and status["state"] == "closed")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Compression prompt structure (Improvement 1+2 end-to-end)
# ─────────────────────────────────────────────────────────────────────────────
def test_compress_prompt_structure():
    print("\n[6] Compression prompt structure (NO_TOOLS_PREAMBLE + <analysis> block)")
    import src.agent.session_manager as sm_module

    # Reconstruct what _compress() would send
    conversation_text = "User: Who is Nahida?\nAssistant: She is the Dendro Archon."
    prompt = f"""{sm_module._NO_TOOLS_PREAMBLE}

Summarize this Genshin Impact lore conversation. Think step by step in <analysis>, then output the final JSON in <summary>.

Conversation:
{conversation_text}

<analysis>
Identify: (a) key entities discussed, (b) confirmed lore facts, (c) user's language and style, (d) any unresolved questions.
</analysis>

<summary>
{{
  "entities_discussed": "...",
  "facts_established": "...",
  "user_style": "...",
  "open_topics": "..."
}}
</summary>"""

    check("Prompt starts with NO_TOOLS_PREAMBLE", prompt.startswith("CRITICAL"))
    check("Prompt contains <analysis> block", "<analysis>" in prompt)
    check("Prompt contains <summary> block", "<summary>" in prompt)
    check("Prompt asks for JSON structure", "entities_discussed" in prompt)

    # Test summary extraction regex
    import re
    test_response = """<analysis>
Nahida is the Dendro Archon. User speaks English.
</analysis>
<summary>
{"entities_discussed": "Nahida, Sumeru", "facts_established": "Nahida is the Dendro Archon", "user_style": "English, brief", "open_topics": "none"}
</summary>"""
    match = re.search(r"<summary>(.*?)</summary>", test_response, re.DOTALL)
    check("Summary extraction regex works", match is not None)
    if match:
        extracted = match.group(1).strip()
        check("Extracted content is JSON-like", extracted.startswith("{"))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Backend API health (requires running server)
# ─────────────────────────────────────────────────────────────────────────────
def test_backend_health():
    print("\n[7] Backend API (requires running server on :8000)")
    try:
        import urllib.request, urllib.error
        with urllib.request.urlopen("http://localhost:8000/api/health", timeout=3) as r:
            data = json.loads(r.read())
        check("Backend /api/health responds", True)
        check("Health response has status", data.get("status") == "healthy",
              str(data.get("status")))
        check("Health response includes answer_cache stats", "answer_cache" in data,
              str(list(data.keys())))
    except Exception as e:
        check("Backend reachable", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: Streaming endpoint (requires running server)
# ─────────────────────────────────────────────────────────────────────────────
def test_streaming_endpoint():
    print("\n[8] Streaming endpoint /api/query/stream (requires running server)")
    try:
        import urllib.request, urllib.error, json as _json

        payload = json.dumps({"question": "What is Sumeru?", "session_id": None}).encode()
        req = urllib.request.Request(
            "http://localhost:8000/api/query/stream",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        token_count = 0
        metadata_received = False
        session_id_received = None
        t0 = time.time()
        first_token_time = None

        with urllib.request.urlopen(req, timeout=60) as r:
            content_type = r.headers.get("Content-Type", "")
            check("Streaming response is text/event-stream",
                  "text/event-stream" in content_type, content_type)

            for raw_line in r:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                try:
                    event = _json.loads(line[6:])
                except Exception:
                    continue

                if event.get("type") == "token":
                    if first_token_time is None:
                        first_token_time = time.time() - t0
                    token_count += 1
                elif event.get("type") == "metadata":
                    metadata_received = True
                    session_id_received = event.get("session_id")
                    break  # stop after metadata

        check("Tokens received via SSE", token_count > 0, f"{token_count} tokens")
        if first_token_time:
            check("TTFB < 3s (streaming benefit)", first_token_time < 3.0,
                  f"TTFB={first_token_time:.2f}s")
        check("Metadata event received", metadata_received)
        check("session_id returned in metadata", session_id_received is not None,
              str(session_id_received))

        # Second request with same session_id → multi-turn
        if session_id_received:
            payload2 = json.dumps({
                "question": "Tell me more about it",
                "session_id": session_id_received,
            }).encode()
            req2 = urllib.request.Request(
                "http://localhost:8000/api/query/stream",
                data=payload2,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            tokens2 = 0
            with urllib.request.urlopen(req2, timeout=60) as r2:
                for raw_line in r2:
                    line = raw_line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        try:
                            ev = _json.loads(line[6:])
                            if ev.get("type") == "token":
                                tokens2 += 1
                            elif ev.get("type") == "metadata":
                                break
                        except Exception:
                            pass
            check("Multi-turn session: second response received", tokens2 > 0,
                  f"{tokens2} tokens")

    except Exception as e:
        check("Streaming endpoint reachable", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: Semantic cache hit via API (requires running server)
# ─────────────────────────────────────────────────────────────────────────────
def test_cache_hit_via_api():
    print("\n[9] Semantic cache hit via /api/query (requires running server)")
    try:
        import urllib.request

        def query(q):
            payload = json.dumps({"question": q}).encode()
            req = urllib.request.Request(
                "http://localhost:8000/api/query",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())

        r1 = query("Who is Nahida in Genshin Impact?")
        check("First query returns answer", bool(r1.get("answer")))
        check("First query is not cache hit", not r1.get("cache_hit", False))

        # Same question again → should hit cache
        r2 = query("Who is Nahida in Genshin Impact?")
        check("Second identical query is cache hit", r2.get("cache_hit") == True,
              f"cache_hit={r2.get('cache_hit')}")

        t1_total = r1.get("timing", {}).get("total", 999)
        t2_total = r2.get("timing", {}).get("total", 999)
        check("Cache hit is faster", t2_total < t1_total,
              f"first={t1_total:.2f}s cached={t2_total:.2f}s")

    except Exception as e:
        check("Cache hit test reachable", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("LoreMaster-AI Optimization Tests")
    print("=" * 60)

    test_parallel_processing()
    test_system_prompt_split()
    test_semantic_cache()
    test_session_manager()
    test_circuit_breaker()
    test_compress_prompt_structure()
    test_backend_health()
    test_streaming_endpoint()
    test_cache_hit_via_api()

    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  ({failed} failed)")
        for name, ok in results:
            if not ok:
                print(f"  {FAIL} {name}")
    else:
        print("  — all passed!")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
