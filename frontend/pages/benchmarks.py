"""Benchmark Dashboard — run, compare, and track autonomy scores."""

import os
from typing import Any

import httpx
import streamlit as st

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def _get(path: str, timeout: int = 10) -> dict | None:
    try:
        r = httpx.get(f"{BACKEND}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _post(path: str, data: Any, timeout: int = 30) -> dict | None:
    try:
        r = httpx.post(f"{BACKEND}{path}", json=data, timeout=timeout)
        if not r.is_success:
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


def show_benchmarks_tab():
    st.markdown("## Benchmark Suite")
    st.caption("Evaluate autonomous software generation across 8 domains")

    tab_run, tab_results, tab_leaderboard, tab_trends = st.tabs(
        [
            " Run",
            " Results",
            " Leaderboard",
            " Trends",
        ]
    )

    with tab_run:
        _show_run_tab()
    with tab_results:
        _show_results_tab()
    with tab_leaderboard:
        _show_leaderboard_tab()
    with tab_trends:
        _show_trends_tab()


def _show_run_tab():
    st.markdown("### Run Benchmark")

    domains_resp = _get("/benchmarks/domains") or {}
    domains = [d["domain"] for d in domains_resp.get("domains", [])]

    if not domains:
        st.info("No benchmark domains found. Ensure benchmarks/ directory exists.")
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        domain = st.selectbox("Domain", domains, key="bm_domain")
    with col2:
        model = st.selectbox("Model", ["local", "cloud"], key="bm_model")

    if st.button("Run Benchmark", key="bm_run_btn", type="primary"):
        with st.spinner(f"Running benchmark for {domain}..."):
            result = _post("/benchmarks/run", {"domain": domain, "model": model, "iteration": 1})
            if result:
                st.success(f"Benchmark started: {result['run_id']}")
                st.code(result, language="json")

    st.divider()
    st.markdown("### Statistics")
    stats = _get("/benchmarks/statistics") or {}
    if stats.get("total_runs", 0) > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Runs", stats.get("total_runs", 0))
        c2.metric("Completed", stats.get("completed_runs", 0))
        c3.metric("Avg Score", f"{stats.get('average_score', 0):.1f}")
        c4.metric("Best Score", f"{stats.get('best_score', 0):.1f}")
        st.caption(f"Best domain: {stats.get('best_domain', 'N/A')} | Tokens: {stats.get('total_tokens', 0):,}")


def _show_results_tab():
    st.markdown("### Results")

    filter_domain = st.text_input("Filter by domain (optional)", key="bm_filter")

    params = {}
    if filter_domain.strip():
        params["domain"] = filter_domain.strip()

    query = "&".join(f"{k}={v}" for k, v in params.items())
    results_resp = _get(f"/benchmarks/results?{query}") or {}
    results = results_resp.get("results", [])

    if not results:
        st.info("No benchmark results yet. Run a benchmark first.")
        return

    for r in results[:20]:
        score = r.get("autonomy_score", 0)
        status = r.get("status", "unknown")
        with st.expander(f"**{r.get('domain', '?')}** — Score: {score}/100 — {status}"):
            c1, c2 = st.columns(2)
            c1.metric("Run ID", r.get("run_id", ""))
            c1.metric("Model", r.get("model", ""))
            c2.metric("Status", status)
            c2.metric("Iteration", r.get("iteration", 1))

            metrics = r.get("metrics", {})
            if metrics:
                st.markdown("#### Metrics")
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Completion", f"{metrics.get('completion_rate', 0):.0f}%")
                mc2.metric("Test Pass", f"{metrics.get('test_pass_rate', 0):.0f}%")
                mc3.metric("Architecture", f"{metrics.get('architecture_quality', 0):.0f}%")
                mc4.metric("Feature Compl.", f"{metrics.get('feature_completeness', 0):.0f}%")
                mc1.metric("Browser Valid.", f"{metrics.get('browser_validation_rate', 0):.0f}%")
                mc2.metric("Deployment", f"{metrics.get('deployment_success_rate', 0):.0f}%")
                mc3.metric("Self-Healing", f"{metrics.get('self_healing_effectiveness', 0):.0f}%")
                mc4.metric("Exec Time", f"{metrics.get('execution_time', 0):.1f}s")

            features = r.get("features_passed", [])
            if features:
                st.markdown(f"**Features Passed:** {', '.join(features[:5])}")
                if len(features) > 5:
                    st.caption(f"... and {len(features) - 5} more")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Export JSON", key=f"bm_json_{r['run_id']}"):
                    report = _get(f"/benchmarks/report/{r['run_id']}?format=json")
                    if report:
                        st.code(report, language="json")
            with col_b:
                if st.button("Export Markdown", key=f"bm_md_{r['run_id']}"):
                    params = {"run_id": r["run_id"], "format": "markdown"}
                    try:
                        rp = httpx.get(f"{BACKEND}/benchmarks/report/{r['run_id']}?format=markdown", timeout=10)
                        if rp.is_success:
                            st.markdown(rp.text)
                    except Exception:
                        st.error("Failed to fetch markdown report")


def _show_leaderboard_tab():
    st.markdown("### Leaderboard")

    domain_filter = st.selectbox(
        "Filter by domain",
        ["All"] + [d["domain"] for d in (_get("/benchmarks/domains") or {}).get("domains", [])],
        key="bm_lb_domain",
    )
    params = ""
    if domain_filter != "All":
        params = f"?domain={domain_filter}"

    lb_resp = _get(f"/benchmarks/leaderboard{params}") or {}
    leaderboard = lb_resp.get("leaderboard", [])

    if not leaderboard:
        st.info("No completed benchmarks to rank.")
        return

    st.markdown("| Rank | Domain | Score | Model | Date |")
    st.markdown("|------|--------|-------|-------|------|")
    for entry in leaderboard[:20]:
        rank = entry.get("rank", "?")
        domain = entry.get("domain", "?")
        score = entry.get("autonomy_score", 0)
        model = entry.get("model", "")
        created = ""
        if entry.get("created_at"):
            from datetime import datetime

            created = datetime.fromtimestamp(entry["created_at"]).strftime("%m-%d %H:%M")
        st.markdown(f"| #{rank} | {domain} | **{score:.1f}** | {model} | {created} |")

    st.divider()
    st.markdown("### Compare Two Runs")
    completed = [e["run_id"] for e in leaderboard[:20]]
    if len(completed) >= 2:
        col1, col2 = st.columns(2)
        with col1:
            run_a = st.selectbox("Run A", completed, key="bm_cmp_a")
        with col2:
            run_b = st.selectbox("Run B", completed, key="bm_cmp_b")

        if st.button("Compare", key="bm_cmp_btn"):
            cmp = _post("/benchmarks/compare", {"run_id_1": run_a, "run_id_2": run_b})
            if cmp:
                st.markdown("#### Score Difference")
                diff = cmp.get("score_difference", 0)
                direction = "↑ improved" if diff > 0 else "↓ regressed"
                st.metric(f"Run B vs Run A ({direction})", f"{diff:+.1f}")

                st.markdown("#### Metrics Comparison")
                diffs = cmp.get("differences", {})
                for key, val in diffs.items():
                    label = key.replace("_", " ").title()
                    st.metric(label, f"{val:+.2f}" if isinstance(val, float) else val)


def _show_trends_tab():
    st.markdown("### Autonomy Score Trends")

    domain_filter = st.selectbox(
        "Filter by domain",
        ["All"] + [d["domain"] for d in (_get("/benchmarks/domains") or {}).get("domains", [])],
        key="bm_tr_domain",
    )
    params = ""
    if domain_filter != "All":
        params = f"?domain={domain_filter}"

    trends = _get(f"/benchmarks/trends{params}") or {}

    if not trends.get("autonomy_scores"):
        st.info("Not enough data for trend analysis. Complete a few benchmarks first.")
        return

    st.markdown(f"**Improvement Rate:** {trends.get('improvement_rate', 0):+.1f}%")

    data = {
        "Date": trends.get("dates", []),
        "Autonomy Score": trends.get("autonomy_scores", []),
        "Completion Rate": trends.get("completion_rates", []),
        "Test Pass Rate": trends.get("test_pass_rates", []),
    }

    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame(data)
        if not df.empty:
            chart = (
                alt.Chart(df)
                .mark_line(point=True)
                .encode(
                    x="Date:T",
                    y=alt.Y("Autonomy Score:Q", scale=alt.Scale(zero=False)),
                    tooltip=["Date:T", "Autonomy Score:Q", "Completion Rate:Q", "Test Pass Rate:Q"],
                )
                .properties(height=400)
            )
            st.altair_chart(chart, use_container_width=True)
    except ImportError:
        st.info("Install pandas and altair for chart visualization: pip install pandas altair")

    st.markdown("#### Recent Scores")
    for i, (date, score) in enumerate(
        zip(
            trends.get("dates", [])[-10:],
            trends.get("autonomy_scores", [])[-10:],
        )
    ):
        st.text(f"{date[:10]} — {score:.1f}")
