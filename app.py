# -*- coding: utf-8 -*-
"""TroHoaLac - giao diện dành cho người tìm trọ.

Chỉ trình bày điểm phù hợp chung (/100); phần chấm điểm nằm trong recommend.py.
Đọc snapshot data/rooms_public.json đã xuất từ SQL Server, KHÔNG kết nối SQL online.
"""
import json
from pathlib import Path
from html import escape

import streamlit as st

from recommend import CODE_GROUP, LABELS
from price_policy import eligible_price
from room_view import DISPLAY_GROUPS, address_display, amenities_table
from web_logic import (
    build_need_from_selection, csv_bytes, format_price, json_bytes,
    run_recommendation, safe_source_url,
)

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="TroHoaLac | Tìm trọ", page_icon="⌂", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
  .block-container {max-width:1080px; padding-top:1.8rem; padding-bottom:3rem}
  .stApp {background:#fff; color:#111}
  h1,h2,h3 {letter-spacing:-.035em}
  h1 {font-weight:760!important}
  div[data-testid="stButton"] button[kind="primary"] {background:#111; color:#fff; border:1px solid #111}
  div[data-testid="stVerticalBlockBorderWrapper"] {border:1px solid #ddd; border-radius:12px}
  .brand {font-weight:800; letter-spacing:.16em; font-size:.83rem}
  .muted {color:#666; font-size:.90rem}
  .room-title {font-size:1.25rem; font-weight:760; line-height:1.3}
  .rank {font-size:.80rem; font-weight:700; color:#555}
  .score {display:inline-block; border:1px solid #111; padding:.35rem .65rem;
          border-radius:8px; font-size:1.12rem; font-weight:800}
  @media(max-width:720px){.block-container{padding:1rem .8rem 3rem}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_data():
    path = ROOT / "data" / "rooms_public.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        raise ValueError("Sai định dạng data/rooms_public.json")
    rooms = data["rooms"]
    if not all(isinstance(r, dict) and isinstance(r.get("amenities"), dict) for r in rooms):
        raise ValueError("Một số phòng thiếu thông tin amenities")
    return [r for r in rooms if eligible_price(r)], set(data.get("catalog", [])), data.get("exported_at")


def unset_other(code, selected_type):
    """Không thể chọn cùng một tiện ích là vừa bắt buộc vừa ưu tiên."""
    if st.session_state.get(f"{selected_type}_{code}"):
        other = "soft" if selected_type == "hard" else "hard"
        st.session_state[f"{other}_{code}"] = False


def select_amenities(catalog):
    required, preferred = [], []
    for tab, codes in zip(st.tabs(list(DISPLAY_GROUPS)), DISPLAY_GROUPS.values()):
        with tab:
            left, right = st.columns(2)
            left.caption("BẮT BUỘC CÓ")
            right.caption("MONG MUỐN CÓ")
            for code in codes:
                if code not in catalog or code not in CODE_GROUP:
                    continue
                name = LABELS.get(code, code)
                with left:
                    hard = st.checkbox(name, key=f"hard_{code}", on_change=unset_other,
                                       args=(code, "hard"))
                with right:
                    soft = st.checkbox(name, key=f"soft_{code}", on_change=unset_other,
                                       args=(code, "soft"))
                if hard:
                    required.append(code)
                elif soft:
                    preferred.append(code)
    return required, preferred


def pretty_number(value, suffix=""):
    try:
        return f"{float(value):g}{suffix}" if value is not None else "Chưa có dữ liệu"
    except (ValueError, TypeError):
        return "Chưa có dữ liệu"


def room_card(room, rank, catalog, uncertain=False):
    with st.container(border=True):
        left, right = st.columns([5, 1.5], vertical_alignment="top")
        with left:
            st.markdown(f'<div class="rank">#{rank:02d} · {"Cần xác minh" if uncertain else "Gợi ý phù hợp"}</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="room-title">{escape(str(room.get("property_name") or "Chưa có tên trọ"))}</div>',
                        unsafe_allow_html=True)
        with right:
            st.markdown(f'<div class="score">{float(room["score"]):.1f}/100</div>', unsafe_allow_html=True)

        # Sáu thông tin người tìm trọ cần xem (tên ở phía trên).
        c1, c2, c3 = st.columns(3)
        c1.metric("Giá thuê", format_price(room.get("monthly_rent_million"), room.get("rent_max_million")))
        c2.metric("Diện tích", pretty_number(room.get("floor_area_m2"), " m²"))
        c3.metric("Cách FPT", pretty_number(room.get("distance_to_fpt_km"), " km"))
        st.markdown(f"**Khu vực:** {escape(str(room.get('area_name') or 'Chưa có dữ liệu'))}")
        st.markdown(f"**Địa chỉ:** {escape(address_display(room))}")

        # Đặt link ngay trong thẻ phòng, không bắt người dùng mở phần chi tiết.
        url = safe_source_url(room.get("source_url"))
        if url:
            st.link_button("↗ Xem bài đăng gốc", url, use_container_width=False)
        else:
            st.caption("Chưa có liên kết bài đăng được xác minh cho phòng này.")

        st.caption("Nguồn: " + str(room.get("source_name") or room.get("source_type") or "Chưa rõ"))
        if uncertain and room.get("filter_notes"):
            st.warning("Cần xác minh: " + "; ".join(room["filter_notes"]))
        if room.get("notes"):
            st.caption(" · ".join(room["notes"]))

        with st.expander("Xem danh sách tiện ích"):
            rows = amenities_table(room, catalog)
            tabs = st.tabs(["Tiện ích đã có", "Tất cả tiện ích"])
            with tabs[0]:
                yes = [{"Nhóm": r["Nhóm"], "Tiện ích": r["Tiện ích"]}
                       for r in rows if r["Trạng thái"] == "Có"]
                if yes:
                    st.dataframe(yes, hide_index=True, use_container_width=True)
                else:
                    st.caption("Chưa có tiện ích nào được nguồn dữ liệu xác nhận.")
            with tabs[1]:
                st.dataframe([{"Nhóm": r["Nhóm"], "Tiện ích": r["Tiện ích"],
                              "Trạng thái": r["Trạng thái"]} for r in rows],
                             hide_index=True, use_container_width=True)
                st.caption("'Chưa xác minh' không đồng nghĩa với 'Không có'.")


st.markdown('<div class="brand">TROHOALAC</div>', unsafe_allow_html=True)
st.title("Tìm phòng trọ phù hợp với bạn")
st.markdown('<div class="muted">Chọn nhu cầu của bạn và xem các phòng được đề xuất.</div>',
            unsafe_allow_html=True)

try:
    rooms, catalog, updated_at = load_data()
except Exception as exc:
    st.error(f"Không đọc được dữ liệu phòng: {exc}")
    st.stop()
if not rooms:
    st.warning("Chưa có dữ liệu phòng giá 1–6 triệu. Hãy xuất lại rooms_public.json.")
    st.stop()

with st.expander("Nguồn thông tin", expanded=False):
    st.caption(f"{len(rooms):,} tin phòng hợp lệ · Bản dữ liệu: {updated_at or 'Chưa rõ ngày'}")
    st.caption("Web đọc bản dữ liệu đã xuất từ SQL Server; giá và tình trạng phòng cần kiểm tra lại với bên đăng tin.")

st.subheader("Tùy chọn tìm trọ")
l, r = st.columns(2, gap="large")
with l:
    budget_max = st.slider("Ngân sách tối đa (triệu/tháng)", 1.0, 6.0, 2.5, 0.1)
    set_min = st.checkbox("Có ngân sách tối thiểu")
    budget_min = st.number_input("Ngân sách tối thiểu", 1.0, float(budget_max), 1.0, 0.1) if set_min else None
    budget_mode = st.radio("Khoảng giá", ["Nghiêm ngặt", "Có giao nhau"], horizontal=True,
                           help="Nghiêm ngặt: toàn bộ khoảng giá phải nằm trong ngân sách.")
with r:
    use_distance = st.checkbox("Giới hạn khoảng cách đến FPT", value=True)
    max_distance = st.slider("Khoảng cách tối đa (km)", 0.5, 20.0, 3.0, 0.5, disabled=not use_distance)
    areas = sorted({str(x.get("area_name")).strip() for x in rooms if x.get("area_name")})
    selected_areas = st.multiselect("Khu vực", areas, placeholder="Tất cả khu vực")
    area_mode = st.radio("Chọn khu vực", ["Ưu tiên", "Bắt buộc"], horizontal=True,
                         disabled=not selected_areas)

st.markdown("**Tiện ích cần có và mong muốn**")
st.caption("Chọn theo 4 nhóm. Mỗi tiện ích chỉ được tick một trong hai cột.")
required, preferred = select_amenities(catalog)

try:
    need = build_need_from_selection(
        budget_max=budget_max, budget_min=budget_min,
        budget_mode="strict" if budget_mode == "Nghiêm ngặt" else "overlap",
        max_distance=max_distance if use_distance else None,
        areas=selected_areas, area_mode="soft" if area_mode == "Ưu tiên" else "hard",
        required=required, preferred=preferred,
    )
    result = run_recommendation(rooms, need, catalog, top_n=10)
except Exception as exc:
    st.error(f"Không thể tìm phòng: {exc}")
    st.stop()

st.divider()
st.subheader("Phòng trọ dành cho bạn")
a, b = st.columns(2)
a.metric("Phòng phù hợp", result["eligible_count"])
b.metric("Cần kiểm tra thêm", result["unverified_count"])

if not result["top10"]:
    st.info("Chưa có phòng phù hợp với các điều kiện đã chọn. Hãy thử nới giới hạn giá hoặc khoảng cách.")
else:
    st.caption("Kết quả tự cập nhật khi bạn thay đổi bộ lọc. Chỉ hiển thị điểm phù hợp tổng trên thang 100.")
    for i, room in enumerate(result["top10"], 1):
        room_card(room, i, catalog)
    c1, c2 = st.columns(2)
    c1.download_button("Tải danh sách (.csv)", csv_bytes(result), "trohoalac_top10.csv",
                       "text/csv", use_container_width=True)
    c2.download_button("Tải dữ liệu (.json)", json_bytes(result), "trohoalac_top10.json",
                       "application/json", use_container_width=True)

if result["unverified_count"]:
    with st.expander(f"Phòng cần xác minh ({result['unverified_count']})"):
        for i, room in enumerate(result["needs_verification"], 1):
            room_card(room, i, catalog, uncertain=True)

st.divider()
st.caption("TroHoaLac · Thông tin phòng chỉ mang tính tham khảo; hãy mở bài đăng gốc để xác nhận trước khi thuê.")
