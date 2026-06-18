"""Analytics Dashboard — charts, metrics, and project history."""
import os

import altair as alt
import pandas as pd
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


def show_analytics_tab():
    st.markdown("## Analytics Dashboard")

    overview = _get("/analytics/overview") or {}
    projects_data = _get("/analytics/projects")
    projects: list[dict] = (projects_data or {}).get("projects", [])

    if not projects:
        st.info("No analytics data yet. Generate a project to see stats here.")
        return

    total_projects = len(projects)
    total_files = overview.get("total_files", sum(p.get("file_count", 0) for p in projects))
    total_tests = overview.get("total_tests", sum(p.get("test_count", 0) for p in projects))
    total_tokens = overview.get("total_tokens", sum(p.get("token_usage", 0) for p in projects))
    avg_dur = overview.get("avg_duration_ms", 0) or 0

    st.markdown("### Overview")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Projects", total_projects)
    with c2:
        st.metric("Files", total_files)
    with c3:
        st.metric("Tests", total_tests)
    with c4:
        st.metric("Total Tokens", f"{total_tokens:,}")
    with c5:
        st.metric("Avg Duration", f"{int(avg_dur/1000)}s" if avg_dur else "N/A")

    st.divider()
    st.markdown("### Duration per Project")

    df = pd.DataFrame(projects)
    if not df.empty and "total_duration_ms" in df.columns:
        df["duration_s"] = (df["total_duration_ms"].fillna(0) / 1000).astype(int)
        df["label"] = df.apply(lambda r: r.get("project_name", "?")[:20], axis=1)
        chart = alt.Chart(df).mark_bar(color="#4C78A8").encode(
            x=alt.X("label:N", sort="-y", title=""),
            y=alt.Y("duration_s:Q", title="Duration (s)"),
            tooltip=["label", "duration_s", "model_used", "status"],
        ).properties(height=250)
        st.altair_chart(chart, use_container_width=True)

    st.markdown("### Token Usage per Project")
    if not df.empty and "token_usage" in df.columns:
        chart2 = alt.Chart(df).mark_bar(color="#F58518").encode(
            x=alt.X("label:N", sort="-y", title=""),
            y=alt.Y("token_usage:Q", title="Tokens"),
            tooltip=["label", "token_usage"],
        ).properties(height=250)
        st.altair_chart(chart2, use_container_width=True)

    st.markdown("### Files per Project")
    if not df.empty and "file_count" in df.columns:
        chart3 = alt.Chart(df).mark_bar(color="#54A24B").encode(
            x=alt.X("label:N", sort="-y", title=""),
            y=alt.Y("file_count:Q", title="Files"),
            tooltip=["label", "file_count"],
        ).properties(height=250)
        st.altair_chart(chart3, use_container_width=True)

    st.markdown("### Test Results by Project")
    if not df.empty and "test_count" in df.columns and "test_passed" in df.columns:
        df_tests = df[df["test_count"] > 0].copy()
        if not df_tests.empty:
            df_tests["test_failed_adj"] = df_tests["test_count"] - df_tests["test_passed"]
            df_long = df_tests.melt(
                id_vars=["label"],
                value_vars=["test_passed", "test_failed_adj"],
                var_name="result", value_name="count",
            )
            df_long["result"] = df_long["result"].map({"test_passed": "Passed", "test_failed_adj": "Failed"})
            chart4 = alt.Chart(df_long).mark_bar().encode(
                x=alt.X("label:N", title=""),
                y=alt.Y("count:Q", title="Tests"),
                color=alt.Color("result:N", scale=alt.Scale(
                    domain=["Passed", "Failed"], range=["#27ae60", "#e74c3c"]
                )),
                tooltip=["label", "result", "count"],
            ).properties(height=250)
            st.altair_chart(chart4, use_container_width=True)

    st.markdown("### Project Details")
    for p in projects:
        name = p.get("project_name", "Unnamed")
        status = p.get("status", "unknown")
        dur = p.get("total_duration_ms", 0)
        tokens = p.get("token_usage", 0)
        files_c = p.get("file_count", 0)
        tests_total = p.get("test_count", 0)
        tests_passed = p.get("test_passed", 0)
        model = p.get("model_used", "N/A")
        created = p.get("created_at", "")[:16].replace("T", " ")
        icon = {"complete": "\u2705", "failed": "\u274c", "cancelled": "\U0001f6ab", "running": "\U0001f504"}.get(status, "\u2022")
        with st.expander(f"{icon} **{name}** \u2014 {created}"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Duration", f"{int(dur/1000)}s" if dur else "N/A")
            c2.metric("Tokens", f"{tokens:,}" if tokens else "N/A")
            c3.metric("Files", files_c)
            c4.metric("Tests", f"{tests_passed}/{tests_total}" if tests_total else "N/A")
            st.caption(f"Model: `{model}` | Status: {status} | Job: `{p.get('job_id', '')[:16]}\u2026`")
