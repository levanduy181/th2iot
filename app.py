from datetime import timedelta
import json
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
from settings import CONFIG, DATA, SENSORS
from storage import database, raw_records, utcnow

st.set_page_config(page_title="BAI2 SENSOR MONITORING", page_icon=":material/sensors:", layout="wide")
st.markdown("""<style>
.block-container {padding-top:2rem;max-width:1450px}
h1 {font-size:1.8rem!important;letter-spacing:0!important}
[data-testid=stMetricValue] {font-size:1.8rem}
</style>""", unsafe_allow_html=True)
st.title("BAI2 SENSOR MONITORING")
st.caption("Lê Văn Duy · B23DCAT074 · MQTT / MongoDB Time-Series")
@st.cache_resource
def connect_database():
    return database()


db = connect_database()
with st.sidebar:
    st.subheader("Dữ liệu")
    source = st.selectbox("Nguồn", ["test", "wokwi"], format_func=lambda x: "Python kiểm thử" if x == "test" else "ESP32 Wokwi")
    minutes = st.select_slider("Khoảng thời gian (phút)", [10, 30, 60, 180, 1440], value=60)
    live = st.toggle("Tự cập nhật", value=True)
    st.caption("B23DCAT074")


@st.fragment(run_every=5 if live else None)
def dashboard():
    try:
        records = list(raw_records(db, utcnow() - timedelta(minutes=minutes), source))[-5000:]
        db.command("ping")
    except Exception as exc:
        st.error("Không kết nối được MongoDB. Kiểm tra cửa sổ chạy python run.py.")
        st.code(str(exc)[:250])
        return
    if not records:
        st.info("Chưa có dữ liệu từ nguồn đã chọn.")
        return
    raw = pd.json_normalize(records)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
    raw["Giờ"] = raw["timestamp"].dt.tz_convert("Asia/Ho_Chi_Minh")
    latest = raw.iloc[-1]
    age = (utcnow() - latest["timestamp"].to_pydatetime()).total_seconds()
    st.caption(f"MongoDB đã kết nối · Nguồn: {source.upper()} · Bản tin gần nhất: {age:.0f} giây trước")
    if source == "test":
        st.warning("Dữ liệu kiểm thử do Python phát qua MQTT; không phải số đo từ ESP32.")
    cols = st.columns(4)
    for col, key, label, unit in zip(cols, SENSORS, ["Nhiệt độ", "Độ ẩm", "Khoảng cách"], ["°C", "%RH", "cm"]):
        value = latest[key]
        col.metric(label, "Thiếu" if pd.isna(value) else f"{value:.2f} {unit}")
    cols[3].metric("Bản ghi trong khoảng", len(raw))
    query = {"timestamp": {"$gte": utcnow() - timedelta(minutes=minutes)}, "meta.source": source}
    processed = pd.json_normalize(list(db.sensor_processed.find(query, {"_id": 0}).sort("timestamp", 1).limit(5000)))
    if not processed.empty:
        processed["Giờ"] = pd.to_datetime(processed["timestamp"], utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")
    tabs = st.tabs(["Theo thời gian", "Sau xử lý", "Chất lượng", "Bảng dữ liệu"])
    colors = ["#008577", "#d44b52", "#4475b9"]
    with tabs[0]:
        for key, label, color in zip(SENSORS, ["Nhiệt độ (°C)", "Độ ẩm (%RH)", "Khoảng cách (cm)"], colors):
            plot = px.line(raw, x="Giờ", y=key, color="meta.boot_id", markers=True,
                           labels={key: label, "meta.boot_id": "Phiên"}, color_discrete_sequence=[color])
            plot.update_layout(height=220, margin=dict(l=15, r=15, t=15, b=15), showlegend=False)
            st.plotly_chart(plot, use_container_width=True, key=key)
    with tabs[1]:
        key = st.selectbox("Đại lượng", list(SENSORS))
        if processed.empty:
            st.info("Đang chờ xử lý dữ liệu.")
        else:
            comparison = px.line(processed, x="Giờ", y=[key, key + "_rolling"], markers=True,
                                 color_discrete_sequence=["#008577", "#d44b52"])
            comparison.update_layout(height=340, legend_title_text="", yaxis_title=key)
            st.plotly_chart(comparison, use_container_width=True)
            normalized = px.line(processed, x="Giờ", y=[k + "_normalized" for k in SENSORS],
                                 color_discrete_sequence=colors)
            normalized.update_layout(height=300, yaxis_title="Chuẩn hóa 0–1", legend_title_text="")
            st.plotly_chart(normalized, use_container_width=True)
    with tabs[2]:
        missing = sum(int(g.sequence.max() - g.sequence.min() + 1 - g.sequence.nunique())
                      for _, g in raw.groupby(["meta.device_id", "meta.boot_id"]))
        c1, c2, c3 = st.columns(3)
        c1.metric("Sequence thiếu giữa các bản tin", missing)
        c2.metric("Ô cảm biến thiếu", int(raw[list(SENSORS)].isna().sum().sum()))
        c3.metric("Ô bất thường", int(processed[[k + "_outlier" for k in SENSORS]].sum().sum()) if not processed.empty else 0)
        path = DATA / "inbox.sqlite3"
        if path.exists():
            with sqlite3.connect(path) as conn:
                events = pd.read_sql_query("SELECT kind,COUNT(*) AS total FROM events GROUP BY kind", conn)
                pending = conn.execute("SELECT COUNT(*) FROM inbox WHERE written IS NULL").fetchone()[0]
                times = pd.read_sql_query("SELECT event_id,received,written,write_ms FROM inbox WHERE written IS NOT NULL", conn)
            st.caption(f"Bộ đệm đang chờ ghi: {pending} · Bộ đếm lỗi bên dưới tính trên toàn bộ thời gian lưu")
            st.dataframe(events, hide_index=True, use_container_width=True)
            selected = times[times.event_id.isin(raw.event_id)]
            if not selected.empty:
                duration = (selected.written - selected.received) * 1000
                a, b = st.columns(2)
                a.metric("Nhận MQTT → lưu DB trung bình", f"{duration.mean():.1f} ms")
                b.metric("Nhận MQTT → lưu DB p95", f"{duration.quantile(.95):.1f} ms")
            st.caption("Độ trễ ESP32 cần đồng hồ đồng bộ. Thời gian hiển thị dashboard có thêm chu kỳ làm mới tối đa khoảng 5 giây.")
    with tabs[3]:
        st.dataframe(raw[["Giờ", *SENSORS, "sequence", "uptime_s", "meta.boot_id"]], hide_index=True, use_container_width=True)
        st.download_button("Tải CSV dữ liệu gốc", raw.to_csv(index=False).encode("utf-8-sig"), "sensor_raw.csv", "text/csv", icon=":material/download:")
        if not processed.empty:
            st.download_button("Tải CSV sau xử lý", processed.to_csv(index=False).encode("utf-8-sig"), "sensor_processed.csv", "text/csv", icon=":material/download:")


dashboard()
