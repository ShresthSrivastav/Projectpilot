"""ProjectPilot — Streamlit Frontend

New in v4:
  - Clarifying question flow before generation
  - Tech stack selector (backend / frontend / db)
  - Live file tree panel during generation
  - Cancel button for running jobs
  - Regenerate file panel on completed jobs
"""
import os
import time
from typing import Dict, List, Optional

import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
POLL_SEC = 2

st.set_page_config(
    page_title="ProjectPilot",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.agent-pill {
    display:inline-block; padding:2px 10px; border-radius:12px;
    font-size:0.78rem; font-weight:600; margin:2px;
}
.pill-done   { background:#1e3a2f; color:#4ade80; }
.pill-active { background:#1e2d45; color:#60a5fa; border:1px solid #3b82f6; }
.pill-wait   { background:#1e1e1e; color:#6b7280; }
.log-INFO    { color:#93c5fd; }
.log-WARNING { color:#fcd34d; }
.log-ERROR   { color:#f87171; }
.log-DEBUG   { color:#a78bfa; }
.log-line    { font-family:monospace; font-size:0.8rem; margin:1px 0; }
.status-badge-complete  { color:#4ade80; font-weight:700; }
.status-badge-running   { color:#60a5fa; font-weight:700; }
.status-badge-failed    { color:#f87171; font-weight:700; }
.status-badge-queued    { color:#fcd34d; font-weight:700; }
.status-badge-cancelled { color:#9ca3af; font-weight:700; }
</style>
""", unsafe_allow_html=True)

#  Session defaults 
for k, v in {
    "job_id": None, "polling": False,
    "selected_model": "local", "last_job_name": "",
    "clarify_question": None, "clarify_answered": False,
    "clarify_answer": "",
    "wizard_data": {},
    "chat_messages": [],
    "chat_conversation_id": None,
    "chat_loading": False,
    "chat_pending_confirm": None,
    "chat_conversations": [],
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


PROJECT_TYPE_DEFAULTS = {
    "Web API (backend only)": {
        "backend": "fastapi",
        "frontend": "none",
        "db": "sqlite",
        "orm": "sqlalchemy",
        "auth": "none",
        "testing": "pytest",
        "css": "none",
        "deploy": "docker",
    },
    "Full-stack Web App": {
        "backend": "fastapi",
        "frontend": "react",
        "db": "sqlite",
        "orm": "sqlalchemy",
        "auth": "jwt",
        "testing": "pytest",
        "css": "bootstrap",
        "deploy": "docker",
    },
    "CLI Tool": {
        "backend": "none",
        "frontend": "none",
        "db": "none",
        "orm": "none",
        "auth": "none",
        "testing": "pytest",
        "css": "none",
        "deploy": "none",
    },
    "Data Pipeline / ETL": {
        "backend": "fastapi",
        "frontend": "none",
        "db": "postgresql",
        "orm": "sqlalchemy",
        "auth": "none",
        "testing": "pytest",
        "css": "none",
        "deploy": "docker",
    },
    "Automation Script": {
        "backend": "none",
        "frontend": "none",
        "db": "none",
        "orm": "none",
        "auth": "none",
        "testing": "pytest",
        "css": "none",
        "deploy": "none",
    },
    "Library / SDK": {
        "backend": "none",
        "frontend": "none",
        "db": "none",
        "orm": "none",
        "auth": "none",
        "testing": "pytest",
        "css": "none",
        "deploy": "none",
    },
}


def _sync_project_defaults(project_type: str) -> Dict[str, str]:
    current = dict(st.session_state.wizard_data)
    defaults = PROJECT_TYPE_DEFAULTS.get(project_type, PROJECT_TYPE_DEFAULTS["Web API (backend only)"])
    current["project_type"] = project_type
    for key, value in defaults.items():
        current.setdefault(key, value)
    if project_type in {"CLI Tool", "Automation Script", "Library / SDK"}:
        current["frontend"] = "none"
        current["db"] = "none"
        current["orm"] = "none"
        current["auth"] = "none"
        current["css"] = "none"
    st.session_state.wizard_data = current
    return current


#  API helpers 
def _get(path: str, timeout: int = 8) -> Optional[Dict]:
    try:
        r = requests.get(f"{BACKEND}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _post(path: str, payload: Dict, timeout: int = 60) -> Optional[Dict]:
    try:
        r = requests.post(f"{BACKEND}{path}", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        st.error(f" {detail}")
        return None
    except requests.ConnectionError:
        st.error(f" Cannot reach backend at `{BACKEND}`")
        return None


def _download(job_id: str) -> Optional[bytes]:
    try:
        r = requests.get(f"{BACKEND}/download/{job_id}", timeout=30)
        r.raise_for_status()
        return r.content
    except Exception as exc:
        st.error(f" Download failed: {exc}")
        return None


def _delete_chat_conv(conversation_id):
    try:
        import requests as _req
        r = _req.delete(f"{BACKEND}/chat/conversations/{conversation_id}", timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None





#  Sidebar 
MODELS = {
    "local":    (" Gemma 4 12B", "gemma4:12b",     "Gemma 4 12B (local)",                        "local"),
    "cloud":    (" Gemma 4 31B", "gemma-4-31b-it", "Google Gemma 4 31B via Google AI (cloud)", "cloud"),
}

with st.sidebar:
    st.markdown("##  ProjectPilot")
    st.caption("Multi-agent project generator")
    st.divider()

    health = _get("/health")

    #  Model selector 
    st.markdown("**Model**")

    providers = (health or {}).get("providers", [])
    prov_avail = {p["name"]: p["available"] for p in providers}
    prov_model  = {p["name"]: p.get("model", "") for p in providers}

    sections = [
        ("Local", ["local"]),
        ("Cloud (Google AI)", ["cloud"]),
    ]

    for section_label, keys in sections:
        st.caption(f" {section_label}")
        for key in keys:
            if key not in MODELS:
                continue
            label, tag, desc, _ = MODELS[key]
            tag = prov_model.get(key, tag)
            available = prov_avail.get(key, False)
            disabled = key != "local" and not available
            if st.button(
                f"{label}  `{tag}`",
                key=f"model_{key}",
                use_container_width=True,
                type="primary" if st.session_state.selected_model == key else "secondary",
                disabled=disabled,
            ):
                st.session_state.selected_model = key
                st.rerun()
            st.caption(desc)

    st.divider()
    with st.expander("Tech Stack", expanded=False):
        st.caption("Configured from the Generate form.")
        wd = st.session_state.get("wizard_data", {})
        if wd:
            st.json({
                "Backend": wd.get("backend", "—"),
                "Frontend": wd.get("frontend", "—"),
                "Database": wd.get("db", "—"),
                "Auth": wd.get("auth", "—"),
                "Testing": wd.get("testing", "—"),
                "CSS": wd.get("css", "—"),
                "ORM": wd.get("orm", "—"),
                "Deploy": wd.get("deploy", "—"),
            })
        else:
            st.caption("No wizard data yet — start a generation to configure.")

    st.divider()
    if health:
        ollama_ok = health.get("ollama_online", False)
        st.markdown(f"**Ollama:** {'🟢 Online' if ollama_ok else ' Offline'}")
        if health.get("models_ready"):
            st.caption(" Local models ready")
        else:
            for m, s in (health.get("pull_status") or {}).items():
                st.caption(f"`{m}`: {s}")
    else:
        st.warning(" Backend unreachable")

    st.divider()
    st.caption(
        "Student mgmt · Inventory · Blog · Task manager · "
        "Employee mgmt · CRUD dashboards · REST APIs"
    )
    st.divider()
    st.caption("Ollama · ChromaDB · FastAPI · Streamlit · Docker")

    #  AI Chatbot 
    st.divider()
    st.markdown("###  AI Chatbot")
    st.caption("Ask about projects or run actions.")

    # Load conversations on first render
    if not st.session_state.get("_chat_loaded"):
        convos = _get("/chat/conversations")
        if convos and convos.get("conversations"):
            st.session_state.chat_conversations = convos["conversations"]
        st.session_state["_chat_loaded"] = True

    col1, col2 = st.columns([3, 1])
    with col1:
        conv_titles = {c["id"]: c["title"] for c in st.session_state.chat_conversations}
        conv_ids = list(conv_titles.keys())
        if conv_ids:
            current_id = st.session_state.chat_conversation_id
            if current_id and current_id not in conv_ids:
                current_id = conv_ids[0]
                st.session_state.chat_conversation_id = current_id
            sel_idx = conv_ids.index(current_id) if current_id in conv_ids else 0
            selected = st.selectbox(
                "Conversation",
                options=conv_ids,
                format_func=lambda x: conv_titles.get(x, x[:8]),
                index=sel_idx,
                key="chat_conv_sel",
                label_visibility="collapsed",
            )
            if selected != st.session_state.chat_conversation_id:
                st.session_state.chat_conversation_id = selected
                msgs_resp = _get(f"/chat/conversations/{selected}/messages", timeout=8)
                st.session_state.chat_messages = (msgs_resp or {}).get("messages", [])
                st.rerun()
        else:
            st.caption("No conversations yet.")

    with col2:
        if st.button("+ New", use_container_width=True):
            import uuid as _uuid
            new_cid = str(_uuid.uuid4())
            resp = _post("/chat/new", {"conversation_id": new_cid, "title": "New Chat"})
            if resp and resp.get("ok"):
                st.session_state.chat_conversation_id = new_cid
                st.session_state.chat_messages = []
                st.session_state.chat_conversations.insert(0, {
                    "id": new_cid,
                    "title": "New Chat",
                })
                st.rerun()

        if st.session_state.chat_conversation_id:
            del_id = st.session_state.chat_conversation_id
            if st.button(" Del", use_container_width=True):
                resp = _delete_chat_conv(del_id)
                if resp and resp.get("ok"):
                    st.session_state.chat_messages = []
                    st.session_state.chat_conversation_id = None
                    st.session_state.chat_conversations = [
                        c for c in st.session_state.chat_conversations
                        if c["id"] != del_id
                    ]
                    st.rerun()

    # Suggested questions (shown when no messages)
    if not st.session_state.chat_messages:
        st.markdown("**Try asking:**")
        suggestions = [
            "Show my recent projects",
            "Which project has failing tests?",
            "Fix tests for my last project",
            "Summarize the last generated project",
        ]
        for s in suggestions:
            if st.button(s, key=f"sugg_{s[:20]}", use_container_width=True):
                st.session_state.chat_loading = True
                cid = st.session_state.chat_conversation_id
                if not cid:
                    import uuid as _uuid2
                    cid = str(_uuid2.uuid4())
                    _post("/chat/new", {"conversation_id": cid, "title": s[:40]})
                    st.session_state.chat_conversation_id = cid
                    st.session_state.chat_conversations.insert(0, {"id": cid, "title": s[:40]})
                resp = _post("/chat", {"message": s, "conversation_id": cid})
                st.session_state.chat_messages.append({"role": "user", "content": s})
                if resp:
                    st.session_state.chat_messages.append({"role": "assistant", "content": resp.get("reply", "")})
                    st.session_state.chat_pending_confirm = resp.get("pending_confirm")
                else:
                    st.session_state.chat_messages.append({"role": "assistant", "content": "Sorry, something went wrong."})
                st.session_state.chat_loading = False
                st.rerun()

    # Chat messages area
    for msg in st.session_state.chat_messages[-10:]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if st.session_state.chat_pending_confirm:
        with st.chat_message("assistant"):
            pc = st.session_state.chat_pending_confirm
            st.warning(f" Proceed with `{pc['tool_name']}`?")
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button(" Yes, proceed", key="confirm_yes", use_container_width=True):
                    resp = _post("/chat/confirm-action", {
                        "conversation_id": st.session_state.chat_conversation_id,
                        "tool_name": pc["tool_name"],
                        "args": pc["args"],
                    })
                    if resp:
                        st.session_state.chat_messages.append({
                            "role": "assistant",
                            "content": resp.get("reply", "Done."),
                        })
                    st.session_state.chat_pending_confirm = None
                    st.rerun()
            with c2:
                if st.button(" No, cancel", key="confirm_no", use_container_width=True):
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": "Action cancelled.",
                    })
                    st.session_state.chat_pending_confirm = None
                    st.rerun()

    # Chat input
    if st.session_state.chat_loading:
        st.caption("Thinking...")
    user_msg = st.chat_input(
        "Ask about projects or run actions...",
        disabled=st.session_state.chat_loading,
        key="chat_input",
    )
    if user_msg:
        cid = st.session_state.chat_conversation_id
        if not cid:
            resp = _post("/chat", {"message": user_msg, "title": user_msg[:40]})
            if resp and resp.get("conversation_id"):
                cid = resp["conversation_id"]
                st.session_state.chat_conversation_id = cid
                st.session_state.chat_conversations.insert(0, {
                    "id": cid,
                    "title": user_msg[:40],
                })
        else:
            st.session_state.chat_loading = True
            resp = _post("/chat", {"message": user_msg, "conversation_id": cid})

        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        if resp:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": resp.get("reply", ""),
            })
            if resp.get("pending_confirm"):
                st.session_state.chat_pending_confirm = resp["pending_confirm"]
            else:
                st.session_state.chat_pending_confirm = None
        else:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "Sorry, something went wrong.",
            })
        st.session_state.chat_loading = False
        st.rerun()


#  Main tabs 
tab_gen, tab_hist, tab_analytics, tab_workspace, tab_benchmarks, tab_org, tab_eco, tab_eval, tab_info = st.tabs([
    " Generate", " History", " Analytics", " Workspace", " Benchmarks", " Organization", " Ecosystem", " Evaluation", "ℹ How It Works",
])


# 
# TAB 1 — Generate
# 
with tab_gen:
    st.markdown("## Generate a Project")
    project_types = list(PROJECT_TYPE_DEFAULTS.keys())
    current_type = st.session_state.wizard_data.get("project_type", project_types[0])
    wiz = _sync_project_defaults(current_type)

    st.caption("Choose the stack in one place, then describe what you want built below.")

    project_type = st.radio(
        "Project Type",
        project_types,
        index=project_types.index(current_type),
        horizontal=True,
        key="project_type_radio",
        help="This sets sensible defaults that you can still override below.",
    )
    if project_type != current_type:
        st.session_state.wizard_data = dict(PROJECT_TYPE_DEFAULTS[project_type], project_type=project_type)
        st.rerun()

    wiz = st.session_state.wizard_data
    is_web = project_type in {"Web API (backend only)", "Full-stack Web App", "Data Pipeline / ETL"}
    has_frontend = True
    uses_db = project_type not in {"CLI Tool", "Automation Script", "Library / SDK"}

    st.markdown("### Stack Configuration")
    top_left, top_mid, top_right = st.columns(3)
    with top_left:
        backend_options = ["fastapi", "flask", "express", "none"] if is_web else ["none"]
        wiz["backend"] = st.selectbox(
            "Backend",
            backend_options,
            index=backend_options.index(wiz.get("backend", backend_options[0])),
            help="Server framework for APIs and business logic.",
        )
        wiz["auth"] = st.selectbox(
            "Authentication",
            ["none", "jwt", "oauth2", "session", "firebase"],
            index=["none", "jwt", "oauth2", "session", "firebase"].index(wiz.get("auth", "none")),
            disabled=wiz["backend"] == "none",
            help="Keep this off unless the project really needs login flows.",
        )
        wiz["testing"] = st.selectbox(
            "Testing",
            ["pytest", "unittest", "jest", "none"],
            index=["pytest", "unittest", "jest", "none"].index(wiz.get("testing", "pytest")),
        )
    with top_mid:
        frontend_options = ["react", "vue", "angular", "svelte", "html", "streamlit", "none"] if has_frontend else ["none"]
        wiz["frontend"] = st.selectbox(
            "Frontend",
            frontend_options,
            index=frontend_options.index(wiz.get("frontend", frontend_options[0])),
            help="Pick `none` for backend-only work.",
        )
        db_default = wiz.get("db", "sqlite" if uses_db else "none")
        wiz["db"] = st.selectbox(
            "Database",
            ["sqlite", "postgresql", "mysql", "mongodb", "none"] if uses_db else ["none"],
            index=(["sqlite", "postgresql", "mysql", "mongodb", "none"] if uses_db else ["none"]).index(db_default),
            help="SQLite is fastest to start with; PostgreSQL is the safer production default.",
        )
        orm_options = ["sqlalchemy", "prisma", "django-orm", "mongoose", "none"]
        orm_default = "none" if wiz["db"] == "none" else wiz.get("orm", "sqlalchemy")
        wiz["orm"] = st.selectbox(
            "ORM / ODM",
            orm_options,
            index=orm_options.index(orm_default),
            disabled=wiz["db"] == "none",
        )
    with top_right:
        css_options = ["bootstrap", "tailwind", "bulma", "none"] if wiz["frontend"] != "none" else ["none"]
        wiz["css"] = st.selectbox(
            "CSS",
            css_options,
            index=css_options.index(wiz.get("css", css_options[0])),
            disabled=wiz["frontend"] == "none",
        )
        wiz["deploy"] = st.selectbox(
            "Deployment",
            ["docker", "docker-compose", "none"],
            index=["docker", "docker-compose", "none"].index(wiz.get("deploy", "docker")),
        )
        st.markdown("**Current model**")
        sel = st.session_state.selected_model
        model_label, model_tag, _, _ = MODELS[sel]
        st.caption(f"{model_label} · `{model_tag}`")

    st.session_state.wizard_data = wiz

    st.markdown("### Project Brief")
    brief_left, brief_right = st.columns([1.3, 1])
    with brief_left:
        proj_name = st.text_input("Project name", value="My Project", max_chars=80, key="wiz_name")
        prompt = st.text_area(
            "Project description",
            placeholder=(
                "Build a student management system with login, CRUD for students and grades, "
                "a dashboard with key stats, search, and export."
            ),
            height=180,
            max_chars=500,
            key="wiz_prompt",
        )
        char_color = "#dc2626" if len(prompt) > 480 else "#6b7280"
        st.markdown(
            f"<span style='color:{char_color};font-size:0.8rem'>{len(prompt)}/500 characters</span>",
            unsafe_allow_html=True,
        )

        action_col, clarify_col = st.columns([1.4, 1])
        with action_col:
            gen_btn = st.button(
                "Generate Project",
                type="primary",
                use_container_width=True,
                disabled=st.session_state.polling,
            )
        with clarify_col:
            clarify_btn = st.button(
                "Check Prompt",
                use_container_width=True,
                disabled=st.session_state.polling or len(prompt.strip()) < 10,
            )

    with brief_right:
        st.markdown("#### Stack Summary")
        st.markdown(
            "\n".join([
                f"- **Type**: {project_type}",
                f"- **Backend**: {wiz.get('backend', 'none')}",
                f"- **Frontend**: {wiz.get('frontend', 'none')}",
                f"- **Database**: {wiz.get('db', 'none')}",
                f"- **ORM**: {wiz.get('orm', 'none')}",
                f"- **Auth**: {wiz.get('auth', 'none')}",
                f"- **Testing**: {wiz.get('testing', 'none')}",
                f"- **CSS**: {wiz.get('css', 'none')}",
                f"- **Deploy**: {wiz.get('deploy', 'none')}",
            ])
        )
        st.caption("This summary is what will be sent with the prompt when you generate.")

    if clarify_btn:
        if len(prompt.strip()) < 10:
            st.error("Enter a project description first.")
        else:
            with st.spinner("Checking prompt clarity..."):
                resp = _post("/clarify", {"prompt": prompt.strip(), "model": "local"})
            if resp:
                question = resp.get("question")
                if question:
                    st.session_state.clarify_question = question
                    st.session_state.clarify_answered = False
                    st.session_state.clarify_answer = ""
                else:
                    st.session_state.clarify_question = None
                    st.session_state.clarify_answered = False
                    st.session_state.clarify_answer = ""
                    st.success("The prompt is already clear enough to generate.")

    if st.session_state.clarify_question:
        st.info(st.session_state.clarify_question)
        st.session_state.clarify_answer = st.text_input(
            "Optional answer",
            value=st.session_state.clarify_answer,
            placeholder="Add extra detail only if it helps the generator.",
            key="wiz_clarify_input",
        )
        answer_cols = st.columns(2)
        with answer_cols[0]:
            if st.button("Use this detail", use_container_width=True, key="wiz_use_clarify"):
                st.session_state.clarify_answered = True
        with answer_cols[1]:
            if st.button("Ignore it", use_container_width=True, key="wiz_skip_clarify"):
                st.session_state.clarify_question = None
                st.session_state.clarify_answered = False
                st.session_state.clarify_answer = ""
                st.rerun()

    if gen_btn:
        clean_prompt = prompt.strip()
        if len(clean_prompt) < 10:
            st.error("Enter a project description with at least 10 characters.")
        else:
            payload = {
                "prompt": clean_prompt,
                "project_name": proj_name.strip() or "My Project",
                "model": st.session_state.selected_model,
                "stack": {
                    "backend": wiz.get("backend", "fastapi"),
                    "frontend": wiz.get("frontend", "none"),
                    "db": wiz.get("db", "sqlite"),
                    "css": wiz.get("css", "none"),
                    "testing": wiz.get("testing", "pytest"),
                    "orm": wiz.get("orm", "none" if wiz.get("db") == "none" else "sqlalchemy"),
                    "auth": wiz.get("auth", "none"),
                    "deploy": wiz.get("deploy", "docker"),
                },
            }
            if st.session_state.clarify_answer.strip():
                payload["clarification"] = st.session_state.clarify_answer.strip()

            with st.spinner("Submitting project generation..."):
                resp = _post("/generate-project", payload)
            if resp:
                st.session_state.job_id = resp["job_id"]
                st.session_state.polling = True
                st.session_state.last_job_name = proj_name.strip() or "My Project"
                st.session_state.clarify_question = None
                st.session_state.clarify_answered = False
                st.session_state.clarify_answer = ""
                st.success(f"Job started — `{resp['job_id'][:16]}...`")
                time.sleep(0.5)
                st.rerun()

    #  Progress panel 
    if st.session_state.job_id:
        st.divider()
        data = _get(f"/status/{st.session_state.job_id}")

        if not data:
            st.warning(" Could not fetch job status.")
        else:
            status  = data.get("status", "unknown")
            pct     = int(data.get("progress_pct", 0))
            agent   = data.get("current_agent", "")
            err     = data.get("error_message", "")
            logs: List[Dict] = data.get("logs", [])

            badge_html = f"<span class='status-badge-{status}'>{status.upper()}</span>"
            st.markdown(
                f"**Job** `{st.session_state.job_id[:16]}…`  •  Status {badge_html}",
                unsafe_allow_html=True,
            )

            if status == "complete":
                st.progress(max(pct, 1), text=f"Generation complete ({pct}%)")
            elif status in ("failed", "cancelled"):
                st.progress(max(pct, 1), text=f"{status.capitalize()} ({pct}%)")
            else:
                st.progress(max(pct, 1), text=f"{agent or 'Starting...'} ({pct}%)")

            AGENTS = [
                ("RequirementAgent", " Requirements"),
                ("PlannerAgent",     " Planner"),
                ("CodeAgent",        " Code"),
                ("TestGenAgent",     " Test Gen"),
                ("DebugAgent",       " Debug"),
                ("DocsAgent",        " Docs"),
                ("ValidationAgent",  " Validate"),
                ("ZipService",       " Package"),
            ]
            THRESHOLDS = [10, 25, 55, 65, 83, 90, 96, 100]

            pills_html = ""
            for (a_key, a_label), threshold in zip(AGENTS, THRESHOLDS):
                if a_key == agent:
                    css = "pill-active"
                elif pct >= threshold:
                    css = "pill-done"
                else:
                    css = "pill-wait"
                pills_html += f"<span class='agent-pill {css}'>{a_label}</span> "
            st.markdown(pills_html, unsafe_allow_html=True)

            # Cancel button (only for running/queued jobs)
            if status in ("queued", "running"):
                if st.button(" Cancel Job", key="cancel_btn", type="secondary"):
                    _post(f"/cancel/{st.session_state.job_id}", {})
                    st.session_state.polling = False
                    st.rerun()

            if status in ("failed", "cancelled"):
                st.error(f" {err or status.capitalize()}")
                if st.button(" Start Over", key="restart"):
                    st.session_state.job_id  = None
                    st.session_state.polling = False
                    st.rerun()

            #  Live file tree (two-column layout) 
            col_logs, col_files = st.columns([2, 1])

            with col_logs:
                if logs:
                    with st.expander(
                        f" Agent Logs  ({len(logs)} entries)",
                        expanded=(status == "running"),
                    ):
                        log_lines = ""
                        for entry in logs[-80:]:
                            ts    = entry.get("timestamp", "")[:19].replace("T", " ")
                            level = entry.get("log_level", "INFO")
                            name  = entry.get("agent_name", "")
                            msg   = entry.get("message", "")
                            icon  = {"INFO": "›", "WARNING": "", "ERROR": "", "DEBUG": "·"}.get(level, "›")
                            log_lines += (
                                f"<div class='log-line log-{level}'>"
                                f"<span style='color:#4b5563'>{ts}</span> "
                                f"{icon} <b>{name}</b>: {msg}</div>"
                            )
                        st.markdown(log_lines, unsafe_allow_html=True)

            with col_files:
                file_data = _get(f"/files/{st.session_state.job_id}")
                if file_data and file_data.get("files"):
                    with st.expander(
                        f" Generated Files ({len(file_data['files'])})",
                        expanded=True,
                    ):
                        for f in file_data["files"]:
                            icon = "" if f.endswith(".py") else "" if f.endswith(".md") else "" if f.endswith(".txt") else "" if "Docker" in f else ""
                            st.caption(f"{icon} `{f}`")

            #  Download + Regenerate 
            #  Live test results (visible during and after run) 
            test_total  = data.get("test_total", 0)
            test_passed = data.get("test_passed", 0)
            test_failed = data.get("test_failed", 0)
            test_summary = data.get("test_summary", "")

            if test_total > 0 or test_summary:
                st.divider()
                st.markdown("####  Test Results")
                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    st.metric("Total Tests", test_total)
                with tc2:
                    st.metric("Passed", test_passed, delta_color="off")
                with tc3:
                    st.metric("Failed", test_failed, delta_color="inverse")

                if test_summary:
                    if "Import error" in test_summary or "ImportError" in test_summary:
                        st.warning(f" {test_summary}")
                    elif test_failed > 0:
                        st.error(f" {test_summary}")
                    elif test_passed == test_total and test_total > 0:
                        st.success(f" {test_summary}")
                    else:
                        st.info(f"ℹ {test_summary}")

                #  Test source code + fix button 
                if status == "complete" and st.session_state.job_id:
                    _jid = st.session_state.job_id
                    try:
                        _tr = requests.get(f"{BACKEND}/test-files/{_jid}", timeout=10)
                        if _tr.ok:
                            _tfiles = _tr.json().get("test_files", {})
                            if _tfiles:
                                with st.expander("Test Source Code", expanded=False):
                                    for _tn, _tc in _tfiles.items():
                                        st.markdown(f"**`{_tn}`**")
                                        st.code(_tc, language="python", line_numbers=True)
                    except Exception:
                        pass

                    if test_failed > 0:
                        if st.button("\U0001f527 Fix Failing Tests", key=f"fix_tests_gen_{_jid}",
                                     type="primary"):
                            with st.spinner("Fixing failing tests..."):
                                try:
                                    _fr = requests.post(f"{BACKEND}/fix-tests/{_jid}",
                                                        json={"model": st.session_state.selected_model},
                                                        timeout=300)
                                    if _fr.ok:
                                        _fd = _fr.json()
                                        if _fd.get("already_passing"):
                                            st.success("All tests already pass!")
                                            st.rerun()
                                        else:
                                            _ch = _fd.get("changes", {})
                                            if _ch.get("modified"):
                                                st.info(f"Modified: {', '.join(_ch['modified'])}")
                                            if _ch.get("added"):
                                                st.success(f"Added: {', '.join(_ch['added'])}")
                                            if _fd.get("after", {}).get("passed"):
                                                st.success("\u2705 All tests pass after fix!")
                                            else:
                                                st.error("\u274c Tests still failing.")
                                            with st.expander("Before / After Test Output"):
                                                _c1, _c2 = st.columns(2)
                                                _c1.markdown("**Before**")
                                                _c1.code(_fd.get("before", {}).get("output", ""))
                                                _c2.markdown("**After**")
                                                _c2.code(_fd.get("after", {}).get("output", ""))
                                            st.rerun()
                                except Exception as _exc:
                                    st.error(str(_exc))

            if status == "complete":
                st.divider()
                st.markdown("###  Your Project is Ready")
                dc1, dc2 = st.columns([3, 1])
                with dc1:
                    file_count = data.get("file_count", 0)
                    st.info(
                        f"Generated **{file_count} file(s)**. "
                        "Download → extract → `pip install -r requirements.txt` → run."
                    )
                with dc2:
                    zb = _download(st.session_state.job_id)
                    if zb:
                        fname = (st.session_state.last_job_name or "project").replace(" ", "_")
                        st.download_button(
                            " Download ZIP",
                            data=zb,
                            file_name=f"{fname}.zip",
                            mime="application/zip",
                            use_container_width=True,
                            type="primary",
                        )

                #  Validation summary 
                val_result = _get(f"/validate/{st.session_state.job_id}")
                if val_result:
                    st.divider()
                    st.markdown("####  Validation Report")
                    v1, v2, v3 = st.columns(3)
                    syn_ok     = val_result.get("syntax_ok", False)
                    pytest_res = val_result.get("pytest") or {}
                    py_passed  = pytest_res.get("passed", False)
                    py_skipped = pytest_res.get("skipped", False)
                    syn_count  = len(val_result.get("syntax_results", {}))
                    with v1:
                        st.metric("Syntax", f"{' OK' if syn_ok else ' Errors'}",
                                  f"{syn_count} files checked")
                    with v2:
                        if py_skipped:
                            st.metric("Tests", " Skipped", "No test dir")
                        else:
                            st.metric("Tests", f"{' Passed' if py_passed else ' Failed'}")
                    with v3:
                        overall = syn_ok
                        st.metric("Overall", " PASS" if overall else " FAIL")

                    if not syn_ok:
                        with st.expander("Syntax errors"):
                            for f, r in val_result.get("syntax_results", {}).items():
                                if not r["valid"]:
                                    st.code(f"{f}: {r['error']}", language="text")

                    if not py_skipped and not py_passed and pytest_res.get("output"):
                        with st.expander("pytest output"):
                            st.code(pytest_res["output"][:2000], language="text")

                #  Changelog viewer 
                _jid = st.session_state.job_id
                try:
                    _cr = requests.get(f"{BACKEND}/changelog/{_jid}", timeout=10)
                    if _cr.ok and _cr.json().get("exists"):
                        with st.expander("Project Changelog", expanded=False):
                            st.markdown(_cr.json()["changelog"])
                except Exception:
                    pass

                #  AI Review 
                _rs_raw = data.get("review_summary", "")
                if _rs_raw:
                    import json as _json2
                    try:
                        _rs = _json2.loads(_rs_raw) if isinstance(_rs_raw, str) else _rs_raw
                    except Exception:
                        _rs = None
                    if _rs and isinstance(_rs, dict):
                        _v = _rs.get("verdict", "")
                        _err = _rs.get("error", "")
                        _icon = {"PASS": "\U0001f7e2", "WARN": "\U0001f7e1", "FAIL": "\U0001f534"}.get(_v, "\u26a0\ufe0f")
                        with st.expander(f"{_icon} AI Review — {_v}" + (" (error)" if _err else ""), expanded=True):
                            if _err:
                                st.warning(f"Review encountered an issue: {_err}")
                            _issues = _rs.get("issues", [])
                            if _issues:
                                for _iss in _issues:
                                    _sev_ic = "\U0001f534" if _iss.get("severity") == "error" else "\U0001f7e1"
                                    _loc = f"`{_iss.get('file','')}:{_iss.get('line',0)}`" if _iss.get("file") else ""
                                    st.markdown(f"{_sev_ic} **{_iss.get('description','')}** {_loc}")
                            _recs = _rs.get("recommendations", [])
                            if _recs:
                                st.markdown("**Recommendations:**")
                                for _r in _recs:
                                    st.markdown(f"- {_r}")

                #  Regenerate file panel 
                st.markdown("####  Regenerate a File")
                st.caption("Fix or improve a specific file without regenerating the whole project.")
                regen_file = st.text_input(
                    "File path (e.g. backend/main.py)",
                    placeholder="backend/main.py",
                    key="regen_path",
                )
                regen_note = st.text_area(
                    "Correction note (optional)",
                    placeholder="E.g. Add pagination to the /items endpoint",
                    height=80,
                    key="regen_note",
                )
                if st.button(" Regenerate File", key="regen_btn", disabled=not regen_file.strip()):
                    with st.spinner(f"Regenerating {regen_file}…"):
                        result = _post("/regenerate-file", {
                            "job_id":          st.session_state.job_id,
                            "file_path":       regen_file.strip(),
                            "correction_note": regen_note.strip() or None,
                            "model":           st.session_state.selected_model,
                        })
                    if result:
                        if result.get("syntax_ok"):
                            st.success(f" `{regen_file}` regenerated ({result.get('chars', 0)} chars, syntax OK)")
                        else:
                            st.warning(f" `{regen_file}` regenerated but has syntax error: {result.get('syntax_error')}")

                #  Iterate project panel 
                st.markdown("####  Iterate on Project")
                st.caption("Add new features, modify existing code, or change behavior with a natural language prompt.")
                iter_prompt = st.text_area(
                    "What would you like to add or change?",
                    placeholder="E.g. Add user authentication with JWT tokens and a login page",
                    height=90,
                    key="iter_prompt",
                )
                if st.button(" Apply Changes", key="iter_btn", disabled=not iter_prompt.strip()):
                    with st.spinner("AI is modifying your project..."):
                        result = _post(f"/iterate/{st.session_state.job_id}", {
                            "prompt": iter_prompt.strip(),
                            "model":  st.session_state.selected_model,
                        })
                    if result:
                        changes = result.get("changes", {})
                        added = changes.get("added", [])
                        modified = changes.get("modified", [])
                        deleted = changes.get("deleted", [])
                        if added:
                            st.success(f" Added {len(added)} file(s): " + ", ".join(added))
                        if modified:
                            st.info(f" Modified {len(modified)} file(s): " + ", ".join(modified))
                        if deleted:
                            st.warning(f" Deleted {len(deleted)} file(s): " + ", ".join(deleted))
                        if not added and not modified and not deleted:
                            st.info("No changes were made. Try a more specific prompt.")
                        st.metric("Syntax OK", " Pass" if result.get("syntax_ok") else " Errors")
                        st.metric("Tests", f"{result.get('test_passed', '?')}/{result.get('test_total', '?')}")
                        if result.get("syntax_errors"):
                            with st.expander("Syntax errors"):
                                for f, e in result["syntax_errors"].items():
                                    st.code(f"{f}: {e}")
                        # Show diffs
                        diffs = result.get("diffs", {})
                        if diffs:
                            with st.expander("Code Diffs", expanded=True):
                                for fpath, diff_text in diffs.items():
                                    st.markdown(f"**`{fpath}`**")
                                    st.code(diff_text[:3000], language="diff")
                        st.rerun()

                if st.button(" New Project", use_container_width=False):
                    st.session_state.job_id  = None
                    st.session_state.polling = False
                    st.rerun()

            if st.session_state.polling and status in ("queued", "running"):
                time.sleep(POLL_SEC)
                st.rerun()
            elif status in ("complete", "failed", "cancelled"):
                st.session_state.polling = False


# 
# TAB 2 — History
# 
with tab_hist:
    st.markdown("## Recent Jobs")
    if st.button(" Refresh", key="hist_refresh"):
        st.rerun()

    hist = _get("/jobs")
    jobs: List[Dict] = (hist or {}).get("jobs", [])

    if not jobs:
        st.info("No jobs found yet. Generate your first project!")
    else:
        STATUS_ICON = {
            "complete": "", "running": "", "failed": "",
            "queued": "", "cancelled": "",
        }
        for job in jobs:
            jid      = job.get("job_id", "")
            jname    = job.get("project_name", "Unnamed")
            jstat    = job.get("status", "unknown")
            jpct     = int(job.get("progress_pct", 0))
            jcreated = job.get("created_at", "")[:16].replace("T", " ")
            icon     = STATUS_ICON.get(jstat, "•")

            with st.expander(f"{icon} **{jname}** — `{jid[:12]}…`  •  {jcreated}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Status",   jstat.upper())
                c2.metric("Progress", f"{jpct}%")
                c3.metric("Files",    job.get("file_count", 0))

                if jstat == "complete":
                    zb = _download(jid)
                    if zb:
                        st.download_button(
                            " Download ZIP",
                            data=zb,
                            file_name=f"{jname.replace(' ', '_')}.zip",
                            mime="application/zip",
                            key=f"dl_{jid}",
                        )
                elif jstat == "failed":
                    st.error(job.get("error_message", "Unknown error"))
                if st.button("View Live Status", key=f"view_{jid}"):
                    st.session_state.job_id  = jid
                    st.session_state.polling = jstat in ("queued", "running")
                    st.rerun()

                with st.popover("Delete"):
                    st.warning("Delete this project permanently?")
                    if st.button("Yes, delete", key=f"del_yes_{jid}"):
                        import urllib.parse
                        try:
                            dr = requests.delete(f"{BACKEND}/jobs/{urllib.parse.quote(jid)}", timeout=10)
                            if dr.ok:
                                st.success("Deleted.")
                                st.rerun()
                            else:
                                st.error(f"Error: {dr.text[:100]}")
                        except Exception as exc:
                            st.error(str(exc))


# 
# TAB 3 — Analytics
# 
with tab_analytics:
    from frontend.pages.analytics import show_analytics_tab
    show_analytics_tab()


# 
# TAB 4 — Workspace
# 
with tab_workspace:
    from frontend.pages.workspace import show_workspace_tab
    show_workspace_tab()


# 
# TAB 5 — Benchmarks
# 
with tab_benchmarks:
    from frontend.pages.benchmarks import show_benchmarks_tab
    show_benchmarks_tab()


# 
# TAB 6 — Organization
# 
with tab_org:
    from frontend.pages.organization import show_organization_tab
    show_organization_tab()


# 
# TAB 7 — Ecosystem
# 
with tab_eco:
    from frontend.pages.ecosystem import show_ecosystem_tab
    show_ecosystem_tab()


# 
# TAB 8 — Evaluation
# 
with tab_eval:
    from frontend.pages.evaluation import show_evaluation_tab
    show_evaluation_tab()


# 
# TAB 9 — How It Works
# 
with tab_info:
    st.markdown("## How ProjectPilot Works")
    st.markdown("""
###  Architecture

```

              Streamlit Frontend (8501)              

                          REST API
                         

              FastAPI Backend (8000)                 
  POST /clarify           POST /generate-project     
  POST /cancel/:id        POST /regenerate-file      
  GET  /files/:id         GET  /validate/:id         
  GET  /status/:id        GET  /download/:id         
  GET  /health            GET  /jobs                 

         Background Thread        
                                  
    
  Agent Pipeline        ChromaDB (chroma_data/)     
                         jobs collection           
  1. Requirement         generation_logs           
  2. Planner             requirements              
  3. Code ()            blueprints                
  4. TestGen          
  5. Debug ()    
  6. Docs             
  7. ZIP                Cleanup Daemon              
      Deletes ZIPs > 24h old      
   = parallel calls     
```

###  Agent Pipeline

| # | Agent | Model | What it does |
|---|-------|-------|--------------|
| 0 | **Clarify** (optional) | local | Asks one question if prompt is vague |
| 1 | **RequirementAgent** | local | Parses prompt → structured JSON requirements |
| 2 | **PlannerAgent** | local | Designs folder structure, routes, DB schema |
| 3 | **CodeAgent** | local | Generates all source files **in parallel** |
| 4 | **TestGenAgent** | local | Generates pytest tests from blueprint routes |
| 5 | **DebugAgent** | local | Syntax-checks + fixes files **in parallel**, runs pytest, blueprint reflection |
| 6 | **DocsAgent** | local | Writes README.md with architecture diagram |
| 7 | **ValidationAgent** | — | Hardcoded structural + syntax + pytest checks → VALIDATION_REPORT.md |
| 8 | **ZipService** | — | Packages everything into a downloadable ZIP |

###  v4 Improvements
-  **Parallel code generation** — 5 files generated concurrently (3–4× faster)
-  **Clarify endpoint** — one question before pipeline if prompt is ambiguous
-  **TestGenAgent** — generates pytest tests from blueprint routes
-  **Blueprint reflection** — checks generated routes match the plan
-  **Regenerate file** — fix one file without full regeneration
-  **Job cancellation** — cancel queued/running jobs
-  **Live file tree** — see files appear during generation
-  **Auto cleanup** — old ZIPs deleted after 24h
-  **Structured JSON logging** — every LLM call logged with duration_ms
-  **LLM retry with backoff** — up to 3 retries on timeout
-  **Tech stack selector** — FastAPI/Flask, Streamlit/React, SQLite/PostgreSQL
-  **Models** — Gemma 4 12B (local) + Gemini/Gemma 4 31B (cloud)
-  **ValidationAgent** — deterministic quality gate: structure + syntax + pytest before packaging
""")
