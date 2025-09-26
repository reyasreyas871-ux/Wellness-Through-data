import streamlit as st
import pandas as pd
import requests
import time
import plotly.express as px

st.set_page_config(page_title="AMR Wellness Dashboard", layout="wide")
st.title("AMR Wellness Dashboard (Localhost)")
st.caption("Real-time view of adherence, trends, and wellness index.")

BACKEND = "http://127.0.0.1:5000"

col1, col2, col3 = st.columns(3)

@st.cache_data(ttl=5.0)
def fetch_metrics():
    try:
        r = requests.get(f"{BACKEND}/api/metrics", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

placeholder = st.empty()

with st.sidebar:
    st.header("Controls")
    interval = st.slider("Refresh interval (seconds)", 2, 30, 5)

    st.markdown(
        f"[Open Control Panel]({BACKEND})",
        unsafe_allow_html=True
    )
    if st.button("Push anonymized data to WHO mock server"):
        try:
            r = requests.post(f"{BACKEND}/share-data", timeout=8)
            st.write(r.json())
        except Exception as e:
            st.error(f"Error: {e}")

# ---- MAIN RENDER ----
data = fetch_metrics()

if not data:
    st.warning("Waiting for backend at http://127.0.0.1:5000 ... Make sure `python backend.py` is running.")
else:
    with placeholder.container():
        col1.metric("Total Prescriptions", data["total_prescriptions"])
        col2.metric("Total Doses Logged", data["total_logs"])
        col3.metric("Adherence Rate (%)", data["adherence_rate"])

        c1, c2 = st.columns(2)
        with c1:
            df = pd.DataFrame([
                {"status": "Taken", "count": data["doses_taken"]},
                {"status": "Missed", "count": data["doses_missed"]},
            ])
            fig = px.bar(df, x="status", y="count", title="Dose Logs")
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            wellness = data["wellness_index"]
            st.subheader(f"Wellness Index: {wellness}")
            st.progress(min(1.0, wellness / 100.0))

        st.caption(f"Last updated: {data['generated_at']}")

# ---- AUTO REFRESH ----
time.sleep(interval)
st.rerun()