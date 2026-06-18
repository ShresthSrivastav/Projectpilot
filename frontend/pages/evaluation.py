"""Evaluation Center — history, trends, regressions, leaderboards, and version comparisons."""
import os
from datetime import datetime
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


def show_evaluation_tab():
    st.markdown("## Evaluation Center")
    st.caption("Continuous Autonomous Evaluation — track, compare, and improve platform performance")

    tab_history, tab_trends, tab_regressions, tab_leaderboards, tab_comparisons = st.tabs([
        " History", " Trends", " Regressions", " Leaderboards", " Comparisons",
    ])

    with tab_history:
        _show_history_tab()
    with tab_trends:
        _show_trends_tab()
    with tab_regressions:
        _show_regressions_tab()
    with tab_leaderboards:
        _show_leaderboards_tab()
    with tab_comparisons:
        _show_comparisons_tab()


def _severity_color(severity: str) -> str:
    return {
        "high": "🔴",
        "critical": "🚨",
        "medium": "🟡",
        "low": "🟢",
    }.get(severity, "⚪")


def _delta_icon(val: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "↑" if val > 0 else ("↓" if val < 0 else "→")
    return "↓" if val > 0 else ("↑" if val < 0 else "→")


def _format_dt(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16]


# ── History Tab ──────────────────────────────────────────────────────────────

def _show_history_tab():
    st.markdown("### Evaluation Runs")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        schedule_filter = st.selectbox("Schedule", ["All", "nightly", "weekly", "release", "on_demand"], key="eval_hist_sched")
    with col2:
        status_filter = st.selectbox("Status", ["All", "pending", "running", "completed", "failed"], key="eval_hist_status")
    with col3:
        search_id = st.text_input("Search Run ID", key="eval_hist_search")

    params = []
    if schedule_filter != "All":
        params.append(f"trigger_type={schedule_filter}")
    if status_filter != "All":
        params.append(f"status={status_filter}")
    query = "&".join(params) if params else ""

    data = _get(f"/evaluation/history?{query}") or {}
    runs = data.get("runs", [])

    if search_id:
        runs = [r for r in runs if search_id.lower() in r.get("id", "").lower()]

    if not runs:
        st.info("No evaluation runs found. Trigger a run from the API or wait for scheduled runs.")
        return

    st.caption(f"Showing {len(runs)} run(s)")
    for r in runs:
        run_id = r.get("id", "")
        schedule = r.get("trigger_type", r.get("schedule", "?"))
        status = r.get("status", "?")
        autonomy = r.get("autonomy_score", 0)
        cost = r.get("total_cost", 0)
        runtime = r.get("total_runtime", r.get("avg_runtime_ms", 0))
        started = _format_dt(r.get("started_at"))
        completed = _format_dt(r.get("completed_at"))

        with st.expander(f"**{schedule}** — Score: {autonomy:.2f} — {status.upper()} — {run_id[:8]}..."):
            c1, c2, c3 = st.columns(3)
            c1.metric("Autonomy Score", f"{autonomy:.3f}")
            c2.metric("Total Cost", f"${cost:.2f}" if isinstance(cost, (int, float)) else str(cost))
            c3.metric("Avg Runtime", f"{runtime:.0f}ms" if isinstance(runtime, (int, float)) else str(runtime))
            c1.metric("Success Rate", f"{r.get('success_rate', 0):.1%}")
            c2.metric("Healing Rate", f"{r.get('healing_rate', 0):.1%}")
            c3.metric("Deployment Rate", f"{r.get('deployment_success_rate', 0):.1%}")
            st.text(f"Run ID: {run_id}")
            st.text(f"Started: {started}  |  Completed: {completed}")
            if r.get("error"):
                st.error(r["error"])


# ── Trends Tab ───────────────────────────────────────────────────────────────

def _show_trends_tab():
    st.markdown("### Performance Trends")

    data = _get("/evaluation/history?limit=100") or {}
    runs = data.get("runs", [])

    if len(runs) < 2:
        st.info("Not enough data for trend analysis. Complete at least 2 evaluation runs.")
        return

    runs.reverse()
    dates = [_format_dt(r.get("started_at") or r.get("completed_at")) for r in runs]
    autonomy_scores = [r.get("autonomy_score", 0) for r in runs]
    costs = [r.get("total_cost", 0) for r in runs]
    runtimes = [r.get("total_runtime", r.get("avg_runtime_ms", 0)) for r in runs]
    success_rates = [r.get("success_rate", 0) for r in runs]

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Current Autonomy", f"{autonomy_scores[-1]:.3f}",
                  delta=f"{autonomy_scores[-1] - autonomy_scores[-2]:+.3f}" if len(autonomy_scores) >= 2 else None)
        st.metric("Current Cost", f"${costs[-1]:.2f}",
                  delta=f"{costs[-1] - costs[-2]:+.2f}" if len(costs) >= 2 else None)
    with c2:
        st.metric("Current Runtime", f"{runtimes[-1]:.0f}ms",
                  delta=f"{runtimes[-1] - runtimes[-2]:+.0f}ms" if len(runtimes) >= 2 else None)
        st.metric("Current Success Rate", f"{success_rates[-1]:.1%}",
                  delta=f"{success_rates[-1] - success_rates[-2]:+.1%}" if len(success_rates) >= 2 else None)

    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame({
            "Run": list(range(1, len(runs) + 1)),
            "Date": dates,
            "Autonomy Score": autonomy_scores,
            "Cost ($)": costs,
            "Runtime (ms)": runtimes,
            "Success Rate": success_rates,
        })

        chart1 = alt.Chart(df).mark_line(point=True, color="#4ade80").encode(
            x=alt.X("Run:Q", title="Run #"),
            y=alt.Y("Autonomy Score:Q", scale=alt.Scale(zero=False)),
            tooltip=["Date:N", "Autonomy Score:Q"],
        ).properties(height=250, title="Autonomy Score")
        st.altair_chart(chart1, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            chart2 = alt.Chart(df).mark_line(point=True, color="#f87171").encode(
                x=alt.X("Run:Q", title="Run #"),
                y=alt.Y("Cost ($):Q", scale=alt.Scale(zero=False)),
                tooltip=["Date:N", "Cost ($):Q"],
            ).properties(height=200, title="Cost")
            st.altair_chart(chart2, use_container_width=True)
        with c2:
            chart3 = alt.Chart(df).mark_line(point=True, color="#60a5fa").encode(
                x=alt.X("Run:Q", title="Run #"),
                y=alt.Y("Runtime (ms):Q", scale=alt.Scale(zero=False)),
                tooltip=["Date:N", "Runtime (ms):Q"],
            ).properties(height=200, title="Runtime")
            st.altair_chart(chart3, use_container_width=True)

        chart4 = alt.Chart(df).mark_line(point=True, color="#fcd34d").encode(
            x=alt.X("Run:Q", title="Run #"),
            y=alt.Y("Success Rate:Q", scale=alt.Scale(zero=False)),
            tooltip=["Date:N", "Success Rate:Q"],
        ).properties(height=250, title="Success Rate")
        st.altair_chart(chart4, use_container_width=True)

    except ImportError:
        st.info("Install pandas and altair for chart visualization: pip install pandas altair")
        st.markdown("#### Raw Data")
        for r in runs[-10:]:
            st.text(f"{_format_dt(r.get('started_at'))} — Score: {r.get('autonomy_score', 0):.3f} — Cost: ${r.get('total_cost', 0):.2f}")


# ── Regressions Tab ──────────────────────────────────────────────────────────

def _show_regressions_tab():
    st.markdown("### Regressions & Alerts")

    categories_resp = _get("/evaluation/leaderboards") or {}
    all_categories = categories_resp.get("categories", [])
    category_list = ["All"] + all_categories

    col1, col2 = st.columns(2)
    with col1:
        cat_filter = st.selectbox("Category", category_list, key="eval_reg_cat")
    with col2:
        sev_filter = st.selectbox("Severity", ["All", "critical", "high", "medium", "low"], key="eval_reg_sev")

    params = []
    if cat_filter != "All":
        params.append(f"category={cat_filter}")
    if sev_filter != "All":
        params.append(f"severity={sev_filter}")
    query = "&".join(params) if params else ""

    data = _get(f"/evaluation/regressions?{query}") or {}
    regressions = data.get("regressions", [])

    if not regressions:
        st.success("No regressions detected. All metrics are healthy.")
        return

    st.caption(f"Found {len(regressions)} regression(s)")

    for reg in regressions:
        severity = reg.get("severity", "low")
        category = reg.get("category", "general")
        metric = reg.get("metric", "")
        prev_val = reg.get("previous_value", 0)
        curr_val = reg.get("current_value", 0)
        change = reg.get("change_pct", 0)
        dismissed = reg.get("dismissed", False)
        created = _format_dt(reg.get("created_at"))
        reg_id = reg.get("id", "")
        desc = reg.get("description", reg.get("title", ""))

        color = _severity_color(severity)
        label = f"{color} **{severity.upper()}** — {category} — {metric} ({change:+.1f}%)"
        if dismissed:
            label = f"~~{label}~~ (dismissed)"

        with st.expander(label):
            c1, c2, c3 = st.columns(3)
            c1.metric("Previous", f"{prev_val:.4f}" if isinstance(prev_val, float) else str(prev_val))
            c2.metric("Current", f"{curr_val:.4f}" if isinstance(curr_val, float) else str(curr_val))
            c3.metric("Change", f"{change:+.1f}%")
            if desc:
                st.text(f"Details: {desc}")
            st.text(f"Detected: {created}  |  ID: {reg_id}")

            if not dismissed:
                if st.button("Dismiss", key=f"dismiss_{reg_id}"):
                    from database.memory_store import mem_update_regression
                    mem_update_regression(reg_id, {"dismissed": True})
                    st.success("Regression dismissed")
                    st.rerun()


# ── Leaderboards Tab ─────────────────────────────────────────────────────────

def _show_leaderboards_tab():
    st.markdown("### Leaderboards")

    lb_tab_models, lb_tab_agents, lb_tab_workflows, lb_tab_benchmarks = st.tabs([
        " Models", " Agents", " Workflows", " Benchmark Packs",
    ])

    with lb_tab_models:
        _show_leaderboard_table("model")
    with lb_tab_agents:
        _show_leaderboard_table("agent")
    with lb_tab_workflows:
        _show_leaderboard_table("workflow")
    with lb_tab_benchmarks:
        _show_leaderboard_table("benchmark")


def _show_leaderboard_table(category: str):
    sort_by = st.selectbox(
        "Sort by", ["score", "autonomy_score", "reliability_score", "cost_efficiency"],
        key=f"eval_lb_sort_{category}",
    )
    data = _get(f"/evaluation/leaderboards?category={category}&sort_by={sort_by}&limit=50") or {}
    entries = data.get("entries", [])

    if not entries:
        st.info(f"No leaderboard entries for category '{category}'.")
        return

    st.markdown("| Rank | Name | Score | Autonomy | Reliability | Cost Eff. | Runs |")
    st.markdown("|------|------|-------|----------|-------------|-----------|------|")
    for i, entry in enumerate(entries[:50], 1):
        name = entry.get("entry_name", "?")
        score = entry.get("score", 0)
        autonomy = entry.get("autonomy_score", 0)
        reliability = entry.get("reliability_score", 0)
        cost_eff = entry.get("cost_efficiency", 0)
        run_count = entry.get("run_count", 0)
        st.markdown(
            f"| #{i} | {name} | **{score:.2f}** | {autonomy:.2f} | {reliability:.2f} | {cost_eff:.2f} | {run_count} |"
        )


# ── Comparisons Tab ──────────────────────────────────────────────────────────

def _show_comparisons_tab():
    st.markdown("### Version Comparisons")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        from_ver = st.text_input("From Version", "v11.0", key="eval_cmp_from")
    with col2:
        to_ver = st.text_input("To Version", "v12.0", key="eval_cmp_to")
    with col3:
        limit = st.number_input("Limit", min_value=1, max_value=100, value=20, key="eval_cmp_limit")

    data = _get(f"/evaluation/comparison?from_version={from_ver}&to_version={to_ver}&limit={limit}") or {}
    comparisons = data.get("comparisons", [])

    if comparisons:
        st.caption(f"Found {len(comparisons)} comparison(s)")
        for cmp in comparisons:
            from_v = cmp.get("from_version", "?")
            to_v = cmp.get("to_version", "?")
            created = _format_dt(cmp.get("created_at"))
            summary = cmp.get("summary", "")

            with st.expander(f"**{from_v} → {to_v}** — {created}"):
                if summary:
                    st.markdown(f"**Summary:** {summary}")

                deltas = [
                    ("Autonomy", cmp.get("autonomy_delta", 0), True),
                    ("Execution Time", cmp.get("execution_time_delta", 0), False),
                    ("Healing", cmp.get("healing_delta", 0), True),
                    ("Deployment", cmp.get("deployment_delta", 0), True),
                    ("Cost Efficiency", cmp.get("cost_efficiency_delta", 0), True),
                    ("Success Rate", cmp.get("success_rate_delta", 0), True),
                    ("Benchmark", cmp.get("benchmark_delta", 0), True),
                ]

                for label, val, higher_better in deltas:
                    icon = _delta_icon(val, higher_better)
                    color = "green" if (higher_better and val > 0) or (not higher_better and val < 0) else "red"
                    st.markdown(
                        f"<span style='color:{color}'>{icon} **{label}**: {val:+.2f}%</span>",
                        unsafe_allow_html=True,
                    )
    else:
        st.info("No comparisons found. Record version snapshots and run comparisons via the API.")

    st.divider()
    st.markdown("### Trigger New Comparison")
    st.caption("Record a version snapshot from the latest evaluation run")
    if st.button("Refresh Comparisons", key="eval_cmp_refresh"):
        st.rerun()
