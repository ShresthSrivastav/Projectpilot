"""Organization Dashboard — multi-repo graph, impact analysis, cross-repo changes."""
import os
from typing import Any

import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def _get(path: str, timeout: int = 10) -> dict | None:
    try:
        r = requests.get(f"{BACKEND}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _post(path: str, data: Any, timeout: int = 30) -> dict | None:
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


def show_organization_tab():
    st.markdown("## Organization Intelligence")
    st.caption("Multi-repository knowledge graph, impact analysis, and cross-repo changes")

    # ── Organization selector ──────────────────────────────────────────────
    orgs_data = _get("/organization/list")
    orgs = (orgs_data or {}).get("organizations", [])
    org_names = {o["name"]: o["id"] for o in orgs}

    col1, col2 = st.columns([3, 1])
    with col1:
        if org_names:
            sel_org = st.selectbox("Organization", options=list(org_names.keys()), key="org_selector")
            org_id = org_names[sel_org]
        else:
            st.info("No organizations yet. Create one below.")
            org_id = ""
    with col2:
        new_name = st.text_input("New org name", placeholder="my-org", key="new_org_name")
        if st.button("Create", key="create_org", disabled=not new_name.strip()):
            resp = _post("/organization/create", {"name": new_name.strip(), "description": ""})
            if resp:
                st.success(f"Created: {resp.get('organization_id', '')[:8]}")
                st.rerun()

    if not org_id:
        return

    tab_graph, tab_repos, tab_impact, tab_changes, tab_validate = st.tabs([
        " Graph", " Repositories", " Impact", " Changes", " Validate",
    ])

    # ── Tab 1: Graph ──────────────────────────────────────────────────────
    with tab_graph:
        st.markdown("### Organization Graph")
        st.caption("Repository dependencies and relationships")

        col_a, col_b = st.columns([2, 1])
        with col_a:
            if st.button(" Refresh Graph", key="refresh_graph"):
                st.rerun()
        with col_b:
            if st.button(" Index All Repos", key="index_all"):
                with st.spinner("Indexing repositories..."):
                    resp = _post("/organization/index", {"org_id": org_id})
                if resp:
                    idx = resp.get("index_results", {})
                    for rname, stats in idx.items():
                        st.info(f"{rname}: {stats.get('files_scanned', 0)} files, {stats.get('entities_found', 0)} entities")
                    st.rerun()

        graph_data = _get(f"/organization/graph?org_id={org_id}")
        if graph_data:
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            st.metric("Repositories", len(nodes))
            st.metric("Dependencies", len(edges))

            if nodes:
                node_lines = "| " + " | ".join(["Name", "Category", "Files", "id"]) + " |\n"
                node_lines += "|" + "|".join(["---"] * 4) + "|\n"
                for n in nodes:
                    node_lines += f"| {n['label']} | {n['category']} | {n['file_count']} | `{n['id']}` |\n"
                st.markdown(node_lines)

            if edges:
                st.markdown("**Dependencies**")
                edge_lines = "| " + " | ".join(["Source", "Target", "Type"]) + " |\n"
                edge_lines += "|" + "|".join(["---"] * 3) + "|\n"
                for e in edges:
                    edge_lines += f"| {e['source']} | {e['target']} | {e['label']} |\n"
                st.markdown(edge_lines)

            if not nodes:
                st.info("No repositories yet. Add repos in the Repositories tab.")
        else:
            st.warning("Could not fetch graph data.")

        health = _get(f"/organization/health?org_id={org_id}")
        if health:
            st.metric("Health Score", f"{health.get('health_score', 0):.1f}")

    # ── Tab 2: Repositories ───────────────────────────────────────────────
    with tab_repos:
        st.markdown("### Repositories")
        st.caption("Add or remove repositories in this organization")

        with st.expander(" Add Repository", expanded=True):
            r_name = st.text_input("Repo name", placeholder="frontend-web", key="repo_name")
            r_path = st.text_input("Path", placeholder="/path/to/repo", key="repo_path")
            r_cat = st.selectbox("Category", ["", "backend", "frontend", "mobile", "infrastructure", "shared-libraries", "data-services", "documentation", "other"], key="repo_cat")
            r_lang = st.text_input("Language (optional)", placeholder="python", key="repo_lang")
            r_url = st.text_input("URL (optional)", placeholder="https://github.com/org/repo", key="repo_url")
            r_desc = st.text_area("Description", placeholder="What this repo does", key="repo_desc")

            if st.button(" Add Repo", key="add_repo", disabled=not r_name.strip() or not r_path.strip()):
                resp = _post("/organization/add-repo", {
                    "org_id": org_id,
                    "name": r_name.strip(),
                    "path": r_path.strip(),
                    "category": r_cat,
                    "language": r_lang.strip(),
                    "url": r_url.strip(),
                    "description": r_desc.strip(),
                })
                if resp:
                    st.success(f"Added repo: {resp.get('repository', {}).get('name', '')}")
                    st.rerun()

        st.divider()

        with st.expander(" Manual Dependency", expanded=False):
            dep_src = st.text_input("Source repo name", key="dep_src")
            dep_tgt = st.text_input("Target repo name", key="dep_tgt")
            dep_rel = st.selectbox("Relationship", ["depends_on", "imports", "calls", "deploys", "tests", "documents"], key="dep_rel")
            if st.button(" Add Dependency", key="add_dep", disabled=not dep_src.strip() or not dep_tgt.strip()):
                resp = _post("/organization/dependency", {
                    "org_id": org_id,
                    "source_repo": dep_src.strip(),
                    "target_repo": dep_tgt.strip(),
                    "relationship": dep_rel,
                    "weight": 1.0,
                })
                if resp:
                    st.success(f"Dependency added: {dep_src} -> {dep_tgt}")
                    st.rerun()

        st.divider()
        repos_data = _get(f"/organization/repositories?org_id={org_id}")
        if repos_data and repos_data.get("repositories"):
            for r in repos_data["repositories"]:
                with st.expander(f" {r['name']} ({r['category']})"):
                    st.json({
                        "path": r["path"],
                        "language": r["language"],
                        "url": r["url"],
                        "files": r["file_count"],
                        "description": r["description"],
                    })
                    if st.button(f" Index {r['name']}", key=f"idx_{r['id']}"):
                        with st.spinner(f"Indexing {r['name']}..."):
                            resp = _post("/organization/index", {"org_id": org_id})
                            if resp:
                                st.info(f"Indexed. Entities: {resp.get('index_results', {}).get(r['name'], {}).get('entities_found', 0)}")
                                st.rerun()

    # ── Tab 3: Impact Analysis ────────────────────────────────────────────
    with tab_impact:
        st.markdown("### Impact Analysis")
        st.caption("Analyze the impact of a change across all repositories")

        query = st.text_area(
            "What change do you want to make?",
            placeholder='e.g., "Change authentication flow from JWT to OAuth"',
            key="impact_query",
        )
        if st.button(" Analyze Impact", key="run_impact", disabled=not query.strip()):
            with st.spinner("Analyzing impact across repos..."):
                resp = _post("/organization/impact", {"org_id": org_id, "query": query.strip()})
            if resp:
                st.metric("Impact Score", f"{resp.get('impact_score', 0):.1f}/100")
                risk = resp.get("risk_level", "unknown")
                risk_icon = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}.get(risk, "\u2753")
                st.metric("Risk Level", f"{risk_icon} {risk.upper()}")

                repos = resp.get("affected_repos", [])
                if repos:
                    st.markdown("**Affected Repositories:**")
                    for r in repos:
                        st.markdown(f"- {r}")

                files = resp.get("affected_files", [])
                if files:
                    st.markdown("**Affected Files:**")
                    for f in files[:20]:
                        st.markdown(f"- `{f['repo']}/{f['file']}` ({f['type']}, score: {f['match_score']:.1f})")

                recs = resp.get("recommendations", [])
                if recs:
                    st.markdown("**Recommendations:**")
                    for r in recs:
                        st.markdown(f"- {r}")

        st.divider()
        st.markdown("### Recent Impact Reports")
        reports_data = _get(f"/organization/report?org_id={org_id}")
        if reports_data and reports_data.get("impact_reports"):
            for rp in reports_data["impact_reports"][:10]:
                with st.expander(f" {rp.get('query', '')[:50]}... (Score: {rp.get('impact_score', 0):.1f})"):
                    st.json({
                        "risk": rp.get("risk_level"),
                        "repos": len(rp.get("affected_repos", [])),
                        "files": len(rp.get("affected_files", [])),
                    })

    # ── Tab 4: Cross-Repo Changes ─────────────────────────────────────────
    with tab_changes:
        st.markdown("### Coordinated Changes")
        st.caption("Plan and apply changes across multiple repositories")

        with st.expander(" New Coordinated Change", expanded=True):
            change_desc = st.text_area("Description", placeholder="What this change does across repos", key="change_desc")
            st.caption("Specify file changes per repo (repo_name -> file_path -> content)")
            st.info("Format: one repo per line in the format `repo_name:file_path|content`")
            change_input = st.text_area(
                "Repos and files",
                placeholder="e.g.\nfrontend-web:src/config.ts|export const API_URL = '...'\nbackend-api:app/config.py|API_URL = '...'",
                height=120,
                key="change_input",
            )
            if st.button(" Plan & Apply Change", key="apply_change", disabled=not change_desc.strip() or not change_input.strip()):
                changes: dict[str, dict[str, str]] = {}
                for line in change_input.strip().split("\n"):
                    line = line.strip()
                    if ":" not in line:
                        continue
                    repo_part, _, content_part = line.partition(":")
                    if "|" in content_part:
                        fpath, fcontent = content_part.split("|", 1)
                        repo_name = repo_part.strip()
                        if repo_name not in changes:
                            changes[repo_name] = {}
                        changes[repo_name][fpath.strip()] = fcontent
                if changes:
                    with st.spinner("Applying changes..."):
                        resp = _post("/organization/modify", {
                            "org_id": org_id,
                            "description": change_desc.strip(),
                            "changes": changes,
                        })
                    if resp:
                        st.success(f"Change applied: {resp.get('status', '')}")
                        st.json({k: v.get("status", "") for k, v in resp.get("changes", {}).items()})
                else:
                    st.error("Could not parse any file changes.")

        st.divider()
        changes_data = _get(f"/organization/changes?org_id={org_id}")
        if changes_data and changes_data.get("changes"):
            st.markdown("### Recent Changes")
            for ch in changes_data["changes"]:
                with st.expander(f" {ch.get('description', '')[:60]}... ({ch.get('status', '')})"):
                    st.json(ch)

    # ── Tab 5: Validation ─────────────────────────────────────────────────
    with tab_validate:
        st.markdown("### Cross-Repo Validation")
        st.caption("Validate API compatibility, shared libraries, schemas, deployment, and docs")

        validate_types = st.multiselect(
            "Validation types",
            ["api_compatibility", "shared_libraries", "schema_compatibility", "deployment_consistency", "documentation_coverage"],
            default=["api_compatibility", "schema_compatibility"],
            key="validate_types",
        )
        if st.button(" Run Validation", key="run_validate"):
            with st.spinner("Running validations..."):
                resp = _post("/organization/validate", {
                    "org_id": org_id,
                    "validation_types": validate_types if validate_types else None,
                })
            if resp:
                results = resp.get("results", {})
                for vtype, vresult in results.items():
                    passed = vresult.get("passed", False)
                    icon = "\u2705" if passed else "\u274c"
                    with st.expander(f"{icon} {vtype.replace('_', ' ').title()} — {'PASS' if passed else 'FAIL'}"):
                        issues = vresult.get("issues", [])
                        if issues:
                            for iss in issues:
                                st.warning(iss.get("message", ""))
                        else:
                            st.success("No issues found")
