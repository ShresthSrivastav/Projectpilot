"""Chat Engine - pre-fetches project data and injects into prompt so the model just answers naturally."""

import json
import logging
import re

from database import chroma_db, memory_store
from services.llm_service import call_model

logger = logging.getLogger(__name__)

CHAT_MODEL = "local"

# In-memory store for pending confirmations per conversation
_pending_actions: dict[str, dict] = {}
_last_project_id: dict[str, str] = {}

CONFIRM_WORDS = {"yes", "proceed", "sure", "yeah", "yep", "ok", "okay", "confirm", "yea"}
CANCEL_WORDS = {"no", "cancel", "stop", "don't", "nah", "nope", "never mind"}

PROJECT_KEYWORDS = [
    "project",
    "app",
    "booking",
    "train",
    "railway",
    "library",
    "todo",
    "blog",
    "ecommerce",
    "chat",
    "inventory",
    "student",
    "employee",
    "crud",
    "api",
    "rest",
    "dashboard",
    "manage",
]


def _find_project(query: str, workspace_id: str = "") -> list[dict]:
    """Search projects by name or prompt text matching."""
    q = query.lower().strip()
    words = [w for w in re.sub(r"[^a-z0-9\s]", " ", q).split() if len(w) > 2]
    jobs = chroma_db.list_jobs(workspace_id=workspace_id, limit=50)
    scored = []
    for j in jobs:
        name = (j.get("project_name") or "").lower()
        prompt = (j.get("prompt") or "").lower()
        combined = f"{name} {prompt}"
        # Exact match gets highest priority
        if q in combined:
            scored.append((10, j))
        elif q in name:
            scored.append((9, j))
        elif q in prompt:
            scored.append((8, j))
        else:
            # Count how many words match
            match_count = sum(1 for w in words if w in combined)
            if match_count >= 2:
                scored.append((5 + match_count, j))
            elif match_count == 1:
                scored.append((2, j))
    # Sort by score descending, take top matches
    scored.sort(key=lambda x: -x[0])
    return [j for _, j in scored[:5]]


def _get_project_context(job) -> str:
    """Build a rich text context for a project."""
    jid = job.get("job_id", "")
    lines = []
    lines.append(f"Project ID: {jid}")
    lines.append(f"Name: {job.get('project_name', '?')}")
    lines.append(f"Status: {job.get('status', '?')}")
    lines.append(f"Prompt: {(job.get('prompt') or '')[:200]}")
    lines.append(f"Files: {job.get('file_count', 0)}")
    lines.append(
        f"Tests: {job.get('test_total', 0)} total, "
        f"{job.get('test_passed', 0)} passed, "
        f"{job.get('test_failed', 0)} failed, "
        f"{job.get('test_skipped', 0)} skipped"
    )
    ts = job.get("test_summary", "")
    if ts:
        lines.append(f"Test summary: {ts[:300]}")
    td = job.get("test_details", "")
    if td:
        lines.append(f"Test details: {td[:500]}")
    try:
        memory_store.read_file if hasattr(memory_store, "read_file") else None
    except Exception:
        pass
    try:
        from services.file_service import read_file as rf

        try:
            cl = rf(jid, "CHANGELOG.md")
            if cl:
                lines.append(f"Changelog:\n{cl[:1000]}")
        except Exception:
            pass
        try:
            rf(jid, "")
        except Exception:
            pass
    except Exception:
        pass
    # analytics
    try:
        all_ana = memory_store.get_project_analytics(limit=100)
        match = next((a for a in all_ana if a.get("job_id") == jid), {})
        if match:
            lines.append(f"Model: {match.get('model_used', '?')}")
            lines.append(f"Tokens used: {match.get('token_usage', 0)}")
            lines.append(f"Duration: {match.get('total_duration_ms', 0)}ms")
    except Exception:
        pass
    return "\n".join(lines)


SYSTEM_PROMPT = """You are ProjectPilot Assistant, a helpful chatbot for the ProjectPilot project generator.
You help users understand their generated projects, answer questions, and perform actions.

GUIDELINES:
- Answer concisely and accurately based on the project data provided below.
- If the user asks about something not in the data, say you don't have that information.
- For actions like fixing tests, iterating, or previewing, ask the user to confirm first.
- Never make up data about projects. Only use what's provided.
"""


def process_message(message: str, conversation_id: str, context: dict = None, workspace_id: str = "") -> dict:
    """Process a user message by pre-fetching project data and calling the LLM."""

    memory_store.add_chat_message(conversation_id, "user", message)
    msg_lower = message.strip().lower()

    # Check if this is a confirmation or cancellation of a pending action
    if conversation_id in _pending_actions:
        first_word = msg_lower.split()[0] if msg_lower.split() else ""
        if (
            msg_lower in CONFIRM_WORDS
            or msg_lower.startswith("yes ")
            or msg_lower == "y"
            or first_word in {"yes", "yeah", "sure", "ok", "okay", "yep", "proceed", "do"}
        ):
            pending = _pending_actions.pop(conversation_id)
            return execute_confirmed_action(conversation_id, pending["tool"], pending["args"])
        elif (
            msg_lower in CANCEL_WORDS
            or msg_lower.startswith("no ")
            or msg_lower == "n"
            or first_word in {"no", "nah", "nope", "cancel", "stop"}
        ):
            _pending_actions.pop(conversation_id, None)
            reply = "Action cancelled."
            memory_store.add_chat_message(conversation_id, "assistant", reply)
            return {"reply": reply, "conversation_id": conversation_id}
        # Non-confirm/cancel response while action is pending - let it fall through

    # Check for action keywords
    action = _detect_action(message, conversation_id, workspace_id=workspace_id)
    if action:
        return _handle_action(conversation_id, action, message)

    # Find matching projects
    projects = _find_project(message, workspace_id=workspace_id)
    context_parts = []

    if projects:
        _last_project_id[conversation_id] = projects[0].get("job_id", "")
        context_parts.append(f"Found {len(projects)} matching project(s):\n")
        for i, p in enumerate(projects, 1):
            ctx = _get_project_context(p)
            context_parts.append(f"--- Project {i} ---\n{ctx}\n")
    else:
        context_parts.append("No matching projects found in the database.")

    try:
        summary = memory_store.get_analytics_summary()
        context_parts.append(
            f"Overall stats: {summary.get('total_projects', 0)} projects, "
            f"{summary.get('total_tokens', 0)} tokens used, "
            f"{summary.get('total_files', 0)} files generated, "
            f"{summary.get('total_tests', 0)} tests written."
        )
    except Exception:
        pass

    full_context = "\n\n".join(context_parts)
    user_prompt = f"""Project Data Context:
{full_context}

User Question: {message}

Answer the user's question based on the project data above. Be concise and helpful."""

    raw = call_model(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        model=CHAT_MODEL,
    )

    reply = (raw or "Sorry, I couldn't process that.").strip()
    memory_store.add_chat_message(conversation_id, "assistant", reply)
    return {"reply": reply, "conversation_id": conversation_id}


def execute_confirmed_action(conversation_id: str, tool_name: str, args: dict) -> dict:
    """Execute a confirmed action."""
    memory_store.add_chat_message(conversation_id, "assistant", f"Executing {tool_name}...")
    try:
        result = _run_action(tool_name, args)
        reply = result.get("message", json.dumps(result))
        memory_store.add_chat_message(conversation_id, "assistant", reply)
        return {"reply": reply, "conversation_id": conversation_id}
    except Exception as exc:
        err = f"Action failed: {exc}"
        logger.error("Action %s failed: %s", tool_name, exc)
        memory_store.add_chat_message(conversation_id, "assistant", err)
        return {"reply": err, "conversation_id": conversation_id}


def _detect_action(message: str, conversation_id: str = "", workspace_id: str = "") -> dict:
    """Detect if user wants to perform an action."""
    m = message.lower()
    jid = _extract_job_id(message, conversation_id, workspace_id=workspace_id)

    # Check for fix tests - even without a matched project, try harder
    fix_keywords = [
        "fix test",
        "fix failing",
        "fix-test",
        "failing test",
        "test fail",
        "fix the test",
        "fix my test",
        "fix this test",
        "fix all test",
        "repair test",
        "correct test",
    ]
    if any(x in m for x in fix_keywords):
        if not jid:
            # Try finding any project with failed tests
            jobs = chroma_db.list_jobs(workspace_id=workspace_id, limit=50)
            for j in jobs:
                if j.get("test_failed", 0) and j.get("test_failed", 0) > 0:
                    jid = j.get("job_id", "")
                    break
            if not jid and jobs:
                jid = jobs[0].get("job_id", "")
        if jid:
            return {"tool": "fix_tests", "args": {"job_id": jid}, "confirm": True}

    if not jid:
        return None

    if any(x in m for x in ["iterate", "modify", "update", "add feature", "change", "add "]):
        instructions = _extract_instructions(m, ["iterate", "modify", "update", "add feature", "change", "add"])
        return {"tool": "iterate_project", "args": {"job_id": jid, "instructions": instructions}, "confirm": True}
    if any(x in m for x in ["run test", "run pytest", "execute test", "run the test"]):
        return {"tool": "run_tests", "args": {"job_id": jid}, "confirm": True}

    if any(x in m for x in ["validate", "check project", "check my project", "verify"]):
        return {"tool": "validate_project", "args": {"job_id": jid}, "confirm": True}
    if any(x in m for x in ["regenerate", "rewrite file", "recreate file"]):
        fp = _extract_file_path(m)
        note = _extract_correction_note(m)
        return {
            "tool": "regenerate_file",
            "args": {"job_id": jid, "file_path": fp or "backend/main.py", "correction_note": note},
            "confirm": True,
        }
    return None


def _extract_job_id(message: str, conversation_id: str = "", workspace_id: str = "") -> str:
    """Try to find a job_id from the message or match a project name."""
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", message.lower())
    if m:
        _last_project_id[conversation_id] = m.group(0)
        return m.group(0)
    msg_lower = message.lower()
    # Check if message is short (likely referring to last discussed project)
    words = msg_lower.split()
    is_short_ref = len(words) <= 3 and any(w in {"it", "this", "that", "the", "my", "project"} for w in words)
    if is_short_ref and conversation_id and conversation_id in _last_project_id:
        return _last_project_id.get(conversation_id, "")

    q_words = [w for w in re.sub(r"[^a-z0-9\s]", " ", msg_lower).split() if len(w) > 2]
    jobs = chroma_db.list_jobs(workspace_id=workspace_id, limit=50)
    best = ("", 0)
    for j in jobs:
        name = (j.get("project_name") or "").lower()
        prompt = (j.get("prompt") or "").lower()
        combined = f"{name} {prompt}"
        score = 0
        if msg_lower in combined:
            score = 20
        elif msg_lower in name:
            score = 18
        elif msg_lower in prompt:
            score = 15
        else:
            match_count = sum(1 for w in q_words if w in combined)
            score = match_count * 3
        if score > best[1]:
            best = (j.get("job_id", ""), score)
    return best[0]


def _extract_instructions(msg: str, keywords: list[str]) -> str:
    """Extract instructions after a keyword."""
    for kw in keywords:
        idx = msg.find(kw)
        if idx >= 0:
            after = msg[idx + len(kw) :].strip()
            if after:
                return after
    return msg[:200]


def _extract_file_path(msg: str) -> str:
    m = re.search(r"file\s+([\w/.]+)", msg)
    return m.group(1) if m else ""


def _extract_correction_note(msg: str) -> str:
    m = re.search(r"(?:to|with|note)\s*[:\s]+(.+)", msg)
    return m.group(1) if m else ""


def _handle_action(conversation_id: str, action: dict, message: str) -> dict:
    """Handle an action request - first ask for confirmation."""
    tool_name = action["tool"]
    args = action["args"]
    jid = args.get("job_id", "")
    if jid:
        _last_project_id[conversation_id] = jid
    job = chroma_db.get_job(jid) if jid else None
    project_name = job.get("project_name", jid[:8]) if job else jid[:8]

    # Store the pending action (also used for typed "yes" confirmations)
    _pending_actions[conversation_id] = {"tool": tool_name, "args": args}

    reply = f"I can run `{tool_name}` on project **{project_name}**. Type **yes** to proceed or **no** to cancel."
    memory_store.add_chat_message(conversation_id, "assistant", reply)
    return {
        "reply": reply,
        "conversation_id": conversation_id,
        "pending_confirm": {"tool_name": tool_name, "args": args},
    }


def _run_action(tool_name: str, args: dict) -> dict:
    """Execute an action tool."""
    import httpx

    if tool_name == "fix_tests":
        jid = args.get("job_id", "")
        resp = httpx.post(f"http://localhost:5000/fix-tests/{jid}", timeout=300)
        resp.raise_for_status()
        data = resp.json()
        return {"message": data.get("message", "Tests fixed.")}

    if tool_name == "iterate_project":
        jid = args.get("job_id", "")
        instructions = args.get("instructions", "")
        resp = httpx.post(f"http://localhost:5000/iterate/{jid}", json={"instructions": instructions}, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        return {"message": f"Iteration done. {data.get('test_summary', 'N/A')}"}

    if tool_name == "run_tests":
        from services.test_service import run_pytest

        result = run_pytest(args.get("job_id", ""))
        return {"message": f"Tests: {result.get('passed', 0)} passed, {result.get('failures', 0)} failed"}

    if tool_name == "validate_project":
        jid = args.get("job_id", "")
        resp = httpx.get(f"http://localhost:5000/validate/{jid}", timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return {"message": data.get("summary", "Validation complete.")}

    if tool_name == "regenerate_file":
        jid = args.get("job_id", "")
        fp = args.get("file_path", "backend/main.py")
        note = args.get("correction_note", "")
        resp = httpx.post(
            "http://localhost:5000/regenerate-file",
            json={"job_id": jid, "file_path": fp, "correction_note": note},
            timeout=120,
        )
        resp.raise_for_status()
        return {"message": f"File {fp} regenerated."}

    return {"message": f"Unknown action: {tool_name}"}
