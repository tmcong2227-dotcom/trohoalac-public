# -*- coding: utf-8 -*-
"""TroHoaLac Web App – Streamlit UI cho mô hình Weighted Sum Proposal 4A.

Chế độ SQL Server là mặc định và chỉ SELECT dữ liệu THẬT khi ấn Tìm trọ.
Chế độ DEMO phải được người dùng chủ động chọn và luôn hiển thị cảnh báo.
"""
from __future__ import annotations

from collections import Counter
import json
from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st

from recommend import CODE_GROUP, DEFAULT_IMPORTANCE, LABELS
from web_logic import (
    PRIORITY_LABELS, build_need_from_selection, csv_bytes, format_price,
    json_bytes, run_recommendation, safe_source_url, supported_catalog,
)

HERE = Path(__file__).resolve().parent

st.set_page_config(
    page_title="TroHoaLac | Tìm phòng phù hợp",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container { max-width: 1130px; padding-top: 2.0rem; padding-bottom: 5rem; }
  div[data-testid="stSidebar"] { background: #f1f5f2; border-right: 1px solid #dfe9e3; }
  div[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
  h1,h2,h3 { font-family: 'Segoe UI', sans-serif; letter-spacing: -0.035em; color: #183e36; }
  h1 { font-weight: 780; font-size: 2.65rem !important; line-height: 1.17; }
  h2 { font-size: 1.5rem !important; }
  [data-testid="stMetric"] { padding: 0.3rem 0; }
  [data-testid="stMetricLabel"] { font-size: .88rem; color: #596f67; }
  div[data-testid="stButton"] > button[kind="primary"] {
      border-radius: 12px; background: #137a6b; border: 1px solid #137a6b;
      min-height: 3.2rem; font-weight: 700; }
  div[data-testid="stButton"] > button[kind="primary"]:hover { background: #0f5f54; }
  div[data-testid="stDownloadButton"] > button { border-radius: 10px; }
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
  .thl-kicker { color: #137a6b; font-size: .76rem; font-weight: 800; letter-spacing: .12em; margin-bottom: .8rem; }
  .thl-hero { font-size: 1.04rem; color: #61716c; margin: -0.35rem 0 1.25rem 0; max-width: 700px; }
  .thl-overline { color: #788982; font-size: .78rem; text-transform: uppercase; font-weight: 800; letter-spacing: .065em; }
  .thl-rank { color: #137a6b; font-weight: 750; font-size: .8rem; letter-spacing: .08em; }
  .thl-subtle { font-size: .9rem; color: #596f67; }
  .thl-pill { display: inline-block; background: #e9f6ef; color:#155f52; border-radius: 99px;
    padding: .32rem .65rem; font-weight: 750; font-size: .85rem; }
  .thl-title { font-size: 1.25rem; font-weight: 780; color: #17392f; margin-top: .25rem; }
  .thl-foot { color:#7a8882; font-size:.79rem; }
  hr { border-color: #e2eae5; }
  @media (max-width: 760px) {
    .block-container { padding-top: 1.2rem; padding-left: 1.0rem; padding-right: 1.0rem; }
    h1 { font-size: 2.0rem !important; }
  }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_public_snapshot():
    path = HERE / "data" / "rooms_public.json"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        raise ValueError("rooms_public.json không có định dạng snapshot hợp lệ.")
    if not isinstance(data.get("catalog", []), list):
        raise ValueError("catalog không phải danh sách mã tiện ích.")
    rooms = data["rooms"]
    if not all(isinstance(r,dict) and isinstance(r.get("amenities", {}),dict) for r in rooms):
        raise ValueError("Có bản ghi phòng trọ thiếu trường amenities hợp lệ.")
    catalog = set(str(c).strip().upper() for c in data.get("catalog", []))
    return rooms, catalog, data.get("exported_at")


def source_summary(rooms):
    return {
        "areas": sorted({str(r["area_name"]).strip() for r in rooms if r.get("area_name")}),
        "counts": dict(Counter(str(r.get("source_type") or "Chưa rõ") for r in rooms)),
        "total": len(rooms),
    }


def set_data_context(signature, rooms, codes):
    desc = source_summary(rooms)
    st.session_state["data_context"] = {
        "signature": signature, "areas": desc["areas"],
        "counts": desc["counts"], "total": desc["total"],
        "catalog": set(codes), "verified_at": datetime.now().strftime("%H:%M:%S"),
    }
    st.session_state.pop("last_result", None)


def render_card(room, rank, *, tentative=False):
    with st.container(border=True):
        main, side = st.columns([4.6, 1], vertical_alignment="top")
        with main:
            label = escape(str(room.get("property_name") or "Phòng chưa có tên"))
            st.markdown(f'<div class="thl-rank">#{rank:02d} · {"CẦN XÁC MINH" if tentative else "PHÙ HỢP"}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="thl-title">{label}</div>', unsafe_allow_html=True)
            area = escape(str(room.get("area_name") or "Chưa rõ khu vực"))
            st.caption(f"📍 {area}    ·    Nguồn: {room.get('source_type') or 'Chưa rõ'}")
        with side:
            st.markdown(f'<div class="thl-pill">{room["score"]:.1f}/100</div>', unsafe_allow_html=True)
        a, b, c = st.columns(3)
        with a:
            st.markdown("<div class='thl-overline'>Giá thuê</div>", unsafe_allow_html=True)
            st.write(format_price(room.get("monthly_rent_million"), room.get("rent_max_million")))
        with b:
            st.markdown("<div class='thl-overline'>Cách FPT</div>", unsafe_allow_html=True)
            dist = room.get("distance_to_fpt_km")
            st.write(f"{dist:g} km" if dist is not None else "Chưa rõ")
        with c:
            st.markdown("<div class='thl-overline'>Diện tích</div>", unsafe_allow_html=True)
            area_m2 = room.get("floor_area_m2")
            st.write(f"{area_m2:g} m²" if area_m2 is not None else "Chưa rõ")
        if tentative and room.get("filter_notes"):
            st.warning("Cần xác minh: " + "; ".join(room["filter_notes"]))
        if room.get("notes"):
            st.caption(" · ".join(room["notes"]))
        with st.expander("Xem cách tính điểm và trạng thái tiện ích"):
            parts = {"price": "Giá", "distance": "Khoảng cách", "amenities": "Tiện ích", "area": "Khu vực"}
            scores = room.get("scores", {})
            contributes = room.get("contributions", {})
            if scores:
                headers = st.columns(len(scores))
                for col, (key, score) in zip(headers, scores.items()):
                    with col:
                        st.metric(parts.get(key, key), f"{contributes.get(key, 0):.1f} điểm")
                        st.caption(f"Điểm chuẩn hóa: {score:.2f}")
            details = room.get("amenity_details") or {}
            if details:
                st.markdown("**Tiện ích bạn ưu tiên**")
                for info in details.values():
                    prefix = {"có": "✓", "không": "✕", "chưa rõ": "?"}.get(info["status"], "?")
                    st.write(f"{prefix} {info['name']} — {info['status']} (mức quan trọng {info['importance']})")
            else:
                st.caption("Bạn không chọn tiện ích ưu tiên nên điểm chỉ dựa trên các tiêu chí còn lại.")
        url = safe_source_url(room.get("source_url"))
        if url:
            st.link_button("Xem bài đăng gốc", url, use_container_width=False)
        else:
            st.caption("Chưa có liên kết bài đăng gốc trong dữ liệu.")


# ------- LOAD PUBLISHED SNAPSHOT (không yêu cầu SQL Server / mật khẩu từ khách) -------
try:
    rooms_public, catalog_public, exported_at = load_public_snapshot()
except Exception as exc:
    st.error("Không đọc được dữ liệu công khai: " + str(exc))
    st.stop()

with st.sidebar:
    st.markdown("### 🏡 TroHoaLac")
    st.caption("Tìm phòng theo nhu cầu · Weighted Sum 4A")
    st.divider()
    st.success("Nguồn: dữ liệu TroHoaLac công khai")
    st.metric("Số bản ghi", f"{len(rooms_public):,}")
    st.caption("Ngày xuất dữ liệu: " + (str(exported_at) if exported_at else "Chưa xuất"))
    st.caption("Dữ liệu được xuất từ SQL Server và cập nhật theo từng lần đăng bản mới.")
    st.divider()
    st.caption("Kết quả chỉ hỗ trợ tìm kiếm, không xác nhận phòng còn trống.")

if not rooms_public:
    st.warning("Chưa có dữ liệu thực tế để công bố. Trên máy có SQL Server, chạy export_public.py rồi upload lại data/rooms_public.json lên GitHub.")
    st.stop()
context = source_summary(rooms_public)
context["catalog"] = catalog_public
signature = ("public", str(exported_at))

# ------- HEADER -------
st.markdown('<div class="thl-kicker">TROHOALAC / TÌM TRỌ THÔNG MINH</div>', unsafe_allow_html=True)
st.title("Tìm đúng phòng, theo cách của bạn.")
st.markdown('<div class="thl-hero">Chọn mức giá, khoảng cách và tiện ích. TroHoaLac sẽ tìm và xếp hạng những phòng phù hợp nhất từ dữ liệu đã chuẩn hóa.</div>', unsafe_allow_html=True)

st.caption("Nguồn dữ liệu: bản xuất từ TroHoaLac. Không kết nối trực tiếp SQL Server của người quản trị.")

# ------- INPUT PANEL -------
st.markdown("## 1. Nhu cầu tìm trọ")
st.caption("Các tiêu chí bắt buộc sẽ dùng để lọc. Các tiêu chí ưu tiên dùng để xếp hạng.")

left, right = st.columns(2, gap="large")
with left:
    st.markdown("**Ngân sách và vị trí**")
    budget_max = st.slider("Ngân sách tối đa (triệu/tháng)", min_value=0.5, max_value=15.0,
                           value=2.5, step=0.1)
    use_min_budget = st.checkbox("Giới hạn giá tối thiểu", value=False)
    budget_min = st.number_input("Giá tối thiểu (triệu/tháng)", 0.0, float(budget_max),
                                 min(1.0, float(budget_max)), 0.1) if use_min_budget else None
    budget_choice = st.radio("Kiểm tra ngân sách", ["Nghiêm ngặt", "Linh hoạt"], horizontal=True,
                             help="Nghiêm ngặt: toàn bộ khoảng giá phải nằm trong ngân sách. Linh hoạt: chỉ cần có mức giá giao với ngân sách.")
    budget_mode = "strict" if budget_choice == "Nghiêm ngặt" else "overlap"
    limit_distance = st.checkbox("Giới hạn khoảng cách đến FPT", value=True)
    max_distance = st.slider("Khoảng cách tối đa (km)", 0.5, 20.0, 3.0, 0.5,
                             disabled=not limit_distance) if limit_distance else None
with right:
    st.markdown("**Khu vực và tiện ích**")
    areas = st.multiselect("Khu vực mong muốn", context["areas"], placeholder="Không giới hạn khu vực")
    area_choice = st.radio("Khu vực là", ["Ưu tiên", "Bắt buộc"], horizontal=True,
                           disabled=not areas, help="Ưu tiên: nơi khác vẫn được xếp hạng. Bắt buộc: chỉ giữ phòng ở khu vực bạn chọn.")
    area_mode = "soft" if area_choice == "Ưu tiên" else "hard"
    codes = supported_catalog(context["catalog"])
    fmt = lambda c: LABELS.get(c, c)
    required = st.multiselect("Tiện ích bắt buộc", codes, format_func=fmt,
                              placeholder="Ví dụ: WC riêng")
    preferred = st.multiselect("Tiện ích ưu tiên", codes, format_func=fmt,
                               placeholder="Ví dụ: Điều hòa, Wifi")
    if not codes:
        st.warning("Không có mã tiện ích nào khớp từ điển mô hình. Có thể tìm trọ theo giá, khoảng cách và khu vực, nhưng cần đối chiếu core.amenity trước khi dùng tiện ích.")
    if set(required).intersection(preferred):
        st.caption("Tiện ích đã chọn là bắt buộc sẽ không được tính điểm ưu tiên lần thứ hai.")

importance = {}
priority = {"price": "medium", "distance": "medium", "amenities": "medium", "area": "medium"}
with st.expander("Tùy chỉnh mức độ ưu tiên (không bắt buộc)"):
    st.caption("Mặc định theo Proposal 4A: giá 40%, khoảng cách 30%, tiện ích 30%. Nếu ưu tiên khu vực: 36% / 27% / 27% / 10%.")
    p1, p2, p3 = st.columns(3)
    with p1:
        priority["price"] = PRIORITY_LABELS[st.selectbox("Ưu tiên giá", list(PRIORITY_LABELS), index=1)]
    with p2:
        priority["distance"] = PRIORITY_LABELS[st.selectbox("Ưu tiên khoảng cách", list(PRIORITY_LABELS), index=1)]
    with p3:
        priority["amenities"] = PRIORITY_LABELS[st.selectbox("Ưu tiên tiện ích", list(PRIORITY_LABELS), index=1)]
    if areas and area_mode == "soft":
        priority["area"] = PRIORITY_LABELS[st.selectbox("Ưu tiên khu vực", list(PRIORITY_LABELS), index=1)]
    for code in preferred:
        if code in required:
            continue
        default_imp = DEFAULT_IMPORTANCE[CODE_GROUP[code]]
        importance[code] = st.select_slider(
            f"{fmt(code)} – mức quan trọng", options=[1, 2, 3], value=default_imp,
            format_func=lambda v: {1: "Thấp", 2: "Vừa", 3: "Cao"}[v],
            key="imp_" + code,
        )

st.caption("Diện tích chưa dùng để lọc hoặc chấm điểm theo Proposal 4A; sẽ hiển thị cùng kết quả phòng.")
current_need = build_need_from_selection(
    budget_max=budget_max, budget_min=budget_min,
    max_distance=max_distance, areas=areas, area_mode=area_mode,
    budget_mode=budget_mode, required=required, preferred=preferred,
    importance=importance, priority=priority,
)
search_clicked = st.button("🔎 Tìm phòng phù hợp", type="primary", use_container_width=True)

if search_clicked:
    try:
        need = current_need
        with st.spinner("Đang lọc và tính điểm phòng trọ ..."):
            result = run_recommendation(rooms_public, need, catalog_public, top_n=10)
        result["data_source_mode"] = "TroHoaLac – dữ liệu công khai"
        result["retrieved_at"] = datetime.now().isoformat(timespec="seconds")
        st.session_state["last_result"] = {"signature": signature, "data": result}
    except Exception as exc:
        st.error("Không thể tìm trọ với các lựa chọn này: " + str(exc))
        st.session_state.pop("last_result", None)

last = st.session_state.get("last_result")
if not last or last.get("signature") != signature or last["data"].get("query") != current_need:
    st.markdown("---")
    st.info("Chọn tiêu chí phía trên rồi nhấn **Tìm phòng phù hợp** để xem Top 10.")
    st.stop()

result = last["data"]
st.divider()
st.markdown("## 2. Phòng phù hợp với bạn")
st.caption(f"Dữ liệu: {result['data_source_mode']} · Tra cứu lúc {result['retrieved_at']} · Chỉ xếp hạng các phòng đáp ứng điều kiện cứng đã xác minh")

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Tổng tin đã đọc", f"{result['total_raw']:,}")
with m2:
    st.metric("Phòng sau gộp trùng", f"{result['unique_rooms']:,}")
with m3:
    st.metric("Phòng đạt yêu cầu", f"{result['eligible_count']:,}")
with m4:
    st.metric("Cần xác minh", f"{result['unverified_count']:,}")

if not result["top10"]:
    st.warning("Không tìm thấy phòng nào đã được xác minh đáp ứng tất cả điều kiện. Hãy thử tăng ngân sách, mở rộng khoảng cách hoặc giảm số tiện ích bắt buộc. Hệ thống không tự thay đổi yêu cầu của bạn.")
else:
    st.success(f"Tìm thấy {result['eligible_count']} phòng đạt điều kiện. Hiển thị {len(result['top10'])} phòng xếp hạng cao nhất.")
    for rank, room in enumerate(result["top10"], 1):
        render_card(room, rank)

if result["unverified_count"]:
    with st.expander(f"🔍 {result['unverified_count']} phòng gần phù hợp nhưng cần xác minh (danh sách riêng)"):
        st.warning("Các phòng này chưa được chứng minh đáp ứng đủ điều kiện bắt buộc, vì vậy KHÔNG nằm trong Top 10 chính.")
        for rank, room in enumerate(result["needs_verification"], 1):
            render_card(room, rank, tentative=True)

if result["top10"]:
    st.markdown("### Tải kết quả")
    x, y = st.columns(2)
    with x:
        st.download_button("⬇ Tải Top 10 (CSV)", data=csv_bytes(result),
                           file_name="trohoalac_top10.csv", mime="text/csv", use_container_width=True)
    with y:
        st.download_button("⬇ Tải kết quả chi tiết (JSON)", data=json_bytes(result),
                           file_name="trohoalac_ket_qua.json", mime="application/json", use_container_width=True)

st.divider()
st.markdown('<div class="thl-foot">TroHoaLac • Weighted Sum theo Proposal 4A • Phần mềm hỗ trợ tìm kiếm, không xác nhận tình trạng còn trống hoặc tính chính xác của thông tin đăng.</div>', unsafe_allow_html=True)
