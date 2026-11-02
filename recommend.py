# -*- coding: utf-8 -*-
"""Core TroHoaLac: input có cấu trúc -> hard filter -> Weighted Sum -> Top-N.

Chỉ dùng thư viện chuẩn Python. Không phụ thuộc giao diện hay kết nối SQL.
Không tự sửa hoặc nới điều kiện bắt buộc của người dùng.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

AMENITY_GROUPS = {
    "FURNISHING": ["AIR_CON", "FRIDGE", "WATER_HEATER", "BED_MATTRESS",
                   "WARDROBE", "STUDY_DESK", "KITCHEN_COUNTER"],
    "ROOM_LAYOUT": ["WINDOW", "BALCONY", "LOFT", "OPEN_VIEW", "DRYING_AREA",
                    "SEPARATE_KITCHEN", "PRIVATE_WC"],
    "SECURITY": ["SMART_LOCK", "CCTV", "GUARD", "PARKING"],
    "BUILDING": ["WIFI", "WASHING_MACHINE", "ELEVATOR"],
    "NEARBY": ["MARKET", "SUPERMARKET", "PHARMACY", "GAS_STATION",
               "BUS_STATION", "EATERY"],
}
LABELS = {
    "AIR_CON": "Điều hòa", "FRIDGE": "Tủ lạnh", "WATER_HEATER": "Bình nóng lạnh",
    "BED_MATTRESS": "Giường/nệm", "WARDROBE": "Tủ quần áo",
    "STUDY_DESK": "Bàn học/làm việc", "KITCHEN_COUNTER": "Kệ bếp",
    "WINDOW": "Cửa sổ", "BALCONY": "Ban công", "LOFT": "Gác xép",
    "OPEN_VIEW": "Không gian thoáng", "DRYING_AREA": "Khu phơi đồ",
    "SEPARATE_KITCHEN": "Bếp riêng", "PRIVATE_WC": "WC riêng",
    "SMART_LOCK": "Khóa vân tay/thẻ từ", "CCTV": "Camera", "GUARD": "Bảo vệ",
    "PARKING": "Chỗ để xe", "WIFI": "Wifi", "WASHING_MACHINE": "Máy giặt",
    "ELEVATOR": "Thang máy", "MARKET": "Chợ", "SUPERMARKET": "Siêu thị",
    "PHARMACY": "Nhà thuốc", "GAS_STATION": "Cây xăng", "BUS_STATION": "Bến xe",
    "EATERY": "Quán ăn",
}
DEFAULT_IMPORTANCE = {"FURNISHING": 3, "SECURITY": 3, "ROOM_LAYOUT": 2,
                      "BUILDING": 2, "NEARBY": 1}
CODE_GROUP = {c: g for g, codes in AMENITY_GROUPS.items() for c in codes}
BASE_WEIGHTS = {"price": .40, "distance": .30, "amenities": .30}
BASE_WEIGHTS_SOFT_AREA = {"price": .36, "distance": .27, "amenities": .27, "area": .10}
PRIORITY_LEVEL = {"low": .5, "medium": 1., "high": 1.5}


def number(value):
    """Return valid finite number or None. bool is not a number here."""
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) else None


def amenity_state(value):
    """1: yes; 0: confirmed no; None: unknown. Invalid -> unknown."""
    if value is True or str(value).strip() in {"1", "1.0"}:
        return 1
    if value is False or str(value).strip() in {"0", "0.0"}:
        return 0
    return None


def clamp01(x):
    return min(1., max(0., x))


def validate_need(raw):
    if not isinstance(raw, dict):
        raise ValueError("Nhu cầu phải là JSON object.")
    bmax = number(raw.get("budget_max"))
    bmin = number(raw.get("budget_min"))
    dist = number(raw.get("max_distance"))
    if bmax is None or bmax <= 0:
        raise ValueError("budget_max phải > 0 (triệu đồng/tháng).")
    if bmin is not None and not (0 <= bmin <= bmax):
        raise ValueError("budget_min phải trong khoảng [0, budget_max].")
    if raw.get("max_distance") is not None and (dist is None or dist <= 0):
        raise ValueError("max_distance phải > 0 km hoặc null.")
    budget_mode = raw.get("budget_mode", "overlap")
    area_mode = raw.get("area_mode", "soft")
    if budget_mode not in {"overlap", "strict"}:
        raise ValueError("budget_mode: overlap/strict.")
    if area_mode not in {"soft", "hard"}:
        raise ValueError("area_mode: soft/hard.")
    areas = raw.get("areas") or []
    if not isinstance(areas, list) or any(not isinstance(x, str) for x in areas):
        raise ValueError("areas phải là list tên khu vực.")
    areas = list(dict.fromkeys(a.strip() for a in areas if a.strip()))
    required = raw.get("required_amenities") or []
    preferred = raw.get("preferred_amenities") or {}
    if not isinstance(required, list) or any(not isinstance(c, str) for c in required):
        raise ValueError("required_amenities phải là list mã tiện ích.")
    if isinstance(preferred, list):
        if not all(isinstance(x, dict) and "code" in x for x in preferred):
            raise ValueError("preferred_amenities list phải gồm các {code, importance}.")
        preferred = {x["code"]: x.get("importance") for x in preferred}
    if not isinstance(preferred, dict):
        raise ValueError("preferred_amenities phải là object hoặc list.")
    unknown = (set(required) | set(preferred)) - set(CODE_GROUP)
    if unknown:
        raise ValueError("Mã tiện ích không được hỗ trợ: " + ", ".join(sorted(unknown)))
    preferred_valid = {}
    for code, level in preferred.items():
        if level is None:
            level = DEFAULT_IMPORTANCE[CODE_GROUP[code]]
        if isinstance(level, bool) or level not in (1, 2, 3):
            raise ValueError(f"Mức quan trọng của {code} chỉ được là 1/2/3/null.")
        preferred_valid[code] = int(level)
    priority = raw.get("criterion_priority") or {}
    if not isinstance(priority, dict):
        raise ValueError("criterion_priority phải là object.")
    modifiers = {}
    for name in ("price", "distance", "amenities", "area"):
        value = priority.get(name, "medium")
        if isinstance(value, str):
            value = PRIORITY_LEVEL.get(value.strip().lower())
        if isinstance(value, bool) or value not in (.5, 1, 1.5):
            raise ValueError(f"Mức ưu tiên tiêu chí {name} không hợp lệ (low/medium/high).")
        modifiers[name] = float(value)
    return {"budget_max": bmax, "budget_min": bmin, "max_distance": dist,
            "budget_mode": budget_mode, "areas": areas, "area_mode": area_mode,
            "required_amenities": sorted(set(required)),
            "preferred_amenities": preferred_valid, "criterion_priority": modifiers}


def deduplicate(rooms):
    """One record per dup_group_id; prefer known-price FORM/SURVEY.

    Do NOT fill amenities from a duplicate listing: facts from sources/dates may conflict.
    Keep traceability of representative and group size.
    """
    groups = defaultdict(list)
    for index, room in enumerate(rooms):
        gid = room.get("dup_group_id")
        key = ("G", str(gid)) if gid not in (None, "") else ("L", index)
        groups[key].append(room)

    def rep_key(r):
        source = str(r.get("source_type") or "").upper()
        known_price = number(r.get("monthly_rent_million")) is not None
        source_rank = 0 if source in {"FORM", "SURVEY"} else 1
        known_amenities = sum(amenity_state(v) is not None for v in (r.get("amenities") or {}).values())
        return (not known_price, source_rank, -known_amenities, str(r.get("listing_id", "")))

    output = []
    for rows in groups.values():
        chosen = dict(sorted(rows, key=rep_key)[0])
        chosen["amenities"] = {c: amenity_state(v) for c, v in (chosen.get("amenities") or {}).items()}
        chosen["_duplicate_count"] = len(rows)
        output.append(chosen)
    return output


def check_room(room, need):
    """Return (ok/unverified/reject, explanations).

    'strict' means ALL the declared rent interval must meet the budget.
    'overlap' means there exists an advertised rent within the budget interval.
    """
    rejected, unverified = [], []
    lo, hi = number(room.get("monthly_rent_million")), number(room.get("rent_max_million"))
    if lo is None or lo <= 0:
        unverified.append("Thiếu/không hợp lệ giá thuê")
    else:
        if hi is None:
            hi = lo  # Proposal 4A: COALESCE(max_rent, min_rent)
        if hi < lo or hi <= 0:
            rejected.append("Khoảng giá không hợp lệ")
        elif need["budget_mode"] == "strict":
            if lo < (need["budget_min"] if need["budget_min"] is not None else 0) or hi > need["budget_max"]:
                rejected.append("Khoảng giá không nằm toàn bộ trong ngân sách (strict)")
        elif lo > need["budget_max"] or (need["budget_min"] is not None and hi < need["budget_min"]):
            rejected.append("Khoảng giá không giao ngân sách")
    d = number(room.get("distance_to_fpt_km"))
    if need["max_distance"] is not None:
        if d is None or d < 0:
            unverified.append("Chưa xác minh khoảng cách đến FPT")
        elif d > need["max_distance"]:
            rejected.append("Khoảng cách vượt giới hạn")
    if need["areas"] and need["area_mode"] == "hard":
        area = str(room.get("area_name") or "").strip().casefold()
        if not area:
            unverified.append("Chưa rõ khu vực")
        elif area not in {a.casefold() for a in need["areas"]}:
            rejected.append("Khác khu vực bắt buộc")
    for code in need["required_amenities"]:
        state = amenity_state((room.get("amenities") or {}).get(code))
        if state == 0:
            rejected.append("Xác nhận KHÔNG có " + LABELS[code])
        elif state is None:
            unverified.append("Chưa xác minh " + LABELS[code])
    if rejected:
        return "reject", rejected
    if unverified:
        return "unverified", unverified
    return "ok", []


def effective_weights(need):
    area_soft = bool(need["areas"] and need["area_mode"] == "soft")
    base = BASE_WEIGHTS_SOFT_AREA if area_soft else BASE_WEIGHTS
    enabled = {"price": True, "distance": need["max_distance"] is not None,
               "amenities": bool(need["preferred_amenities"]), "area": area_soft}
    unnormalized = {k: v * need["criterion_priority"][k]
                    for k, v in base.items() if enabled.get(k)}
    total = sum(unnormalized.values())
    return {k: v / total for k, v in unnormalized.items()}


def score_room(room, need, weights):
    lo, hi = number(room.get("monthly_rent_million")), number(room.get("rent_max_million"))
    d = number(room.get("distance_to_fpt_km"))
    scores = {"price": clamp01(1 - lo / need["budget_max"]) if lo and lo > 0 else .5}
    if "distance" in weights:
        scores["distance"] = clamp01(1 - d / need["max_distance"]) if d is not None and d >= 0 else .5
    details, numerator, denominator = {}, 0., 0.
    if "amenities" in weights:
        for code, imp in need["preferred_amenities"].items():
            state = amenity_state((room.get("amenities") or {}).get(code))
            value = .5 if state is None else float(state)  # Proposal: unknown = 0.5, NOT 0
            details[code] = {"name": LABELS[code], "status": "chưa rõ" if state is None else ("có" if state else "không"),
                             "value": value, "importance": imp}
            numerator += imp * value
            denominator += imp
        scores["amenities"] = numerator / denominator
    if "area" in weights:
        scores["area"] = float(str(room.get("area_name") or "").strip().casefold() in
                               {a.casefold() for a in need["areas"]})
    raw = sum(weights[k] * scores[k] for k in weights)
    contributions = {k: round(100 * weights[k] * scores[k], 3) for k in weights}
    notes = []
    if hi is not None and lo is not None and hi > need["budget_max"]:
        notes.append("Khoảng giá giao ngân sách nhưng giá cao nhất vượt ngân sách: hỏi giá phòng cụ thể")
    if room.get("_duplicate_count", 1) > 1:
        notes.append(f"Đại diện {room['_duplicate_count']} bản ghi trùng; không tự trộn thuộc tính khác nguồn")
    missing = [LABELS[c] for c, info in details.items() if info["status"] == "chưa rõ"]
    if missing:
        notes.append("Tiện ích chưa xác minh: " + ", ".join(missing))
    return {"listing_id": room.get("listing_id"), "property_name": room.get("property_name"),
            "area_name": room.get("area_name"), "address_raw": room.get("address_raw"),
            "amenities": dict(room.get("amenities") or {}), "source_type": room.get("source_type"),
            "source_name": room.get("source_name"),
            "source_url": room.get("source_url"), "dup_group_id": room.get("dup_group_id"),
            "monthly_rent_million": lo, "rent_max_million": hi if hi is not None else lo,
            "distance_to_fpt_km": d, "floor_area_m2": number(room.get("floor_area_m2")),
            "score": round(100 * raw, 3), "scores": {k: round(scores[k], 5) for k in weights},
            "contributions": contributions, "amenity_details": details, "notes": notes,
            "_score_sort": raw}


def deduplicate_for_need(rooms, need):
    """Choose ONE real source record per duplicate group, based on this query.

    Confirmed matching source records take priority over unverified/rejected ones.
    Among equally confirmed records, prefer Form/Survey and then better coverage.
    Never merge amenities between different source rows.
    """
    grouped = defaultdict(list)
    for idx, room in enumerate(rooms):
        gid = room.get("dup_group_id")
        group_key = ("G", str(gid)) if gid not in (None, "") else ("L", idx)
        grouped[group_key].append(room)

    status_rank = {"ok": 0, "unverified": 1, "reject": 2}
    chosen_rooms = []
    for options in grouped.values():
        def select_key(rec):
            status, _ = check_room(rec, need)
            source = str(rec.get("source_type") or "").upper()
            known_price = number(rec.get("monthly_rent_million")) is not None
            known_attrs = sum(amenity_state(v) is not None
                              for v in (rec.get("amenities") or {}).values())
            return (status_rank[status], not known_price,
                    0 if source in ("FORM", "SURVEY") else 1,
                    -known_attrs, str(rec.get("listing_id", "")))

        selected = dict(min(options, key=select_key))
        selected["amenities"] = {k: amenity_state(v)
                                 for k, v in (selected.get("amenities") or {}).items()}
        selected["_duplicate_count"] = len(options)
        chosen_rooms.append(selected)
    return chosen_rooms


def recommend(rooms, user_input, top_n=10):
    if not isinstance(rooms, list) or not all(isinstance(r, dict) for r in rooms):
        raise ValueError("Danh sách phòng phải là list JSON objects.")
    if not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n phải là số nguyên dương.")
    need = validate_need(user_input)
    weights = effective_weights(need)
    rooms_unique = deduplicate_for_need(rooms, need)
    approved, uncertain, rejected = [], [], []
    for room in rooms_unique:
        status, reasons = check_room(room, need)
        if status == "reject":
            rejected.append({"listing_id": room.get("listing_id"), "reasons": reasons})
            continue
        item = score_room(room, need, weights)
        item["filter_status"] = status
        item["filter_notes"] = reasons
        if status == "ok":
            approved.append(item)
        else:
            uncertain.append(item)

    def order(r):
        return (-r["_score_sort"],
                r["monthly_rent_million"] if r["monthly_rent_million"] is not None else math.inf,
                r["distance_to_fpt_km"] if r["distance_to_fpt_km"] is not None else math.inf,
                str(r["listing_id"]))

    approved.sort(key=order)
    uncertain.sort(key=order)
    for r in approved + uncertain:
        del r["_score_sort"]
    return {"query": need, "weights": {k: round(v, 6) for k, v in weights.items()},
            "total_raw": len(rooms), "unique_rooms": len(rooms_unique),
            "eligible_count": len(approved), "unverified_count": len(uncertain),
            "rejected_count": len(rejected), "top10": approved[:top_n],
            "needs_verification": uncertain[:top_n], "rejected": rejected}


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def export_results(result, output_dir=HERE / "output"):
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / "result.json"
    csv_path = folder / "top10.csv"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    cols = ["rank", "listing_id", "property_name", "area_name", "address_raw", "source_type",
            "monthly_rent_million", "rent_max_million", "distance_to_fpt_km",
            "floor_area_m2", "score", "price_points", "distance_points",
            "amenity_points", "area_points", "notes", "source_url"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for i, r in enumerate(result["top10"], start=1):
            writer.writerow({"rank": i, **{c: r.get(c) for c in cols},
                             "price_points": r["contributions"].get("price"),
                             "distance_points": r["contributions"].get("distance"),
                             "amenity_points": r["contributions"].get("amenities"),
                             "area_points": r["contributions"].get("area"),
                             "notes": "; ".join(r["notes"])})
    return csv_path, json_path
