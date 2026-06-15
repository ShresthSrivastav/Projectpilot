"""Ecosystem Dashboard — Plugin & Agent SDK Manager, Marketplace Browser, Workflow Manager."""
import os
import time
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def _get(path: str, timeout: int = 10) -> Optional[Dict]:
    try:
        r = requests.get(f"{BACKEND}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _post(path: str, data: Any, timeout: int = 30) -> Optional[Dict]:
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


def show_ecosystem_tab():
    st.markdown("## Plugin & Agent SDK Ecosystem")
    st.caption("Extend the platform with custom plugins, agents, workflows, and benchmark packs")

    tab_plugins, tab_marketplace, tab_agents, tab_workflows, tab_health = st.tabs([
        " Plugin Manager", " Marketplace", " Custom Agents", " Workflows", " Health",
    ])

    with tab_plugins:
        _show_plugin_manager()
    with tab_marketplace:
        _show_marketplace_browser()
    with tab_agents:
        _show_agent_manager()
    with tab_workflows:
        _show_workflow_manager()
    with tab_health:
        _show_ecosystem_health()


def _show_plugin_manager():
    st.markdown("### Plugin Manager")
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        source = st.text_input("Plugin Source (path to .py or plugin.yaml)", placeholder="/path/to/plugin.py")
    with col2:
        pname = st.text_input("Plugin Name (optional)", placeholder="my-plugin")
    with col3:
        ptype = st.selectbox("Type", ["tool", "integration", "provider", "validator", "workflow"], key="plugin_type_sel")

    if st.button(" Install Plugin") and source:
        data = {"source": source, "plugin_type": ptype}
        if pname:
            data["name"] = pname
        result = _post("/plugins/install", data)
        if result:
            st.success(f"Plugin installed: {result.get('manifest', {}).get('name', 'unknown')}")
            st.rerun()

    st.divider()
    st.markdown("#### Installed Plugins")
    plugins_data = _get("/plugins")
    plugins = (plugins_data or {}).get("plugins", [])

    if not plugins:
        st.info("No plugins installed yet")
        return

    for p in plugins:
        manifest = p.get("manifest", {})
        pid = p["id"]
        enabled = p.get("enabled", False)
        cols = st.columns([3, 1, 1, 1])
        with cols[0]:
            st.markdown(f"**{manifest.get('name', 'unknown')}** v{manifest.get('version', '?')}")
            st.caption(manifest.get('description', ''))
        with cols[1]:
            st.caption(manifest.get('plugin_type', ''))
        with cols[2]:
            if enabled:
                if st.button(" Disable", key=f"dis_{pid}"):
                    _post("/plugins/disable", {"plugin_id": pid})
                    st.rerun()
            else:
                if st.button(" Enable", key=f"en_{pid}"):
                    _post("/plugins/enable", {"plugin_id": pid})
                    st.rerun()
        with cols[3]:
            if st.button(" Uninstall", key=f"un_{pid}"):
                _post("/plugins/uninstall", {"plugin_id": pid})
                st.rerun()


def _show_marketplace_browser():
    st.markdown("### Marketplace Browser")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_q = st.text_input("Search packages", placeholder="code quality, deployment, ...", key="mkt_search")
    with col2:
        mkt_type = st.selectbox("Type", ["", "plugin", "agent", "workflow", "benchmark"], key="mkt_type")
    with col3:
        sort_by = st.selectbox("Sort by", ["downloads", "rating", "name", "updated"], key="mkt_sort")

    if search_q or mkt_type:
        params = {"query": search_q, "sort_by": sort_by}
        if mkt_type:
            params["package_type"] = mkt_type
        mkt_data = _get("/plugins/marketplace", params)
    else:
        mkt_data = _get("/plugins/marketplace/list")

    packages = (mkt_data or {}).get("packages", [])

    if not packages:
        st.info("No packages found")
    else:
        st.caption(f"Showing {len(packages)} package(s)")
        for pkg in packages:
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                st.markdown(f"**{pkg.get('name', 'unknown')}** v{pkg.get('version', '?')}")
                st.caption(pkg.get('description', ''))
            with cols[1]:
                st.caption(f"⭐ {pkg.get('rating', 0):.1f} ({pkg.get('rating_count', 0)})")
            with cols[2]:
                st.caption(f"⬇ {pkg.get('downloads', 0)}")
            with cols[3]:
                if st.button(" Install", key=f"mkt_install_{pkg['id']}"):
                    result = _post("/plugins/marketplace/install", {"package_id": pkg["id"]})
                    if result:
                        st.success(f"Installed at {result.get('installed_at', '?')}")
                        st.rerun()

    st.divider()
    st.markdown("#### Publish a Package")
    with st.expander("Publish New Package"):
        col1, col2 = st.columns(2)
        with col1:
            pub_name = st.text_input("Name", key="pub_name")
            pub_ver = st.text_input("Version", "1.0.0", key="pub_ver")
            pub_author = st.text_input("Author", key="pub_author")
        with col2:
            pub_desc = st.text_input("Description", key="pub_desc")
            pub_type = st.selectbox("Type", ["plugin", "agent", "workflow", "benchmark"], key="pub_type")
            pub_path = st.text_input("Source Path", key="pub_path")
        if st.button(" Publish") and pub_name and pub_path:
            result = _post("/plugins/marketplace/publish", {
                "name": pub_name, "version": pub_ver, "author": pub_author,
                "description": pub_desc, "source_path": pub_path, "package_type": pub_type,
            })
            if result:
                st.success(f"Published: {result.get('name')}")
                st.rerun()


def _show_agent_manager():
    st.markdown("### Custom Agent Manager")
    with st.expander("Register New Agent"):
        col1, col2 = st.columns(2)
        with col1:
            agent_name = st.text_input("Agent Name", key="agent_name")
            agent_ver = st.text_input("Version", "1.0.0", key="agent_ver")
            agent_source = st.text_input("Source Path (.py)", key="agent_source")
        with col2:
            agent_desc = st.text_input("Description", key="agent_desc")
            agent_caps = st.text_area("Capabilities (JSON array)", '[{"name": "cap1", "description": "..."}]', key="agent_caps")
        if st.button(" Register Agent") and agent_name and agent_source:
            caps = []
            try:
                caps = __import__("json").loads(agent_caps) if agent_caps else []
            except Exception:
                st.warning("Invalid capabilities JSON, using empty")
            result = _post("/agents/register", {
                "name": agent_name, "version": agent_ver, "source": agent_source,
                "description": agent_desc, "capabilities": caps,
            })
            if result:
                st.success(f"Agent registered: {result.get('name')}")
                st.rerun()

    st.divider()
    st.markdown("#### Registered Agents")
    agents_data = _get("/agents/custom")
    agents = (agents_data or {}).get("agents", [])

    if not agents:
        st.info("No custom agents registered")
        return

    for a in agents:
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.markdown(f"**{a.get('name', 'unknown')}** v{a.get('version', '?')}")
            st.caption(a.get('description', ''))
        with cols[1]:
            caps = a.get("capabilities", [])
            st.caption(f"{len(caps)} capability(ies)")
        with cols[2]:
            if st.button(" Delete", key=f"del_agent_{a['id']}"):
                _post("/agents/delete", {"agent_id": a["id"]})
                st.rerun()


def _show_workflow_manager():
    st.markdown("### Workflow Manager")
    with st.expander("Register New Workflow"):
        col1, col2 = st.columns(2)
        with col1:
            wf_name = st.text_input("Workflow Name", key="wf_name")
            wf_ver = st.text_input("Version", "1.0.0", key="wf_ver")
            wf_source = st.text_input("Source Path", key="wf_source")
        with col2:
            wf_desc = st.text_input("Description", key="wf_desc")
            wf_steps = st.text_area("Steps (JSON array)", '[{"name": "step1", "deps": []}]', key="wf_steps")
        if st.button(" Register Workflow") and wf_name and wf_source:
            steps = []
            try:
                steps = __import__("json").loads(wf_steps) if wf_steps else []
            except Exception:
                st.warning("Invalid steps JSON, using empty")
            result = _post("/workflows/register", {
                "name": wf_name, "version": wf_ver, "source": wf_source,
                "description": wf_desc, "steps": steps,
            })
            if result:
                st.success(f"Workflow registered: {result.get('name')}")
                st.rerun()

    st.divider()
    st.markdown("#### Registered Workflows")
    wf_data = _get("/workflows")
    workflows = (wf_data or {}).get("workflows", [])

    if not workflows:
        st.info("No custom workflows registered")
        return

    for w in workflows:
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.markdown(f"**{w.get('name', 'unknown')}** v{w.get('version', '?')}")
            st.caption(w.get('description', ''))
        with cols[1]:
            steps = w.get("steps", [])
            st.caption(f"{len(steps)} step(s)")
        with cols[2]:
            if st.button(" Delete", key=f"del_wf_{w['id']}"):
                _post("/workflows/delete", {"workflow_id": w["id"]})
                st.rerun()


def _show_ecosystem_health():
    st.markdown("### Ecosystem Health")
    health = _get("/ecosystem/health")
    if not health:
        st.warning("Could not fetch ecosystem health")
        return

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Plugins Installed", health.get("plugins_installed", 0))
    with col2:
        st.metric("Plugins Enabled", health.get("plugins_enabled", 0))
    with col3:
        st.metric("Marketplace Packages", health.get("marketplace_packages", 0))
    with col4:
        st.metric("Custom Agents", health.get("custom_agents", 0))
    with col5:
        st.metric("Custom Workflows", health.get("custom_workflows", 0))

    st.divider()
    st.markdown("### SDK Version")
    st.code("""
    ProjectPilot SDK — Plugin & Agent SDK Ecosystem
    ├── sdk/agent_sdk/      → BaseAgent for custom agents
    ├── sdk/plugin_sdk/     → BasePlugin for custom plugins
    ├── sdk/workflow_sdk/   → BaseWorkflow for custom DAG workflows
    ├── sdk/deployment_sdk/ → BaseDeploymentTarget for custom deploy targets
    ├── sdk/benchmark_sdk/  → BaseBenchmarkPack for custom benchmarks
    ├── sdk/validation_sdk/ → BaseValidator for custom validators
    └── sdk/examples/       → Reference implementations
    """)

    st.markdown("### Quick Start")
    st.code("""# Create a plugin without modifying platform source:
from sdk.plugin_sdk.base_plugin import BasePlugin, PluginManifest

class MyPlugin(BasePlugin):
    def install(self) -> bool: ...
    def uninstall(self) -> bool: ...
    def configure(self, config) -> bool: ...
    def validate(self) -> bool: ...
""", language="python")
