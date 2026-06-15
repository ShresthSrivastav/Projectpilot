"""Workspace — browse local projects and GitHub repositories with full management UI."""
import os
from typing import Any, Dict, Optional

import requests
import streamlit as st
from streamlit.components.v1 import html as _html

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def _get(path: str, timeout: int = 10) -> Optional[Dict]:
    try:
        r = requests.get(f"{BACKEND}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _post(path: str, data: Any, timeout: int = 15) -> Optional[Dict]:
    try:
        r = requests.post(f"{BACKEND}{path}", json=data, timeout=timeout)
        if not r.ok:
            try:
                detail = r.json().get("detail", r.text[:200])
            except Exception:
                detail = r.text[:200]
            st.error(f"Request failed: {detail}")
            return None
        return r.json()
    except Exception as e:
        st.error(str(e))
        return None


# 
#   Local Projects Section
# 

def _show_local_projects():
    st.markdown("#### Local Generated Projects")
    try:
        r = requests.get(f"{BACKEND}/jobs", timeout=8)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
    except Exception:
        st.info("Backend not reachable.")
        return

    if not jobs:
        st.caption("No local projects yet. Submit a prompt on the Generate tab.")
        return

    labels = [f"{j.get('project_name','?')} [{j.get('job_id','')[:10]}] \u2014 {j.get('status','?')}" for j in jobs]
    sel = st.selectbox("Project", labels, key="ws_local_sel")
    if not sel:
        return
    idx = labels.index(sel)
    job = jobs[idx]
    jid = job.get("job_id", "")

    detail = _get(f"/status/{jid}")
    if not detail:
        st.warning("Could not fetch details.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Status", detail.get("status", ""))
    c2.metric("Progress", f"{detail.get('progress_pct',0)}%")
    c3.metric("Files", detail.get("file_count", 0))

    fl = detail.get("file_list", [])
    if fl:
        sf = st.selectbox("File", fl, key="ws_local_file", label_visibility="collapsed")
        if sf:
            enc = sf.replace("\\", "/")
            resp = requests.get(f"{BACKEND}/read-project-file/{jid}/{enc}", timeout=10)
            if resp.ok:
                ext = os.path.splitext(sf)[1]
                lang = {"py":"python","js":"javascript","ts":"typescript","html":"html",
                        "css":"css","json":"json","yaml":"yaml","md":"markdown",
                        "sh":"bash","bat":"batch","txt":"text"}.get(ext.lstrip("."),"")
                st.code(resp.text, language=lang or "text", line_numbers=True)

    _show_test_results(detail)
    _show_logs(detail)
    _show_changelog(jid)

    if detail.get("status") == "complete":
        st.divider()
        st.markdown("#### Modify Project")
        iter_prompt = st.text_area(
            "Prompt",
            placeholder="E.g. Add user authentication with JWT...",
            key="ws_iter_prompt",
            label_visibility="collapsed",
        )
        if st.button("Apply Changes", key="ws_iter_btn", disabled=not iter_prompt.strip()):
            with st.spinner("Applying changes..."):
                try:
                    r = requests.post(
                        f"{BACKEND}/iterate/{jid}",
                        json={"prompt": iter_prompt, "model": st.session_state.selected_model},
                        timeout=300,
                    )
                    if r.ok:
                        data = r.json()
                        ch = data.get("changes", {})
                        added = ch.get("added", [])
                        modified = ch.get("modified", [])
                        deleted = ch.get("deleted", [])
                        if added:
                            st.success(f"Added: {', '.join(added)}")
                        if modified:
                            st.info(f"Modified: {', '.join(modified)}")
                        if deleted:
                            st.warning(f"Deleted: {', '.join(deleted)}")
                        if not (added or modified or deleted):
                            st.warning("No changes were applied.")
                        syntax_ok = data.get("syntax_ok", True)
                        st.metric("Syntax", "\u2705 OK" if syntax_ok else "\u274c Errors")
                        tp = data.get("test_passed", 0)
                        tt = data.get("test_total", 0)
                        st.metric("Tests", f"{tp}/{tt} passed")
                        if not syntax_ok:
                            with st.expander("Syntax Errors"):
                                for f, err in data.get("syntax_errors", {}).items():
                                    st.code(f"{f}: {err}")
                        # Show diffs
                        diffs = data.get("diffs", {})
                        if diffs:
                            with st.expander("Code Diffs", expanded=True):
                                for fpath, diff_text in diffs.items():
                                    st.markdown(f"**`{fpath}`**")
                                    st.code(diff_text[:3000], language="diff")
                        st.rerun()
                    else:
                        st.error(f"Request failed: {r.text[:200]}")
                except Exception as exc:
                    st.error(str(exc))

        st.divider()
        if st.button("\u274c Delete Project", key="ws_del_btn", type="secondary",
                     help="Permanently delete this project and all its files."):
            import urllib.parse
            try:
                r = requests.delete(f"{BACKEND}/jobs/{urllib.parse.quote(jid)}", timeout=10)
                if r.ok:
                    st.success("Project deleted.")
                    st.rerun()
                else:
                    st.error(f"Delete failed: {r.text[:200]}")
            except Exception as exc:
                st.error(str(exc))


def _show_test_results(detail: Dict):
    tt = detail.get("test_total", 0)
    if tt <= 0:
        return
    st.markdown("#### Test Results")
    tp = detail.get("test_passed", 0)
    tf = detail.get("test_failed", 0)
    ts = detail.get("test_skipped", 0)
    pp = max(tp / tt * 100, 0)
    fp = max(tf / tt * 100, 0)
    sp = max(ts / tt * 100, 0)
    st.markdown(
        f"<div style='display:flex;height:26px;border-radius:6px;overflow:hidden;font-size:13px;font-weight:600;'>"
        f"<div style='flex:{pp};background:#27ae60;display:flex;align-items:center;justify-content:center;color:#fff'>{tp} passed</div>"
        f"<div style='flex:{fp};background:#e74c3c;display:flex;align-items:center;justify-content:center;color:#fff'>{tf} failed</div>"
        f"<div style='flex:{sp};background:#f39c12;display:flex;align-items:center;justify-content:center;color:#fff'>{ts} skipped</div>"
        f"</div>", unsafe_allow_html=True)
    tdetails = detail.get("test_details", [])
    if tdetails:
        st.markdown("**Individual Tests**")
        for td in tdetails:
            nm = td.get("test", "?")
            sts = td.get("status", "?")
            ic = {"PASSED":"\u2705","FAILED":"\u274c","SKIPPED":"\u23ed\ufe0f"}.get(sts,"\u2022")
            st.markdown(f"{ic} `{nm}`")
    sm = detail.get("test_summary", "")
    if sm:
        st.caption(f"Summary: {sm}")

    # Show test source code
    jid = detail.get("job_id", "")
    if jid:
        try:
            tr = requests.get(f"{BACKEND}/test-files/{jid}", timeout=10)
            if tr.ok:
                tfiles = tr.json().get("test_files", {})
                if tfiles:
                    with st.expander("Test Source Code", expanded=False):
                        for tname, tcode in tfiles.items():
                            st.markdown(f"**`{tname}`**")
                            st.code(tcode, language="python", line_numbers=True)
        except Exception:
            pass

    # Fix failing tests button
    if tf > 0 and jid:
        if st.button("\U0001f527 Fix Failing Tests", key=f"fix_tests_{jid}", type="primary",
                     help="Use AI to fix source code so all tests pass"):
            with st.spinner("Running tests, analysing failures, and fixing code..."):
                try:
                    fr = requests.post(f"{BACKEND}/fix-tests/{jid}",
                                       json={"model": st.session_state.selected_model}, timeout=300)
                    if fr.ok:
                        fdata = fr.json()
                        if fdata.get("already_passing"):
                            st.success("All tests already pass!")
                            st.rerun()
                        else:
                            ch = fdata.get("changes", {})
                            mods = ch.get("modified", [])
                            adds = ch.get("added", [])
                            if mods:
                                st.info(f"Modified: {', '.join(mods)}")
                            if adds:
                                st.success(f"Added: {', '.join(adds)}")
                            after = fdata.get("after", {})
                            if after.get("passed"):
                                st.success(f"\u2705 All tests pass after fix!")
                            else:
                                st.error(f"\u274c Tests still failing.")
                            with st.expander("Before / After Test Output"):
                                col1, col2 = st.columns(2)
                                col1.markdown("**Before**")
                                col1.code(fdata.get("before", {}).get("output", ""))
                                col2.markdown("**After**")
                                col2.code(after.get("output", ""))
                            st.rerun()
                    else:
                        st.error(f"Fix failed: {fr.text[:200]}")
                except Exception as exc:
                    st.error(str(exc))

    #  AI Review 
    rs_raw = detail.get("review_summary", "")
    if rs_raw:
        import json as _json
        try:
            rs = _json.loads(rs_raw) if isinstance(rs_raw, str) else rs_raw
        except Exception:
            rs = None
        if rs and isinstance(rs, dict):
            v = rs.get("verdict", "")
            err = rs.get("error", "")
            icon = {"PASS": "\U0001f7e2", "WARN": "\U0001f7e1", "FAIL": "\U0001f534"}.get(v, "\u26a0\ufe0f")
            with st.expander(f"{icon} AI Review — {v}" + (" (error)" if err else ""), expanded=True):
                if err:
                    st.warning(f"Review encountered an issue: {err}")
                issues = rs.get("issues", [])
                if issues:
                    for iss in issues:
                        sev = iss.get("severity", "info")
                        sev_ic = "\U0001f534" if sev == "error" else "\U0001f7e1"
                        fp = iss.get("file", "")
                        ln = iss.get("line", 0)
                        loc = f"`{fp}:{ln}`" if fp and ln else ""
                        st.markdown(f"{sev_ic} **{iss.get('description', '')}** {loc}")
                recs = rs.get("recommendations", [])
                if recs:
                    st.markdown("**Recommendations:**")
                    for r in recs:
                        st.markdown(f"- {r}")

    if jid:
        if st.button("\U0001f50d Review Project", key=f"review_{jid}", type="secondary",
                     help="Run AI review of the full project"):
            with st.spinner("Analyzing project..."):
                try:
                    rr = requests.post(f"{BACKEND}/review/{jid}",
                                       json={"model": st.session_state.selected_model}, timeout=300)
                    if rr.ok:
                        st.rerun()
                    else:
                        st.error(f"Review failed: {rr.text[:200]}")
                except Exception as exc:
                    st.error(str(exc))


def _show_changelog(jid: str):
    try:
        r = requests.get(f"{BACKEND}/changelog/{jid}", timeout=10)
        if r.ok:
            data = r.json()
            if data.get("exists"):
                with st.expander("Project Changelog", expanded=False):
                    st.markdown(data["changelog"])
    except Exception:
        pass


def _show_logs(detail: Dict):
    logs = detail.get("logs", [])
    if logs:
        with st.expander("Agent Logs", expanded=False):
            for log in logs[-25:]:
                lv = log.get("log_level", "INFO")
                ag = log.get("agent_name", "")
                msg = log.get("message", "")
                ts = log.get("timestamp", "")[11:19] if log.get("timestamp") else ""
                st.code(f"[{ts}] [{lv}] [{ag}] {msg}")


# 
#   GitHub Integration Section
# 

def _gh_get(path: str, timeout: int = 10) -> Optional[Dict]:
    return _get(path, timeout)


def _gh_post(path: str, data: Any = None, timeout: int = 15) -> Optional[Dict]:
    return _post(path, data or {}, timeout)


def _show_github_section():
    st.markdown("---")
    st.markdown("## GitHub Integration")

    #  Connection 
    conns = _gh_get("/github/connections")
    connections = (conns or {}).get("connections", [])
    current_username = st.session_state.get("gh_username", "")

    if not current_username and connections:
        current_username = connections[0].get("username", "")
        st.session_state.gh_username = current_username

    with st.expander("GitHub Connection", expanded=not bool(current_username)):
        if current_username:
            st.info(f"Connected as **{current_username}**")
            if st.button("Disconnect", key="gh_disconnect"):
                _gh_post("/github/disconnect", {"username": current_username})
                st.session_state.gh_username = ""
                st.rerun()
        else:
            token = st.text_input("GitHub Personal Access Token", type="password",
                                  placeholder="ghp_...", key="gh_token_input")
            if st.button("Connect", key="gh_connect"):
                if token:
                    res = _gh_post("/github/connect", {"token": token})
                    if res and res.get("status") == "connected":
                        data = res.get("data", {})
                        st.session_state.gh_username = data.get("username", "")
                        st.success(f"Connected as {data.get('username', '')}")
                        st.rerun()
                    else:
                        st.error("Connection failed. Check your token.")

    if not current_username:
        st.info("Connect to GitHub above to browse repositories, manage branches, commits, PRs, and issues.")
        return

    username = current_username
    token_placeholder = "TODO"  # not stored in session for security; fetched from backend

    #  Tabs within GitHub 
    gh_tab1, gh_tab2, gh_tab3, gh_tab4, gh_tab5 = st.tabs([
        "Repositories", "Branches && Files", "Commits", "Pull Requests", "Issues",
    ])

    # 
    # GH TAB 1 — Repositories
    # 
    with gh_tab1:
        st.markdown("### Your Repositories")

        col1, col2 = st.columns([3, 1])
        with col1:
            search_q = st.text_input("Search repos", placeholder="e.g. my-project or organization/repo",
                                     key="gh_search_q")
        with col2:
            st.write("")
            if st.button("Refresh", key="gh_refresh_repos", use_container_width=True):
                pass  # triggers rerun below

        repos_data = _gh_get(f"/github/{username}/repos")
        repos = (repos_data or {}).get("repos", [])

        if search_q:
            q = search_q.lower()
            repos = [r for r in repos if q in r["full_name"].lower() or q in r.get("description","").lower()]

        if not repos:
            st.caption("No repositories found. Make sure your token has repo scope.")
        else:
            for r in repos:
                nm = r["full_name"]
                desc = r.get("description", "") or "No description"
                lang = r.get("language", "") or "N/A"
                stars = r.get("stars", 0)
                priv = "\U0001f512" if r.get("private") else "\U0001f4c2"
                with st.expander(f"{priv} **{nm}** \u2014 {lang} \u2606{stars}"):
                    st.caption(desc[:200])
                    c1, c2, c3, c4 = st.columns(4)
                    c1.markdown(f"**Branch:** `{r.get('default_branch','')}`")
                    c2.markdown(f"Forks: {r.get('forks',0)}")
                    c3.markdown(f"Issues: {r.get('open_issues',0)}")
                    c4.markdown(f"[Open on GitHub]({r.get('url','')})")
                    if st.button("Browse Files", key=f"gh_browse_{nm}", use_container_width=True):
                        st.session_state.gh_active_repo = nm
                        st.session_state.gh_active_tab = "Branches && Files"
                        st.rerun()

    # 
    # GH TAB 2 — Branches & Files
    # 
    with gh_tab2:
        repo = st.session_state.get("gh_active_repo", "")
        if not repo:
            repo = st.text_input("Repository (user/repo)", placeholder="e.g. octocat/Hello-World",
                                 key="gh_repo_input")
            if not repo:
                st.caption("Select a repo from the Repositories tab or type one above.")
                st.stop()

        st.markdown(f"**Repo:** `{repo}`")

        branches_data = _gh_get(f"/github/{repo}/branches?username={username}")
        branches = (branches_data or {}).get("branches", [])
        branch_names = [b["name"] for b in branches]
        current_branch = st.session_state.get("gh_branch", branches[0]["name"] if branches else "main")
        if branch_names:
            current_branch = st.selectbox("Branch", branch_names, index=branch_names.index(current_branch)
                                          if current_branch in branch_names else 0, key="gh_branch_sel")
            st.session_state.gh_branch = current_branch

        col1, col2 = st.columns([2, 1])
        with col1:
            new_branch = st.text_input("New branch name", placeholder="feature/xyz", key="gh_new_branch")
            if st.button("Create Branch", key="gh_create_branch") and new_branch:
                res = _gh_post(f"/github/{repo}/branches", {
                    "username": username, "branch": new_branch,
                    "source_branch": current_branch,
                })
                if res:
                    st.success(f"Branch `{new_branch}` created")
                    st.rerun()
        with col2:
            st.write("")
            if st.button("\U0001f504 Refresh Branches", key="gh_refresh_branches"):
                st.rerun()

        #  File Browser 
        st.markdown("#### Files")
        gh_path = st.session_state.get("gh_file_path", "")
        gh_path = st.text_input("Path", value=gh_path, placeholder="/", key="gh_file_path_inp")
        st.session_state.gh_file_path = gh_path

        files_data = _gh_get(f"/github/{repo}/files?path={gh_path}&ref={current_branch}&username={username}")
        files = (files_data or {}).get("files", [])

        if files:
            cols = st.columns(4)
            for i, f in enumerate(files):
                with cols[i % 4]:
                    icon = "\U0001f4c1" if f["type"] == "dir" else "\U0001f4c4"
                    name = f["name"]
                    if f["type"] == "dir":
                        if st.button(f"{icon} {name}", key=f"gh_dir_{name}_{i}"):
                            new_path = f"{gh_path}/{name}" if gh_path else name
                            st.session_state.gh_file_path = new_path
                            st.rerun()
                    else:
                        if st.button(f"{icon} {name}", key=f"gh_file_{name}_{i}"):
                            st.session_state.gh_selected_file = f["path"]
                            st.session_state.gh_edit_mode = "view"

        #  File Viewer/Editor 
        selected_file = st.session_state.get("gh_selected_file", "")
        if selected_file:
            st.markdown(f"#### `{selected_file}`")
            doc = _gh_get(f"/github/{repo}/file?path={selected_file}&ref={current_branch}&username={username}")
            content = (doc or {}).get("content", "")
            sha = (doc or {}).get("sha", "")

            edit_mode = st.session_state.get("gh_edit_mode", "view")
            if edit_mode == "edit":
                new_content = st.text_area("Edit content", value=content, height=400,
                                           key="gh_edit_area")
                commit_msg = st.text_input("Commit message", placeholder=f"Update {selected_file.split('/')[-1]}",
                                           key="gh_commit_msg")
                ccol1, ccol2 = st.columns(2)
                with ccol1:
                    if st.button("Save & Commit", key="gh_save_file"):
                        res = _gh_post(f"/github/{repo}/file", {
                            "username": username,
                            "path": selected_file,
                            "content": new_content,
                            "message": commit_msg or f"Update {selected_file.split('/')[-1]}",
                            "branch": current_branch,
                            "sha": sha,
                        })
                        if res:
                            st.success(f"Committed: `{res.get('commit','')[:12]}`")
                            st.session_state.gh_edit_mode = "view"
                            st.rerun()
                with ccol2:
                    if st.button("Cancel", key="gh_cancel_edit"):
                        st.session_state.gh_edit_mode = "view"
                        st.rerun()
            else:
                ext = os.path.splitext(selected_file)[1]
                lang_map = {"py":"python","js":"javascript","ts":"typescript","html":"html",
                            "css":"css","json":"json","yaml":"yaml","md":"markdown",
                            "sh":"bash","bat":"batch","txt":"text"}
                lang = lang_map.get(ext.lstrip("."), "")
                st.code(content[:10000], language=lang or "text", line_numbers=True)
                if st.button("Edit File", key="gh_edit_file"):
                    st.session_state.gh_edit_mode = "edit"
                    st.rerun()

    # 
    # GH TAB 3 — Commits
    # 
    with gh_tab3:
        repo = st.session_state.get("gh_active_repo", repo if 'repo' in dir() else "")
        if not repo:
            repo = st.text_input("Repository", placeholder="user/repo", key="gh_commits_repo")
        if repo:
            branch = st.text_input("Branch", value=st.session_state.get("gh_branch", ""),
                                   key="gh_commits_branch")
            since = st.text_input("Since (ISO date)", placeholder="2026-01-01", key="gh_commits_since")
            commits_data = _gh_get(
                f"/github/{repo}/commits?branch={branch}&since={since}&username={username}")
            commits = (commits_data or {}).get("commits", [])
            if commits:
                for c in commits:
                    with st.expander(f"{c['sha'][:8]} \u2014 {c['message'][:80]}"):
                        st.markdown(f"**Author:** {c['author']} <{c.get('author_email','')}>")
                        st.markdown(f"**Date:** {c['date'][:19]}")
                        st.markdown(f"**Changes:** {c.get('files_changed',0)} files, "
                                    f"+{c.get('additions',0)} -{c.get('deletions',0)}")
                        st.markdown(f"[View on GitHub]({c.get('url','')})")
                        sha = c["sha"]
                        diff = _gh_get(f"/github/{repo}/commits/{sha}?username={username}")
                        if diff and diff.get("diff"):
                            with st.expander("Diff"):
                                st.code(diff["diff"][:3000], language="diff")
            else:
                st.caption("No commits found.")

    # 
    # GH TAB 4 — Pull Requests
    # 
    with gh_tab4:
        repo = st.session_state.get("gh_active_repo", repo if 'repo' in dir() else "")
        if not repo:
            repo = st.text_input("Repository", placeholder="user/repo", key="gh_pr_repo")
        if repo:
            pr_state = st.radio("State", ["open", "closed", "all"], horizontal=True, key="gh_pr_state")
            prs_data = _gh_get(f"/github/{repo}/pulls?state={pr_state}&username={username}")
            prs = (prs_data or {}).get("pull_requests", [])
            if prs:
                for pr in prs:
                    ic = "\U0001f31f" if pr.get("draft") else "\U0001f4d6"
                    with st.expander(f"{ic} **#{pr['number']}** {pr['title'][:80]}"):
                        st.markdown(f"**State:** {pr['state']} | **Branch:** {pr['head_branch']} \u2192 {pr['base_branch']}")
                        st.markdown(f"**Author:** {pr['author']} | **Changes:** +{pr.get('additions',0)}/-{pr.get('deletions',0)}")
                        st.markdown(f"[View PR]({pr.get('url','')})")
                        if pr.get("body"):
                            st.text_area("Description", pr["body"][:500], disabled=True, key=f"gh_pr_body_{pr['number']}")
                        if st.button("Review with AI", key=f"gh_review_pr_{pr['number']}"):
                            with st.spinner("AI reviewing PR..."):
                                review = _gh_post("/github/agent/review-pr", {
                                    "full_name": repo, "pr_number": pr["number"], "username": username,
                                })
                            if review:
                                rv = review.get("review", {})
                                st.markdown(f"**Summary:** {rv.get('summary','')}")
                                st.markdown(f"**Approve:** {'Yes' if rv.get('approve') else 'No'}")
                                for s in rv.get("suggestions", []):
                                    st.markdown(f"- {s}")
                                for iss in rv.get("issues", []):
                                    st.warning(f"{iss.get('file','')} ({iss.get('severity','')}): {iss.get('message','')}")
            else:
                st.caption("No pull requests found.")

            with st.expander("Create Pull Request"):
                pr_title = st.text_input("Title", key="gh_new_pr_title")
                pr_body = st.text_area("Description", key="gh_new_pr_body", height=100)
                pr_head = st.text_input("Head branch", key="gh_new_pr_head")
                pr_base = st.text_input("Base branch", value="main", key="gh_new_pr_base")
                if st.button("Create PR", key="gh_create_pr_btn") and pr_title and pr_head and pr_base:
                    res = _gh_post(f"/github/{repo}/pulls", {
                        "username": username, "title": pr_title,
                        "head": pr_head, "base": pr_base, "body": pr_body,
                    })
                    if res:
                        st.success(f"PR #{res.get('number')} created!")
                        st.rerun()

    # 
    # GH TAB 5 — Issues
    # 
    with gh_tab5:
        repo = st.session_state.get("gh_active_repo", repo if 'repo' in dir() else "")
        if not repo:
            repo = st.text_input("Repository", placeholder="user/repo", key="gh_issues_repo")
        if repo:
            iss_state = st.radio("State", ["open", "closed", "all"], horizontal=True, key="gh_iss_state")
            iss_data = _gh_get(f"/github/{repo}/issues?state={iss_state}&username={username}")
            issues = (iss_data or {}).get("issues", [])
            if issues:
                for iss in issues:
                    labels = " ".join(f"`{l}`" for l in iss.get("labels", []))
                    with st.expander(f"**#{iss['number']}** {iss['title'][:80]} {labels}"):
                        st.markdown(f"**State:** {iss['state']} | **Author:** {iss['author']}")
                        st.markdown(f"**Comments:** {iss.get('comments_count',0)}")
                        if iss.get("body"):
                            st.text_area("Description", iss["body"][:500], disabled=True,
                                         key=f"gh_iss_body_{iss['number']}")
                        comment_text = st.text_area("Add comment", placeholder="Write a comment...",
                                                     key=f"gh_iss_comment_{iss['number']}", height=60)
                        if st.button("Comment", key=f"gh_iss_comment_btn_{iss['number']}") and comment_text:
                            res = _gh_post(f"/github/{repo}/issues/{iss['number']}/comments", {
                                "username": username, "body": comment_text,
                            })
                            if res:
                                st.success("Comment added!")
                                st.rerun()
                        if st.button("Analyze with AI", key=f"gh_ai_issue_{iss['number']}"):
                            with st.spinner("AI analyzing issue..."):
                                analysis = _gh_post("/github/agent/fix-issue", {
                                    "full_name": repo, "issue_number": iss["number"], "username": username,
                                })
                            if analysis:
                                an = analysis.get("analysis", {})
                                st.markdown(f"**Root Cause:** {an.get('root_cause','')}")
                                st.markdown(f"**Effort:** {an.get('effort','unknown')}")
                                for step in an.get("fix_plan", []):
                                    st.markdown(f"- `{step.get('file','')}`: {step.get('description','')}")
            else:
                st.caption("No issues found.")

            with st.expander("Create Issue"):
                iss_title = st.text_input("Title", key="gh_new_iss_title")
                iss_body = st.text_area("Description", key="gh_new_iss_body", height=100)
                iss_labels = st.text_input("Labels (comma-separated)", placeholder="bug, enhancement",
                                           key="gh_new_iss_labels")
                if st.button("Create Issue", key="gh_create_iss_btn") and iss_title:
                    lbls = [l.strip() for l in iss_labels.split(",") if l.strip()] if iss_labels else []
                    res = _gh_post(f"/github/{repo}/issues", {
                        "username": username, "title": iss_title, "body": iss_body, "labels": lbls,
                    })
                    if res:
                        st.success(f"Issue #{res.get('number')} created!")
                        st.rerun()


# 
#   Main Workspace Entry Point
# 

def show_workspace_tab():
    st.markdown("## Workspace")
    main_tab_local, main_tab_github = st.tabs(["Local Projects", "GitHub"])
    with main_tab_local:
        _show_local_projects()
    with main_tab_github:
        _show_github_section()
