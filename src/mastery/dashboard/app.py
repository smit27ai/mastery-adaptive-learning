"""Instructor dashboard.

Streamlit rather than React on purpose: this view is information-dense and will grow
SHAP waterfalls, cluster plots and drift charts, all of which are one line of Python
here and a whole rendering pipeline anywhere else.

Run with:  make dashboard
"""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("MASTERY_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Mastery - Instructor", page_icon="MA", layout="wide")


def api_get(path: str, token: str, **params: str | int | float) -> object:
    response = httpx.get(
        f"{API_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()


def login(email: str, password: str) -> dict:
    response = httpx.post(
        f"{API_URL}/auth/login", json={"email": email, "password": password}, timeout=15.0
    )
    response.raise_for_status()
    return dict(response.json())


st.title("Mastery - Instructor Dashboard")

with st.sidebar:
    st.header("Sign in")
    email = st.text_input("Email", value="instructor@demo.local")
    password = st.text_input("Password", value="demo12345", type="password")
    if st.button("Sign in", use_container_width=True):
        try:
            st.session_state["auth"] = login(email, password)
        except httpx.HTTPError as exc:
            st.error(f"Login failed: {exc}")

    st.divider()
    st.caption(f"API: {API_URL}")
    try:
        health = httpx.get(f"{API_URL}/health", timeout=5.0).json()
        st.success(f"API up - model {health['version']}")
    except httpx.HTTPError:
        st.error("API unreachable")

auth = st.session_state.get("auth")
if not auth:
    st.info("Sign in with an instructor account to load the cohort.")
    st.stop()

if auth.get("role") != "instructor":
    st.error("This dashboard requires an instructor account.")
    st.stop()

token = auth["access_token"]

try:
    overview = api_get("/instructor/cohort/overview", token)
    anomalies = api_get("/instructor/anomalies", token, limit=50)
except httpx.HTTPError as exc:
    st.error(f"Could not load cohort data: {exc}")
    st.stop()

assert isinstance(overview, dict)
assert isinstance(anomalies, list)

col1, col2, col3 = st.columns(3)
col1.metric("Students", overview["total_students"])
col2.metric("Attempts recorded", overview["total_attempts"])
col3.metric("Mean mastery", f"{overview['mean_mastery']:.0%}")

st.subheader("Cohort")
students = pd.DataFrame(overview["students"])
if students.empty:
    st.info("No student activity yet.")
else:
    st.dataframe(
        students.rename(
            columns={
                "user_id": "ID",
                "email": "Student",
                "overall_mastery": "Mastery",
                "risk_score": "Risk",
                "weakest_concept": "Weakest concept",
                "attempts": "Attempts",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Mastery": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
            "Risk": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
        },
    )

    st.subheader("At risk")
    at_risk = students[students["risk_score"] >= 0.5]
    if at_risk.empty:
        st.success("No learner is currently above the risk threshold.")
    else:
        for _, row in at_risk.iterrows():
            st.warning(
                f"**{row['email']}** - risk {row['risk_score']:.0%}, "
                f"mastery {row['overall_mastery']:.0%}, weakest: {row['weakest_concept']}"
            )

    st.subheader("Per-learner mastery")
    choice = st.selectbox("Student", students["email"].tolist())
    student_id = int(students.loc[students["email"] == choice, "user_id"].iloc[0])
    detail = api_get(f"/mastery/{student_id}", token)
    assert isinstance(detail, dict)
    mastery_df = pd.DataFrame(detail["mastery"]).set_index("concept_name")
    st.bar_chart(mastery_df["mastery"])
    st.caption(
        f"Overall {detail['overall']:.0%} - model {detail['model_version']}. "
        "Phase 6 adds the SHAP attribution for the risk score here."
    )

st.subheader("Anomaly flags")
if not anomalies:
    st.info("No anomalies flagged.")
else:
    st.dataframe(pd.DataFrame(anomalies), use_container_width=True, hide_index=True)
