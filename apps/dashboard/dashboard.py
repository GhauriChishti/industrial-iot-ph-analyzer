"""Industrial Streamlit dashboard for the Industrial IoT pH Analyzer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"
LATEST_ENDPOINT = f"{API_BASE_URL}/api/v1/telemetry/latest"
HISTORY_ENDPOINT = f"{API_BASE_URL}/api/v1/telemetry/history"
REQUEST_TIMEOUT_SECONDS = 4
AUTO_REFRESH_MS = 5000
STALE_TELEMETRY_SECONDS = 30

ALARM_CONFIG = {
    0: {"label": "Healthy", "color": "#2ecc71"},
    1: {"label": "Acidic", "color": "#f39c12"},
    2: {"label": "Alkaline", "color": "#e74c3c"},
    3: {"label": "Temperature Alarm", "color": "#ff5c5c"},
}


def configure_page() -> None:
    st.set_page_config(
        page_title="Industrial IoT pH Analyzer Dashboard",
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
            :root {
                --bg-main: #0a1118;
                --bg-panel: #121c26;
                --panel-2: #0f1821;
                --text-main: #e5ecf6;
                --text-muted: #98aeca;
                --border: #2a3c4f;
                --ok: #2ecc71;
                --warn: #f39c12;
                --danger: #e74c3c;
                --neutral: #7f8c8d;
            }
            .stApp {
                background: linear-gradient(180deg, #0d151f 0%, #0a1118 100%);
                color: var(--text-main);
            }
            .block-container {
                max-width: 1450px;
                padding-top: 1.25rem;
                padding-bottom: 1.5rem;
            }
            .header-wrap {
                border: 1px solid var(--border);
                background: linear-gradient(135deg, #122233 0%, #101c29 100%);
                border-radius: 12px;
                padding: 0.9rem 1.1rem;
                margin-bottom: 0.8rem;
            }
            .metric-card {
                border: 1px solid var(--border);
                background: var(--bg-panel);
                border-radius: 12px;
                padding: 14px;
                min-height: 95px;
            }
            .metric-label { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 5px; }
            .metric-value { font-size: 1.4rem; font-weight: 700; }
            .status-pill {
                display: inline-block;
                padding: 0.2rem 0.7rem;
                border-radius: 999px;
                font-weight: 700;
                border: 1px solid rgba(255,255,255,0.15);
                letter-spacing: 0.01em;
            }
            .banner {
                border-left: 8px solid transparent;
                border-radius: 10px;
                padding: 0.8rem 1rem;
                font-weight: 700;
                margin: 0.35rem 0 1rem 0;
                border: 1px solid var(--border);
                background: var(--panel-2);
            }
            .banner-ok { border-left-color: #2ecc71; color: #b9f3cc; }
            .banner-warn { border-left-color: #f39c12; color: #ffd79b; }
            .banner-danger { border-left-color: #e74c3c; color: #ffb1a8; }
            .small-muted { color: var(--text-muted); font-size: 0.85rem; }
            [data-testid="stPlotlyChart"] {
                border: 1px solid var(--border);
                border-radius: 12px;
                background: var(--bg-panel);
                padding: 0.2rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def enable_auto_refresh() -> None:
    st.autorefresh(interval=AUTO_REFRESH_MS, key="scada_refresh")


def fetch_json(url: str, *, params: dict[str, int] | None = None) -> tuple[dict | list, float]:
    start = perf_counter()
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    latency_ms = (perf_counter() - start) * 1000
    return response.json(), latency_ms


def parse_history(payload: dict | list) -> pd.DataFrame:
    records = payload if isinstance(payload, list) else payload.get("items", [])
    if not records:
        return pd.DataFrame(columns=["timestamp", "ph", "temperature"])

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
                "steps": [{"range": [min_value, max_value], "color": "#16222f"}],
            },
        )
    )
    fig.update_layout(margin={"l": 20, "r": 20, "t": 50, "b": 20}, paper_bgcolor="#121b24", height=280)
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


def alarm_banner(alarm_label: str) -> None:
    css = "banner-ok"
    if alarm_label == "Acidic":
        css = "banner-warn"
    elif alarm_label in {"Alkaline", "Temperature Alarm"}:
        css = "banner-danger"

    st.markdown(f"<div class='banner {css}'>ALARM STATUS: {alarm_label}</div>", unsafe_allow_html=True)


def trend_chart(df: pd.DataFrame, y_col: str, title: str, color: str, y_axis_title: str) -> go.Figure:
    rolling = df[y_col].rolling(window=6, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df[y_col],
            mode="lines",
            line={"width": 2, "color": color},
            name=f"{title} Raw",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=rolling,
            mode="lines",
            line={"width": 3, "color": "#ffffff", "dash": "dot"},
            name=f"{title} Rolling Avg",
            opacity=0.7,
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
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.1, "x": 0},
        height=340,
        margin={"l": 35, "r": 20, "t": 50, "b": 40},
    )
    fig.update_xaxes(showgrid=True, gridcolor="#22384d")
    fig.update_yaxes(showgrid=True, gridcolor="#22384d")
    return fig


def main() -> None:
    configure_page()
    enable_auto_refresh()

    now_utc = datetime.now(UTC)
    st.markdown("<div class='header-wrap'><h2 style='margin:0;'>🏭 Industrial IoT pH Analyzer — SCADA Console</h2></div>", unsafe_allow_html=True)
    st.caption(f"Auto-refresh: {AUTO_REFRESH_MS // 1000}s • Render time: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    try:
        latest, latest_latency = fetch_json(LATEST_ENDPOINT)
        history_payload, history_latency = fetch_json(HISTORY_ENDPOINT, params={"limit": 200})
    except requests.RequestException as exc:
        st.error("Backend API unreachable. Verify FastAPI service is running at http://127.0.0.1:8000")
        st.exception(exc)
        return

    history_df = parse_history(history_payload)

    ph = float(latest.get("ph", 0.0))
    temp_c = float(latest.get("temperature", 0.0))
    alarm_code = int(latest.get("alarm", 0))
    sensor_ok = bool(latest.get("sensor_ok", latest.get("sensor_health", True)))
    analyzer_online = bool(latest.get("analyzer_online", latest.get("online", True)))

    alarm = ALARM_CONFIG.get(alarm_code, {"label": f"Unknown ({alarm_code})", "color": "#7f8c8d"})
    alarm_banner(alarm["label"])

    last_ts = pd.to_datetime(latest.get("timestamp"), utc=True, errors="coerce")
    stale = pd.isna(last_ts) or (now_utc - last_ts.to_pydatetime()) > timedelta(seconds=STALE_TELEMETRY_SECONDS)

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        status_badge("Backend Connectivity", "Online" if latest_latency < 1500 else "Degraded", "#2ecc71" if latest_latency < 1500 else "#f39c12")
        st.markdown(f"<div class='small-muted'>latest: {latest_latency:.0f} ms • history: {history_latency:.0f} ms</div>", unsafe_allow_html=True)
    with c2:
        status_badge("Telemetry Freshness", "Stale" if stale else "Live", "#e74c3c" if stale else "#2ecc71")
        age = "unknown" if pd.isna(last_ts) else f"{int((now_utc - last_ts.to_pydatetime()).total_seconds())} sec old"
        st.markdown(f"<div class='small-muted'>sample age: {age}</div>", unsafe_allow_html=True)
    with c3:
        status_badge("Connection Health", "Healthy" if analyzer_online and sensor_ok else "Attention", "#2ecc71" if analyzer_online and sensor_ok else "#e74c3c")
        st.markdown(
            f"<div class='small-muted'>sensor: {'ok' if sensor_ok else 'fault'} • analyzer: {'online' if analyzer_online else 'offline'}</div>",
            unsafe_allow_html=True,
        )

    g1, g2 = st.columns(2, gap="large")
    with g1:
        st.plotly_chart(draw_gauge(ph, "Live pH", 0, 14, "#00bcd4"), width="stretch")
    with g2:
        st.plotly_chart(draw_gauge(temp_c, "Live Temperature (°C)", -10, 120, "#ff6f61"), width="stretch")

    m1, m2, m3 = st.columns(3, gap="large")
    with m1:
        status_badge("Alarm Category", alarm["label"], alarm["color"])
    with m2:
        status_badge("Sensor Health", "Healthy" if sensor_ok else "Fault", "#2ecc71" if sensor_ok else "#e74c3c")
    with m3:
        status_badge("Analyzer Status", "Online" if analyzer_online else "Offline", "#2ecc71" if analyzer_online else "#e74c3c")

    if history_df.empty:
        st.warning("No historical telemetry available yet.")
        return

    t1, t2 = st.columns(2, gap="large")
    with t1:
        st.plotly_chart(trend_chart(history_df, "ph", "pH Trend", "#00bcd4", "pH"), width="stretch")
    with t2:
        st.plotly_chart(
            trend_chart(history_df, "temperature", "Temperature Trend", "#ff6f61", "Temperature (°C)"),
            width="stretch",
        )


if __name__ == "__main__":
    main()
