"""
Streamlit UI  (ui/app.py)

Business-user interface for the Text-to-Insights system.

Screens:
  1. Query          — Enter a question, view report + data table + SQL
  2. Query History  — Paginated past queries for the logged-in user
  3. Schema Browser — Explore registered tables and value mappings

Launch:
    streamlit run ui/app.py
"""
from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Text-to-Insights | Telecom Analytics",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Session state helpers ──────────────────────────────────────────────────────

def _token() -> str | None:
    return st.session_state.get("token")


def _headers() -> dict:
    tok = _token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _is_logged_in() -> bool:
    return bool(_token())


# ── Auth sidebar ───────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.title("📡 Text-to-Insights")
        st.caption("Telecom Analytics — Local AI")
        st.divider()

        if not _is_logged_in():
            st.subheader("Login")
            username = st.text_input("Username", value="analyst")
            password = st.text_input("Password", type="password", value="analyst123")
            if st.button("Login", type="primary", use_container_width=True):
                _do_login(username, password)
        else:
            st.success(f"Logged in as **{st.session_state.get('user_id', '?')}**")
            if st.button("Logout", use_container_width=True):
                for k in ["token", "user_id"]:
                    st.session_state.pop(k, None)
                st.rerun()

        st.divider()
        st.caption("Models")
        st.info(
            "SQL: `sqlcoder`  \nReport: `mistral`  \nHost: Ollama (local)",
            icon="🤖",
        )


def _do_login(username: str, password: str) -> None:
    try:
        r = requests.post(
            f"{API_BASE}/auth/token",
            data={"username": username, "password": password},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            st.session_state["token"] = data["access_token"]
            st.session_state["user_id"] = username
            st.success("Logged in!")
            st.rerun()
        else:
            st.error(f"Login failed: {r.json().get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to the API. Is it running?")


# ── Pages ──────────────────────────────────────────────────────────────────────

def page_query() -> None:
    st.header("🔍 Ask a Business Question")
    st.caption("Type a plain-English question about your telecom metrics.")

    # Example questions
    with st.expander("💡 Example questions"):
        examples = [
            "How many active customers are in the DFW region?",
            "What is the average ARPU by region for the last 3 months?",
            "Show me open critical priority tickets in New York",
            "What is the churn rate breakdown by reason code?",
            "Which network nodes had the highest packet loss last week?",
            "Compare revenue between Fiber and Wireless in Chicago vs Dallas",
        ]
        for ex in examples:
            if st.button(ex, key=ex):
                st.session_state["question_input"] = ex

    question = st.text_area(
        "Your question",
        value=st.session_state.get("question_input", ""),
        height=80,
        placeholder="e.g. How many active customers are in DFW?",
        key="question_input",
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        top_k = st.selectbox("Tables to consider", [2, 3, 4], index=1)
    with col2:
        st.write("")  # spacer

    if st.button("Run Query", type="primary", disabled=not question.strip()):
        if not _is_logged_in():
            st.warning("Please log in first.")
            return
        _run_query(question.strip(), top_k)


def _run_query(question: str, top_k: int) -> None:
    with st.spinner("Running pipeline: Table Retrieval → SQL Generation → Execution → Report …"):
        try:
            r = requests.post(
                f"{API_BASE}/query",
                json={"question": question, "top_k_tables": top_k},
                headers=_headers(),
                timeout=180,
            )
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to the API. Is it running?")
            return
        except requests.exceptions.Timeout:
            st.error("Request timed out. The model may be loading — please retry.")
            return

    if r.status_code != 200:
        detail = r.json().get("detail", r.text)
        st.error(f"Error ({r.status_code}): {detail}")
        return

    data = r.json()
    st.success(f"Query complete — {data['row_count']} rows in {data['execution_time_ms']:.0f} ms")

    # ── Report ──────────────────────────────────────────────────────
    st.subheader("📋 Report")
    st.markdown(data["report"])

    if data.get("truncated"):
        st.warning(f"Results truncated to {data['row_count']} rows.")

    # ── Data table ──────────────────────────────────────────────────
    if data["markdown_table"]:
        st.subheader("📊 Data")
        lines = data["markdown_table"].strip().split("\n")
        if len(lines) >= 3:
            headers = [h.strip() for h in lines[0].strip("|").split("|")]
            rows = []
            for line in lines[2:]:
                cells = [c.strip() for c in line.strip("|").split("|")]
                rows.append(cells)
            if rows:
                df = pd.DataFrame(rows, columns=headers)
                st.dataframe(df, use_container_width=True)

    # ── Debug info ──────────────────────────────────────────────────
    with st.expander("🔧 Pipeline details"):
        st.markdown(f"**Query ID:** `{data['query_id']}`")
        st.markdown(f"**Tables used:** `{', '.join(data['selected_tables'])}`")

        if data["value_mappings"]:
            st.markdown("**Value mappings applied:**")
            for m in data["value_mappings"]:
                st.markdown(
                    f"  - `{m['original_phrase']}` → "
                    f"`{m['table_name']}.{m['column_name']} = '{m['internal_code']}'`"
                )

        if data.get("validation_warnings"):
            for w in data["validation_warnings"]:
                st.info(f"ℹ️ {w}")

        st.markdown("**Generated SQL:**")
        st.code(data["generated_sql"], language="sql")


def page_history() -> None:
    st.header("🕐 Query History")
    if not _is_logged_in():
        st.warning("Please log in to view your query history.")
        return

    page = st.number_input("Page", min_value=1, value=1, step=1)
    try:
        r = requests.get(
            f"{API_BASE}/query/history",
            params={"page": page, "page_size": 20},
            headers=_headers(),
            timeout=15,
        )
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to the API.")
        return

    if r.status_code != 200:
        st.error(f"Error: {r.json().get('detail', r.text)}")
        return

    data = r.json()
    st.caption(f"Showing page {page} of {max(1, (data['total'] + 19) // 20)} ({data['total']} total)")

    for rec in data["records"]:
        with st.container(border=True):
            col1, col2, col3 = st.columns([5, 1, 2])
            with col1:
                st.markdown(f"**{rec['question']}**")
            with col2:
                status_icon = "✅" if rec["status"] == "SUCCESS" else "❌"
                st.markdown(f"{status_icon} {rec['status']}")
            with col3:
                st.caption(rec["created_at"][:19].replace("T", " "))
                st.caption(f"{rec['row_count']} rows")


def page_schema() -> None:
    st.header("🗄️ Schema Browser")
    if not _is_logged_in():
        st.warning("Please log in to browse the schema.")
        return

    domain_filter = st.selectbox(
        "Filter by domain", ["(all)", "customer", "network", "billing"], index=0
    )
    params = {}
    if domain_filter != "(all)":
        params["domain"] = domain_filter

    try:
        r = requests.get(
            f"{API_BASE}/schema/tables", params=params, headers=_headers(), timeout=15
        )
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to the API.")
        return

    if r.status_code != 200:
        st.error(f"Error: {r.json().get('detail', r.text)}")
        return

    data = r.json()
    st.caption(f"{data['total']} registered tables")

    for tbl in data["tables"]:
        with st.expander(f"**{tbl['table_name']}** — {tbl['description']}", expanded=False):
            st.markdown(f"**Domain:** `{tbl['domain']}` | **Columns:** {tbl['column_count']}")

            if tbl["columns"]:
                col_data = []
                for c in tbl["columns"]:
                    col_data.append({
                        "Column": c["name"],
                        "Type": c["type"],
                        "Description": c["description"],
                        "Metric": "✓" if c["is_metric"] else "",
                        "Dimension": "✓" if c["is_dimension"] else "",
                    })
                st.dataframe(pd.DataFrame(col_data), use_container_width=True, hide_index=True)

            # Value mappings
            try:
                rv = requests.get(
                    f"{API_BASE}/schema/values/{tbl['table_name']}",
                    headers=_headers(), timeout=10
                )
                if rv.status_code == 200:
                    vdata = rv.json()
                    if vdata["curated_values"]:
                        st.markdown("**Value mappings:**")
                        vdf = pd.DataFrame(vdata["curated_values"])
                        st.dataframe(vdf, use_container_width=True, hide_index=True)
                    if vdata["flagged_unknown"]:
                        st.warning(
                            f"⚠️ {len(vdata['flagged_unknown'])} unknown values need curation"
                        )
            except Exception:
                pass


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    render_sidebar()

    if not _is_logged_in():
        st.info("👈 Log in using the sidebar to get started.")
        st.markdown(
            """
            ## Welcome to Text-to-Insights
            Query your telecom metrics server in plain English.
            No SQL knowledge required.

            **Demo credentials:**
            - `analyst` / `analyst123`
            - `admin` / `admin123`
            """
        )
        return

    tab_query, tab_history, tab_schema = st.tabs(["🔍 Query", "🕐 History", "🗄️ Schema"])

    with tab_query:
        page_query()
    with tab_history:
        page_history()
    with tab_schema:
        page_schema()


if __name__ == "__main__":
    main()
