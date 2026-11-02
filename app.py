# -*- coding: utf-8 -*-
"""TroHoaLac | Web công khai tối giản. Input động -> Weighted Sum -> Top 10.

Chỉ đọc JSON công khai đã xuất từ SQL Server; không công khai tài khoản database.
Thuật toán gốc nằm trong recommend.py và không được chỉnh theo giao diện.
"""
from collections import Counter
from datetime import datetime
from html import escape
import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from recommend import CODE_GROUP, DEFAULT_IMPORTANCE, LABELS
from price_policy import eligible_price
from room_view import DISPLAY_GROUPS, RADAR_KEYS, address_display, amenities_table, median_radar, radar_scores
from web_logic import build_need_from_selection, csv_bytes, format_price, json_bytes, run_recommendation, safe_source_url

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="TroHoaLac | Tìm trọ", page_icon="⌂", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
  .block-container{max-width:1120px;padding-top:1.6rem;padding-bottom:4rem}
  .stApp { background:#fff; color:#111; }
  h1,h2,h3{letter-spacing:-.035em}
  h1{font-weight:780!important;font-size:2.4rem!important}
  h2{font-weight:700!important;font-size:1.45rem!important}
  [data-testid="stMetricValue"]{font-size:1.32rem}
  [data-testid="stMetricLabel"]{color:#555;font-size:.82rem}
  div[data-testid="stButton"] button[kind="primary"]{background:#111;color:white;border:1px solid #111}
  div[data-testid="stButton"] button[kind="primary"]:hover{background:#333;color:white}
  div[data-testid="stDownloadButton"] button {border-radius:8px}
  div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:10px;border:1px solid #ddd}
  .brand{font-size:.85rem;letter-spacing:.18em;font-weight:850;color:#111}
  .muted{color:#666;font-size:.87rem}
  .thin-rule{border-top:1px solid #ddd;margin:.65rem 0 1rem}
  .rank{color:#444;font-size:.81rem;font-weight:700;letter-spacing:.06em}
  .room-title{font-weight:750;font-size:1.3rem;line-height:1.3}
  .score{display:inline-block;border:1px solid #111;padding:.27rem .55rem;border-radius:6px;font-weight:750}
  .fineprint{color:#777;font-size:.8rem}
  @media(max-width:720px){h1{font-size:1.95rem!important}.block-container{padding:1rem .75rem 3rem}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_snapshot():
    path = ROOT / "data" / "rooms_public.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        raise ValueError("File data/rooms_public.json không đúng định dạng.")
    rooms = data["rooms"]
    if not all(isinstance(r, dict) and isinstance(r.get("amenities"), dict) for r in rooms):
        raise ValueError("Dữ liệu phòng thiếu trường amenities.")
    return [r for r in rooms if eligible_price(r)], set(data.get("catalog", [])), data.get("exported_at")


def unset_other(code, chosen):
    """Không cho chọn cùng một tiện ích vừa cứng vừa mềm."""
    if st.session_state.get(f"{chosen}_{code}"):
        st.session_state[f"{'soft' if chosen == 'hard' else 'hard'}_{code}"] = False


def amenity_inputs(catalog):
    """Four tabs with visible checkboxes; retain original technical codes."""
    required, preferred = [], []
    tabs = st.tabs(list(DISPLAY_GROUPS))
    for tab, (label, codes) in zip(tabs, DISPLAY_GROUPS.items()):
        with tab:
            c1, c2 = st.columns(2)
            c1.caption("BẮT BUỘC CÓ · lọc cứng")
            c2.caption("MONG MUỐN CÓ · cộng điểm")
            for code in codes:
                if code not in catalog or code not in CODE_GROUP:
                    continue
                name = LABELS.get(code, code)
                with c1:
                    hard = st.checkbox(name, key=f"hard_{code}", on_change=unset_other, args=(code, "hard"))
                with c2:
                    soft = st.checkbox(name, key=f"soft_{code}", on_change=unset_other, args=(code, "soft"))
                if hard:
                    required.append(code)
                elif soft:
                    preferred.append(code)
    return required, preferred


def radar_chart(rooms, selected, additional, distance_limit):
    def trace(values, title, color, dash="solid", width=2):
        vals = [values[k] for k in RADAR_KEYS]
        return go.Scatterpolar(
            r=vals + vals[:1], theta=RADAR_KEYS + RADAR_KEYS[:1],
            name=title, mode="lines+markers", fill="none",
            line={"color": color, "width": width, "dash": dash},
            marker={"size": 5}, hovertemplate="%{theta}: %{r:.1f}/100<extra>%{fullData.name}</extra>",
        )

    chart = go.Figure()
    chart.add_trace(trace(median_radar(rooms, max_distance=distance_limit), "Trung vị Top 10", "#B0B0B0", "dash", 2))
    for i, room in enumerate(additional):
        chart.add_trace(trace(radar_scores(room, max_distance=distance_limit),
                              str(room.get("property_name") or "Phòng khác")[:40],
                              ["#666666", "#999999", "#CCCCCC"][i % 3], "dot", 1.5))
    chart.add_trace(trace(radar_scores(selected, max_distance=distance_limit),
                          str(selected.get("property_name") or "Phòng đang chọn")[:40], "#111111", "solid", 3.5))
    chart.update_layout(
        template="plotly_white", height=420, margin=dict(l=42, r=42, t=24, b=30),
        paper_bgcolor="white", plot_bgcolor="white", font=dict(color="#111111"),
        polar={"bgcolor":"white", "radialaxis":{"range":[0,100],"tickvals":[0,25,50,75,100],
                 "gridcolor":"#E5E5E5","linecolor":"#DDD"},
                 "angularaxis":{"gridcolor":"#E5E5E5","linecolor":"#DDD"}},
        legend={"orientation":"h", "y":-0.12, "x":0, "font":{"size":11}},
        showlegend=True,
    )
    return chart


def pretty_number(value, unit=""):
    try:
        return f"{float(value):g}{unit}" if value is not None else "Chưa có dữ liệu"
    except (TypeError, ValueError):
        return "Chưa có dữ liệu"


def render_room(room, rank, catalog, tentative=False):
    with st.container(border=True):
        left, right = st.columns([5,1.2], vertical_alignment="top")
        with left:
            st.markdown(f'<div class="rank">#{rank:02d} / {"CẦN XÁC MINH" if tentative else "TOP 10"}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="room-title">{escape(str(room.get("property_name") or "Chưa có tên trọ"))}</div>', unsafe_allow_html=True)
        with right:
            st.markdown(f'<div class="score">{room["score"]:.1f}/100</div>', unsafe_allow_html=True)
        # Six required outputs: name above, plus area, detailed address, rent, size and distance.
        a, b, c = st.columns(3)
        a.metric("Khu vực", str(room.get("area_name") or "Chưa có dữ liệu"))
        b.metric("Giá thuê", format_price(room.get("monthly_rent_million"), room.get("rent_max_million")))
        c.metric("Diện tích", pretty_number(room.get("floor_area_m2"), " m²"))
        a2, b2 = st.columns([2,1])
        a2.markdown(f"**Địa chỉ cụ thể:** {escape(address_display(room))}")
        b2.markdown(f"**Cách FPT:** {pretty_number(room.get('distance_to_fpt_km'), ' km')}")
        st.caption("Nguồn: " + str(room.get("source_name") or room.get("source_type") or "Chưa rõ") +
                   (" · ID: " + str(room["listing_id"]) if room.get("listing_id") is not None else ""))
        if address_display(room) == "Chưa có địa chỉ cụ thể":
            st.caption("Chưa có địa chỉ được xác minh trong dữ liệu nguồn. Không tự tạo địa chỉ.")
        if tentative and room.get("filter_notes"):
            st.caption("Cần xác minh: " + "; ".join(room["filter_notes"]))
        if room.get("notes"):
            st.caption(" · ".join(room["notes"]))
        with st.expander("Danh mục tiện ích và chi tiết điểm"):
            table = amenities_table(room, catalog)
            confirmed = [r for r in table if r["Trạng thái"] == "Có"]
            t1, t2 = st.tabs([f"Đã xác nhận có ({len(confirmed)})", "Tất cả trạng thái"])
            with t1:
                if confirmed:
                    st.dataframe([{"Nhóm": r["Nhóm"], "Tiện ích": r["Tiện ích"]} for r in confirmed],
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("Chưa có tiện ích nào được dữ liệu xác nhận là có.")
            with t2:
                st.dataframe([{"Nhóm": r["Nhóm"], "Tiện ích": r["Tiện ích"], "Trạng thái": r["Trạng thái"]}
                              for r in table], use_container_width=True, hide_index=True)
                st.caption("'Chưa xác minh' khác với 'Không có'.")
            st.markdown("**Điểm thành phần Weighted Sum**")
            contributions = room.get("contributions") or {}
            st.dataframe([{"Tiêu chí": {"price":"Giá", "distance":"Khoảng cách", "amenities":"Tiện ích", "area":"Khu vực"}.get(k,k),
                           "Điểm đóng góp": round(v,2)} for k,v in contributions.items()],
                         use_container_width=True, hide_index=True)
        url = safe_source_url(room.get("source_url"))
        if url:
            st.link_button("Xem tin gốc", url)


try:
    rooms, catalog, exported_at = load_snapshot()
except Exception as exc:
    st.error(f"Không đọc được nguồn dữ liệu: {exc}")
    st.stop()

st.markdown('<div class="brand">TROHOALAC / FIND YOUR SPACE</div>', unsafe_allow_html=True)
st.title("Tìm trọ phù hợp với bạn.")
st.markdown('<div class="muted">Chọn điều bạn cần. Kết quả thay đổi theo nhu cầu, được xếp hạng bằng Hard Filtering + Weighted Sum.</div>', unsafe_allow_html=True)
st.markdown('<div class="thin-rule"></div>', unsafe_allow_html=True)
if not rooms:
    st.error("Chưa có phòng hợp lệ trong data/rooms_public.json. Hãy xuất dữ liệu SQL và cập nhật file trên GitHub.")
    st.stop()

with st.expander("Nguồn dữ liệu & lưu ý", expanded=False):
    st.write(f"{len(rooms):,} bản ghi giá từ 1–6 triệu/tháng · Cập nhật: {exported_at or 'Chưa có'}")
    st.caption("Web công khai sử dụng bản JSON đã xuất từ SQL Server; không kết nối database theo thời gian thực. Giá, địa chỉ và tình trạng trống cần được xác minh với nguồn đăng.")

st.subheader("01 / Bộ lọc tìm trọ")
left, right = st.columns(2, gap="large")
with left:
    budget_max = st.slider("Ngân sách tối đa (triệu/tháng)", 1.0, 6.0, 2.5, 0.1)
    min_toggle = st.checkbox("Có ngân sách tối thiểu")
    budget_min = st.number_input("Ngân sách tối thiểu", 1.0, float(budget_max), 1.0, 0.1) if min_toggle else None
    budget_mode = st.radio("Khoảng giá", ["Nghiêm ngặt", "Có giao nhau"], horizontal=True,
                           help="Nghiêm ngặt: toàn bộ khoảng giá nằm trong ngân sách. Có giao nhau: chỉ cần một phần khoảng giá thỏa mãn.")
with right:
    use_distance = st.checkbox("Giới hạn khoảng cách tới FPT", value=True)
    max_distance = st.slider("Tối đa (km)", .5, 20., 3., .5, disabled=not use_distance)
    areas = sorted({str(r.get("area_name")).strip() for r in rooms if r.get("area_name")})
    selected_areas = st.multiselect("Khu vực", areas, placeholder="Tất cả khu vực")
    area_mode = st.radio("Áp dụng khu vực", ["Ưu tiên", "Bắt buộc"], horizontal=True, disabled=not selected_areas)

st.markdown("**Tiện ích**")
st.caption("Tick ở cột **Bắt buộc** để lọc cứng; tick ở cột **Mong muốn** để cộng điểm. Mỗi tiện ích chỉ được chọn một loại.")
required, preferred = amenity_inputs(catalog)

with st.expander("Tùy chỉnh mức ưu tiên (tùy chọn)"):
    st.caption("Mặc định theo Proposal 4A: giá 40%, khoảng cách 30%, tiện ích 30%; nếu ưu tiên khu vực: 36% / 27% / 27% / 10%.")
    priorities = {}
    cols = st.columns(4)
    for col, (key, label) in zip(cols, [('price','Giá'),('distance','Khoảng cách'),('amenities','Tiện ích'),('area','Khu vực')]):
        priorities[key] = {'Thấp':'low','Vừa':'medium','Cao':'high'}[col.selectbox(label, ['Thấp','Vừa','Cao'], index=1, key=f'priority_{key}')]
    importance = {}
    for code in preferred:
        default = DEFAULT_IMPORTANCE[CODE_GROUP[code]]
        importance[code] = st.select_slider(f"{LABELS[code]} – độ quan trọng", [1, 2, 3], default, key=f"importance_{code}")

try:
    need = build_need_from_selection(
        budget_max=budget_max, budget_min=budget_min,
        max_distance=max_distance if use_distance else None,
        areas=selected_areas, area_mode='soft' if area_mode == 'Ưu tiên' else 'hard',
        budget_mode='strict' if budget_mode == 'Nghiêm ngặt' else 'overlap',
        required=required, preferred=preferred, importance=importance, priority=priorities,
    )
    # Reactive: on every selection Streamlit reruns and re-ranks directly (no static preview).
    result = run_recommendation(rooms, need, catalog, top_n=10)
except Exception as exc:
    st.error(f"Không thể tính kết quả: {exc}")
    st.stop()

st.divider()
st.subheader("02 / Kết quả đề xuất")
m1, m2, m3 = st.columns(3)
m1.metric("Phòng phù hợp", result['eligible_count'])
m2.metric("Sau gộp trùng", result['unique_rooms'])
m3.metric("Cần xác minh", result['unverified_count'])
top10 = result['top10']
if not top10:
    st.write("Không có phòng đáp ứng đầy đủ điều kiện. Hãy tăng ngân sách, nới khoảng cách hoặc bỏ bớt tiện ích bắt buộc.")
else:
    st.caption("Kết quả được cập nhật khi bạn thay đổi các lựa chọn ở trên.")
    st.markdown("### So sánh Top 10 · biểu đồ lục giác")
    names = {i: f"#{i+1:02d} – {r.get('property_name') or 'Phòng chưa rõ tên'}" for i,r in enumerate(top10)}
    a,b = st.columns(2)
    selected_index = a.selectbox("Phòng đang xem", list(names), format_func=lambda i: names[i])
    other_indices = b.multiselect("So sánh thêm (tối đa 3 phòng)",
                                  [i for i in names if i != selected_index],
                                  format_func=lambda i: names[i], max_selections=3)
    st.plotly_chart(radar_chart(top10, top10[selected_index], [top10[i] for i in other_indices],
                                max_distance if use_distance else None), use_container_width=True)
    st.caption("Trục 0–100: càng cao càng thuận lợi. Giá chuẩn hóa trong khoảng 1–6 triệu; gần FPT theo giới hạn km bạn chọn (mặc định 10 km nếu không giới hạn); nhóm tiện ích tính Có=1, Không=0, Chưa xác minh=0,5. Đường xám đứt là trung vị Top 10. Biểu đồ để so sánh, KHÔNG thay thế điểm Weighted Sum.")
    st.markdown("### Danh sách phòng")
    for rank, r in enumerate(top10,1):
        render_room(r, rank, catalog)

    x,y = st.columns(2)
    x.download_button("Tải Top 10 (.csv)", csv_bytes(result), "trohoalac_top10.csv", "text/csv", use_container_width=True)
    y.download_button("Tải chi tiết (.json)", json_bytes(result), "trohoalac_top10.json", "application/json", use_container_width=True)

if result['unverified_count']:
    with st.expander(f"Phòng cần xác minh ({result['unverified_count']}) – không thuộc Top 10"):
        for rank,r in enumerate(result['needs_verification'],1):
            render_room(r,rank,catalog, tentative=True)
st.divider()
st.markdown('<div class="fineprint">TroHoaLac · Dữ liệu tham khảo. Không xác nhận phòng còn trống, thông tin có thể thay đổi theo thời gian.</div>', unsafe_allow_html=True)
