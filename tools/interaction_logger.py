# interaction_logger.py
# Captures every Jarvis interaction as training data for future LoRA fine-tuning.
#
# Design constraints (these are why the code looks the way it does):
#   1. NEVER add latency to the user-facing response. log_turn() does a
#      queue.put_nowait() and returns; a daemon thread does all file I/O.
#   2. NEVER raise into the caller. Every public function swallows exceptions.
#   3. Works from both the async server and the sync CLI, so the mechanism is
#      a plain thread + queue rather than asyncio.
#
# Storage layout (append-only, never rewritten):
#   training_data/turns/YYYY-MM-DD.jsonl      one record per turn, immutable
#   training_data/feedback/YYYY-MM-DD.jsonl   {turn_id, label, ...} events
#
# Feedback lives in a separate file because corrections arrive one or more
# turns AFTER the turn they judge. Rewriting a JSONL line in place would mean
# read-modify-write on the hot path — slow, and corruptible on crash. The two
# files get joined at training time instead.

import atexit
import datetime
import json
import queue
import re
import threading
import uuid

from tools import paths

TRAINING_DATA = paths.TRAINING_DATA   # JARVIS_TRAINING_DATA overrides
TURNS_DIR     = TRAINING_DATA / "turns"
FEEDBACK_DIR  = TRAINING_DATA / "feedback"

# How long the writer waits for new records before flushing what it has.
_FLUSH_INTERVAL = 2.0

# How many recent turns we keep in memory for retro-labelling corrections.
_RECENT_TURNS_MAX = 20


# ── Feedback signal detection ─────────────────────────────────────────────────
# Deterministic regex, not an LLM call — this runs on every turn and must be
# free. Patterns are anchored to the start of the message to avoid false
# positives like "what's wrong with this code" matching a correction.

_CORRECTION_PATTERNS = [
    r"^no[,.\s]+i\s+meant\b",
    r"^i\s+meant\b",
    r"^no[,.\s]+not\b",
    r"^not\s+that\b",
    r"^that'?s\s+(wrong|not\s+right|not\s+what)\b",
    r"^that\s+is\s+(wrong|not\s+right)\b",
    r"^wrong\b",
    r"^incorrect\b",
    r"^no[,.\s]+that'?s\s+not\b",
    r"^try\s+again\b",
    r"^that'?s\s+not\s+what\s+i\b",
]

_POSITIVE_PATTERNS = [
    # Only a bare "remember this/that" is praise for the previous turn.
    # "remember that my printer is X" is a memory command, not feedback, so
    # this pattern has to match the whole message.
    r"^remember\s+(this|that)\s*[.!]*$",
    r"^perfect\b",
    r"^that'?s\s+(right|correct|it)\b",
    r"^exactly\b",
    r"^nice[,.\s!]*(that\s+worked)?\b",
    r"^(thanks|thank\s+you)[,.\s!]*(that\s+worked)?\b",
    r"^(that\s+)?worked\b",
]

_CORRECTION_RE = re.compile("|".join(_CORRECTION_PATTERNS), re.IGNORECASE)
_POSITIVE_RE   = re.compile("|".join(_POSITIVE_PATTERNS), re.IGNORECASE)

# Brain outputs that are self-labelling failures — free negative examples.
_SELF_LABELLED_NEGATIVE = {"clarify", "unknown"}


def classify_feedback(message: str) -> str | None:
    """Return 'negative', 'positive', or None for a user message.

    Only judges the message as a reaction to the PREVIOUS turn.
    """
    text = (message or "").strip()
    if not text:
        return None
    if _CORRECTION_RE.search(text):
        return "negative"
    if _POSITIVE_RE.search(text):
        return "positive"
    return None


# ── Writer thread ─────────────────────────────────────────────────────────────

class _Writer:
    """Single daemon thread draining a queue to disk. Owns all file I/O."""

    def __init__(self):
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._thread = None
        self._started = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._started:
                return
            self._thread = threading.Thread(
                target=self._run, name="jarvis-interaction-logger", daemon=True
            )
            self._thread.start()
            self._started = True
            atexit.register(self.flush)

    def put(self, kind: str, record: dict):
        self.start()
        self._q.put_nowait((kind, record))

    def flush(self, timeout: float = 2.0):
        """Block until everything queued so far is on disk.

        Real synchronisation, not a sleep: we push a sentinel carrying an Event
        and wait for the writer to set it after the batch is written. Callers
        that read the files back (the stats command, atexit) need this to be
        exact or they'll report stale counts.
        """
        if not self._started:
            return
        try:
            done = threading.Event()
            self._q.put_nowait(("__flush__", done))
            done.wait(timeout)
        except Exception:
            pass

    def _run(self):
        pending: list[tuple[str, dict]] = []
        while True:
            try:
                waiters: list[threading.Event] = []
                try:
                    item = self._q.get(timeout=_FLUSH_INTERVAL)
                    items = [item]
                    # Opportunistically drain anything else already queued.
                    while True:
                        try:
                            items.append(self._q.get_nowait())
                        except queue.Empty:
                            break
                    for kind, payload in items:
                        if kind == "__flush__":
                            waiters.append(payload)
                        else:
                            pending.append((kind, payload))
                except queue.Empty:
                    pass

                if pending:
                    self._write_batch(pending)
                    pending = []

                # Only released once the batch above is durably written.
                for w in waiters:
                    w.set()
            except Exception:
                # A logging thread must never die. Drop the batch and continue.
                pending = []

    def _write_batch(self, batch: list[tuple[str, dict]]):
        by_path: dict = {}
        for kind, record in batch:
            directory = TURNS_DIR if kind == "turn" else FEEDBACK_DIR
            day = record.get("ts", "")[:10] or _today()
            by_path.setdefault(directory / f"{day}.jsonl", []).append(record)

        for path, records in by_path.items():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                # Serialise each record on its own. default=str keeps odd values
                # (Path, datetime, arbitrary objects) from being fatal, and the
                # per-record guard stops one bad record dropping its batch-mates.
                lines = []
                for r in records:
                    try:
                        lines.append(json.dumps(r, ensure_ascii=False, default=str))
                    except Exception:
                        continue
                if not lines:
                    continue
                with path.open("a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            except Exception:
                pass


_WRITER = _Writer()


# ── Conversation tracking ─────────────────────────────────────────────────────
# Retro-labelling needs to know which turn a correction refers to, so we keep a
# small in-memory ring of recent turns per conversation.

_recent: dict[str, list[dict]] = {}
_recent_lock = threading.Lock()


def _today() -> str:
    return datetime.date.today().isoformat()


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def new_conversation() -> str:
    """Mint a conversation id. Callers that don't track one can pass None instead."""
    return str(uuid.uuid4())


# ── Public API ────────────────────────────────────────────────────────────────

def log_turn(
    user_message: str,
    brain_response: dict,
    agent_result,
    source: str = "web",
    conversation_id: str | None = None,
    latency_ms: int | None = None,
) -> str | None:
    """Record one interaction. Returns the turn_id, or None if logging failed.

    Fire-and-forget: this does no file I/O and never raises.
    """
    try:
        turn_id = str(uuid.uuid4())
        convo   = conversation_id or "default"
        ts      = _now()

        brain_response = brain_response or {}
        action = brain_response.get("action", "unknown")

        with _recent_lock:
            history = _recent.setdefault(convo, [])
            turn_index = len(history)

            # Does this message correct or praise the previous turn?
            label = classify_feedback(user_message)
            if label and history:
                prev = history[-1]
                _WRITER.put("feedback", {
                    "turn_id": prev["turn_id"],
                    "label": label,
                    "source": "implicit_user_reply",
                    "evidence": (user_message or "")[:200],
                    "ts": ts,
                })

            history.append({"turn_id": turn_id, "action": action})
            if len(history) > _RECENT_TURNS_MAX:
                history.pop(0)

        record = {
            "turn_id": turn_id,
            "conversation_id": convo,
            "turn_index": turn_index,
            "ts": ts,
            "source": source,
            "user_message": user_message,
            "brain": {
                "action": action,
                "agent": brain_response.get("agent", ""),
                "params": brain_response.get("params", {}),
                "reply": brain_response.get("reply", ""),
            },
            "agent_result": agent_result if isinstance(agent_result, str) else str(agent_result),
            "latency_ms": latency_ms,
        }
        _WRITER.put("turn", record)

        # The brain telling us it failed is a free negative label.
        if action in _SELF_LABELLED_NEGATIVE:
            _WRITER.put("feedback", {
                "turn_id": turn_id,
                "label": "negative",
                "source": f"brain_{action}",
                "evidence": "",
                "ts": ts,
            })

        return turn_id
    except Exception:
        return None


def log_feedback(turn_id: str, label: str, source: str = "explicit", evidence: str = ""):
    """Attach an explicit label to an already-logged turn. Never raises."""
    try:
        _WRITER.put("feedback", {
            "turn_id": turn_id,
            "label": label,
            "source": source,
            "evidence": evidence[:200],
            "ts": _now(),
        })
    except Exception:
        pass


def flush(timeout: float = 2.0):
    """Force a write of anything queued. Used by the stats command."""
    try:
        _WRITER.flush(timeout)
    except Exception:
        pass
