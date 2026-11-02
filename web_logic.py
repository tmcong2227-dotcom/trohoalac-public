# -*- coding: utf-8 -*-
"""Adapter độc lập UI: đưa input đã chọn vào mô hình WSM và xuất file kết quả.

Không dùng Streamlit ở đây để có thể kiểm thử độc lập và tái sử dụng cho API sau này.
"""
from __future__ import annotations

import csv
import io
import json
from urllib.parse import urlsplit

from recommend import CODE_GROUP, DEFAULT_IMPORTANCE, LABELS, recommend, validate_need

PRIORITY_LABELS = {"Thấp": "low", "Vừa": "medium", "Cao": "high"}


def supported_catalog(database_codes):
    """Không cho người dùng chọn code không hỗ trợ bởi mô hình hoặc không có trong DB."""
    return sorted(set(database_codes).intersection(CODE_GROUP), key=lambda c: LABELS[c].casefold())


def build_need_from_selection(
    *, budget_max, budget_min=None, max_distance=None, areas=None,
    area_mode="soft", budget_mode="strict", required=None,
    preferred=None, importance=None, priority=None,
):
    """Chuyển form HTML/Streamlit về JSON input chính thức của recommend.py."""
    required = list(dict.fromkeys(required or []))
    preferred = list(dict.fromkeys(preferred or []))
    importance = importance or {}
    priority = priority or {}
    desired = {
        code: int(importance.get(code, DEFAULT_IMPORTANCE[CODE_GROUP[code]]))
        for code in preferred if code not in required
    }
    need = {
        "budget_max": budget_max,
        "budget_min": budget_min,
        "budget_mode": budget_mode,
        "max_distance": max_distance,
        "areas": list(areas or []),
        "area_mode": area_mode,
        "required_amenities": required,
        "preferred_amenities": desired,
        "criterion_priority": {k: priority.get(k, "medium") for k in
                               ("price", "distance", "amenities", "area")},
    }
    return validate_need(need)


def run_recommendation(rooms, need, available_codes, top_n=10):
    missing = (set(need["required_amenities"]) | set(need["preferred_amenities"])) - set(available_codes)
    if missing:
        raise ValueError("Tiện ích chưa có trong dữ liệu SQL: " + ", ".join(sorted(missing)))
    return recommend(rooms, need, top_n=top_n)


def safe_source_url(url):
    if not isinstance(url, str):
        return None
    value = url.strip()
    if not value or any(c in value for c in "\r\n\t"):
        return None
    parts = urlsplit(value)
    return value if parts.scheme in ("http", "https") and parts.netloc else None


def format_price(lo, hi):
    if lo is None:
        return "Chưa rõ giá"
    low = f"{float(lo):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if hi is not None and float(hi) > float(lo):
        high = f"{float(hi):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"{low}–{high} triệu/tháng"
    return f"{low} triệu/tháng"


def csv_bytes(result):
    output = io.StringIO(newline="")
    cols = ["rank", "listing_id", "property_name", "area_name", "address_raw", "source_type", "source_name",
            "monthly_rent_million", "rent_max_million", "distance_to_fpt_km",
            "floor_area_m2", "score", "price_points", "distance_points",
            "amenity_points", "area_points", "notes", "source_url"]
    writer = csv.DictWriter(output, fieldnames=cols)
    writer.writeheader()
    for rank, room in enumerate(result["top10"], 1):
        writer.writerow({
            **{key: room.get(key) for key in cols},
            "rank": rank,
            "price_points": room["contributions"].get("price", 0),
            "distance_points": room["contributions"].get("distance", 0),
            "amenity_points": room["contributions"].get("amenities", 0),
            "area_points": room["contributions"].get("area", 0),
            "notes": "; ".join(room.get("notes", [])),
        })
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def json_bytes(result):
    return json.dumps(result, ensure_ascii=False, indent=2, default=str).encode("utf-8")
