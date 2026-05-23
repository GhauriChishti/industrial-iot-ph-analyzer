"""Industrial Streamlit dashboard for the Industrial IoT pH Analyzer."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

API_BASE_URL = "http://127.0.0.1:8000"
LATEST_ENDPOINT = f"{API_BASE_URL}/api/v1/telemetry/latest"
HISTORY_ENDPOINT = f"{API_BASE_URL}/api/v1/telemetry/history"
REQUEST_TIMEOUT_SECONDS = 4
AUTO_REFRESH_MS = 5000

ALARM_CONFIG = {
    0: {"label": "Normal", "color": "#2ecc71"},
    1: {"label": "Acidic Alarm", "color": "#f39c12"},
    2: {"label": "Alkaline Alarm", "color": "#f39c12"},
    3: {"label": "Temperature Alarm", "color": "#e74c3c"},
}


def configure_page() -> None:
    st.set_page_config(
        page_title="Industrial IoT pH Analyzer Dashboard",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
            :root {
                --bg-main: #0b1117;
                --bg-panel: #121b24;
                --text-main: #e5ecf6;
                --text-muted: #9db0c5;
                --border: #2b3b4d;
                --ok: #2ecc71;
                --warn: #f39c12;
                --danger: #e74c3c;
                --neutral: #7f8c8d;
            }
            .stApp {
                background: radial-gradient(circle at top, #17222e 0%, #0b1117 50%);
                color: var(--text-main);
            }
            .block-container {
                padding-top: 1.5rem;
                padding-bottom: 1rem;
            }
            .metric-card {
                border: 1px solid var(--border);
                background: var(--bg-panel);
                border-radius: 12px;
                padding: 14px;
                min-height: 95px;
            }
            .metric-label {
                color: var(--text-muted);
                font-size: 0.9rem;
                margin-bottom: 5px;
            }
            .metric-value {
                font-size: 1.4rem;
                font-weight: 700;
            }
            .status-pill {
                display: inline-block;
                padding: 0.2rem 0.7rem;
                border-radius: 999px;
                font-weight: 600;
                border: 1px solid rgba(255,255,255,0.15);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def enable_auto_refresh() -> None:
    components.html(
        f"""
        <script>
            setTimeout(function() {{
                window.parent.location.reload();
            }}, {AUTO_REFRESH_MS});
        </script>
        """,
        height=0,
    )


def fetch_json(url: str, *, params: dict[str, int] | None = None) -> dict | list:
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def parse_history(payload: dict | list) -> pd.DataFrame:
    records = payload if isinstance(payload, list) else payload.get("items", [])
    if not records:
        return pd.DataFrame(columns=["timestamp", "ph", "temperature_c"])

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df


def draw_gauge(value: float, title: str, min_value: float, max_value: float, color: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"font": {"color": "#e5ecf6", "size": 34}},
            title={"text": title, "font": {"color": "#e5ecf6", "size": 18}},
            gauge={
                "axis": {"range": [min_value, max_value], "tickcolor": "#9db0c5"},
                "bar": {"color": color},
                "bgcolor": "#0f1720",
                "bordercolor": "#2b3b4d",
                "steps": [
                    {"range": [min_value, max_value], "color": "#16222f"},
                ],
            },
        )
    )
    fig.update_layout(
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        paper_bgcolor="#121b24",
        height=280,
    )
    return fig


def status_badge(label: str, value: str, color: str) -> None:
    st.markdown(
        (
            "<div class='metric-card'>"
            f"<div class='metric-label'>{label}</div>"
            f"<div class='metric-value'><span class='status-pill' style='background:{color}22; color:{color};'>{value}</span></div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def trend_chart(df: pd.DataFrame, y_col: str, title: str, color: str, y_axis_title: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=df["timestamp"],
            y=df[y_col],
            mode="lines+markers",
            line={"width": 3, "color": color},
            marker={"size": 5},
            name=title,
        )
    )
    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor="#121b24",
        plot_bgcolor="#121b24",
        font={"color": "#e5ecf6"},
        xaxis_title="Timestamp (UTC)",
        yaxis_title=y_axis_title,
        height=320,
        margin={"l": 30, "r": 20, "t": 40, "b": 30},
    )
    return fig


def main() -> None:
    configure_page()
    enable_auto_refresh()

    st.title("Industrial IoT pH Analyzer Dashboard")
    st.caption(
        f"Auto-refresh every {AUTO_REFRESH_MS // 1000}s • Last render: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    try:
        latest = fetch_json(LATEST_ENDPOINT)
        history_payload = fetch_json(HISTORY_ENDPOINT, params={"limit": 100})
    except requests.RequestException as exc:
        st.error("Unable to connect to backend API. Please verify that the service is running at http://127.0.0.1:8000")
        st.exception(exc)
        return

    history_df = parse_history(history_payload)

    ph = float(latest.get("ph", 0.0))
    temp_c = float(latest.get("temperature_c", latest.get("temperature", 0.0)))
    alarm_code = int(latest.get("alarm", 0))
    sensor_ok = bool(latest.get("sensor_ok", latest.get("sensor_health", True)))
    analyzer_online = bool(latest.get("analyzer_online", latest.get("online", True)))

    alarm = ALARM_CONFIG.get(alarm_code, {"label": f"Unknown ({alarm_code})", "color": "#7f8c8d"})

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(draw_gauge(ph, "Live pH", 0, 14, "#00bcd4"), use_container_width=True)
    with col2:
        st.plotly_chart(draw_gauge(temp_c, "Live Temperature (°C)", -10, 120, "#ff6f61"), use_container_width=True)

    m1, m2, m3 = st.columns(3)
    with m1:
        status_badge("Alarm Status", alarm["label"], alarm["color"])
    with m2:
        status_badge("Sensor Health", "Healthy" if sensor_ok else "Fault", "#2ecc71" if sensor_ok else "#e74c3c")
    with m3:
        status_badge("Analyzer Status", "Online" if analyzer_online else "Offline", "#2ecc71" if analyzer_online else "#e74c3c")

    if history_df.empty:
        st.warning("No historical telemetry available yet.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            trend_chart(history_df, "ph", "pH Trend", "#00bcd4", "pH"),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            trend_chart(history_df, "temperature_c", "Temperature Trend", "#ff6f61", "Temperature (°C)"),
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
