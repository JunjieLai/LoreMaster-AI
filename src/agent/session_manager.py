"""
LoreMaster-AI - Session Manager

Maintains per-session conversation history to support:
- Multi-turn dialogue (follow-up questions, pronoun coreference)
- Accumulated entity tracking across turns
- Automatic background compression when history grows too long

Improvements from reading Claude Code source:
1. NO_TOOLS_PREAMBLE (prompt.ts): prevent Haiku calling tools during compression
2. <analysis> draft block (prompt.ts): Haiku reasons first, then outputs JSON → better quality
3. TURNS_CAP=50 (types.ts TEAMMATE_MESSAGES_UI_CAP): prevents memory bloat in long sessions
4. Dual-threshold compression (autoCompact.ts): char count + turn count, not turns alone
5. Background compression (sessionMemory.ts): runs in daemon thread, never blocks the request
6. _compress_lock (autoCompact.ts sequential guard): prevents concurrent double-compression
"""

import logging
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
import anthropic

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from config.settings import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
SESSION_TTL = 3600          # 1 hour idle expiry
MAX_HISTORY_CHARS = 2000    # Hard cap on injected history string

# Improvement 3 (Claude Code types.ts TEAMMATE_MESSAGES_UI_CAP = 50)
# ~20MB RSS per agent at 500+ turns; full history irrelevant once compressed.
TURNS_CAP = 50

# Improvement 4 (Claude Code autoCompact.ts dual-threshold)
# Compress when BOTH: turns >= MIN_TURNS AND accumulated chars >= CHAR_THRESHOLD
COMPRESS_MIN_TURNS = 8
COMPRESS_CHAR_THRESHOLD = 6000   # ~1500 tokens at ~4 chars/token
KEEP_RECENT_TURNS = 2            # Always keep this many full turns after compress

HAIKU_MODEL = "claude-3-haiku-20240307"

# Pronoun patterns for coreference resolution
COREFERENCE_PATTERNS = re.compile(
    r"\b(he|she|they|it|him|her|them|this|that|those|these|the same|their|his|hers)\b",
    re.IGNORECASE,
)

# Improvement 1 (Claude Code prompt.ts NO_TOOLS_PREAMBLE)
# Without this, Haiku sometimes tries to call tools, wasting the turn.
_NO_TOOLS_PREAMBLE = (
    "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools. "
    "Tool calls will be REJECTED and will waste your only turn. "
    "Your entire response must be: <analysis> block then <summary> block."
)

# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Turn:
    question: str
    answer: str
    entities: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    # Metadata for history display (optional — older turns without these fields still work)
    sources: List[dict] = field(default_factory=list)
    path: Optional[dict] = None
    graph_results: List[dict] = field(default_factory=list)
    query_type: str = "FACTUAL"


@dataclass
class Session:
    session_id: str
    turns: List[Turn] = field(default_factory=list)
    accumulated_entities: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    _compress_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def total_history_chars(self) -> int:
        return sum(len(t.question) + len(t.answer) for t in self.turns)


# ── SessionManager ────────────────────────────────────────────────────────────

class SessionManager:
    """In-memory session store. Thread-safe via GIL + per-session compress lock."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── Public API ────────────────────────────────────────────────────────

    def get_or_create(self, session_id: Optional[str]) -> Session:
        """Return existing session or create a new one."""
        self._cleanup_expired()
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_activity = time.time()
            return session
        new_id = session_id or str(uuid.uuid4())
        session = Session(session_id=new_id)
        self._sessions[new_id] = session
        return session

    def add_turn(
        self,
        session: Session,
        question: str,
        answer: str,
        entities: List[str],
        sources: Optional[List[dict]] = None,
        path: Optional[dict] = None,
        graph_results: Optional[List[dict]] = None,
        query_type: str = "FACTUAL",
    ):
        """
        Append a completed turn.

        Improvement 3: cap turns at TURNS_CAP (oldest dropped).
        Improvement 4: trigger compression only when BOTH thresholds exceeded.
        Improvement 5: compression runs in a daemon background thread.
        """
        session.turns.append(Turn(
            question=question,
            answer=answer,
            entities=entities,
            sources=sources or [],
            path=path,
            graph_results=graph_results or [],
            query_type=query_type,
        ))
        session.last_activity = time.time()

        # Update entity list (dedup, cap at 30)
        for e in entities:
            if e not in session.accumulated_entities:
                session.accumulated_entities.append(e)
        session.accumulated_entities = session.accumulated_entities[-30:]

        # Improvement 3: hard cap on turns list (like TEAMMATE_MESSAGES_UI_CAP)
        if len(session.turns) > TURNS_CAP:
            session.turns = session.turns[-TURNS_CAP:]

        # Improvement 4: dual-threshold — only compress when both conditions met
        needs_compress = (
            len(session.turns) >= COMPRESS_MIN_TURNS
            and session.total_history_chars() >= COMPRESS_CHAR_THRESHOLD
        )
        if needs_compress:
            # Improvement 5: background thread, non-blocking
            t = threading.Thread(
                target=self._compress_bg,
                args=(session,),
                daemon=True,
                name=f"compress-{session.session_id[:8]}",
            )
            t.start()

    def get_history_context(self, session: Session) -> str:
        """
        Return formatted history string for injection into AnswerGenerator.
        Includes compressed summary (if any) + recent full turns.
        """
        parts = []

        if session.summary:
            parts.append(f"[Summary of earlier conversation]\n{session.summary}")

        for turn in session.turns[-KEEP_RECENT_TURNS:]:
            preview = turn.answer[:300].rstrip()
            if len(turn.answer) > 300:
                preview += "..."
            parts.append(f"[User]: {turn.question}\n[LoreMaster]: {preview}")

        history = "\n\n".join(parts)
        if len(history) > MAX_HISTORY_CHARS:
            history = history[-MAX_HISTORY_CHARS:]
        return history

    def resolve_coreferences(self, query: str, session: Session) -> str:
        """Prepend last entity if query uses pronouns with no explicit entity mention."""
        if not session.turns:
            return query
        if not COREFERENCE_PATTERNS.search(query):
            return query

        last_entities = session.turns[-1].entities
        if not last_entities:
            return query

        has_entity = any(
            e.lower() in query.lower() for e in session.accumulated_entities[-5:]
        )
        if not has_entity:
            resolved = f"[Referring to {last_entities[0]}] {query}"
            logger.debug("Coreference: '%s' → '%s'", query, resolved)
            return resolved
        return query

    # ── Private ───────────────────────────────────────────────────────────

    def _compress_bg(self, session: Session):
        """
        Improvement 5+6: background compression with lock guard.
        Lock prevents concurrent double-compression (autoCompact.ts sequential guard).
        """
        if not session._compress_lock.acquire(blocking=False):
            logger.debug("Session '%s': compression already in progress, skipping", session.session_id)
            return
        try:
            self._compress(session)
        finally:
            session._compress_lock.release()

    def _compress(self, session: Session):
        """
        Summarize all but the most recent KEEP_RECENT_TURNS turns into a structured summary.

        Improvements applied:
        1. _NO_TOOLS_PREAMBLE: prevent Haiku calling tools
        2. <analysis> draft block: Haiku reasons before outputting JSON → better summaries
        """
        turns_to_compress = session.turns[:-KEEP_RECENT_TURNS]
        if not turns_to_compress:
            return

        conversation_text = "\n\n".join(
            f"User: {t.question}\nAssistant: {t.answer[:400]}"
            for t in turns_to_compress
        )

        # Improvement 1: NO_TOOLS_PREAMBLE at top of prompt
        # Improvement 2: <analysis> draft → <summary> JSON pattern from prompt.ts
        prompt = f"""{_NO_TOOLS_PREAMBLE}

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

        try:
            response = self._anthropic.messages.create(
                model=HAIKU_MODEL,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Extract only the <summary> block (strip the <analysis> draft)
            import re as _re
            summary_match = _re.search(r"<summary>(.*?)</summary>", raw, _re.DOTALL)
            if summary_match:
                session.summary = summary_match.group(1).strip()
            else:
                session.summary = raw  # fallback: use full output

            session.turns = session.turns[-KEEP_RECENT_TURNS:]
            logger.info(
                "Session '%s': compressed %d turns into summary (%d chars)",
                session.session_id, len(turns_to_compress), len(session.summary),
            )
        except Exception as e:
            logger.warning("Session compression failed: %s", e)

    def _cleanup_expired(self):
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_activity > SESSION_TTL
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info("SessionManager: evicted %d expired sessions", len(expired))

    def active_count(self) -> int:
        return len(self._sessions)


# Singleton
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
