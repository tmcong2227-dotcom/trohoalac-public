# -*- coding: utf-8 -*-
"""Presentational helpers. Do not change filtering or Weighted Sum scoring."""
from __future__ import annotations

from statistics import median
from recommend import AMENITY_GROUPS, LABELS, amenity_state, number

# The existing model has 5 technical groups. Show 4 easy-to-understand groups:
# BUILDING amenities are displayed alongside ROOM_LAYOUT in "Không gian".
DISPLAY_GROUPS = {
    'Nội thất': AMENITY_GROUPS['FURNISHING'],
    'Không gian': AMENITY_GROUPS['ROOM_LAYOUT'] + AMENITY_GROUPS['BUILDING'],
    'An ninh': AMENITY_GROUPS['SECURITY'],
    'Xung quanh': AMENITY_GROUPS['NEARBY'],
}
RADAR_KEYS = ['Giá', 'Gần FPT', 'Nội thất', 'Không gian', 'An ninh', 'Xung quanh']


def address_display(room):
    address = (room.get('address_raw') or '').strip()
    if not address or address.casefold() in {'chưa rõ', 'chưa xác định', 'không rõ', 'n/a', 'null'}:
        return 'Chưa có địa chỉ cụ thể'
    return address


def amenities_table(room, catalog=None):
    """All amenity states, not only user-selected preferred amenities."""
    amenities = room.get('amenities') or {}
    available_codes = set(catalog or [])
    output = []
    for group, all_codes in DISPLAY_GROUPS.items():
        for code in all_codes:
            if available_codes and code not in available_codes:
                continue
            state = amenity_state(amenities.get(code))
            output.append({
                'Nhóm': group,
                'Tiện ích': LABELS.get(code, code),
                'Trạng thái': 'Có' if state == 1 else ('Không' if state == 0 else 'Chưa xác minh'),
                'Đã xác nhận': state == 1,
            })
    return output


def _facility_score(room, codes):
    """1=yes, 0=no, 0.5=unknown. A visualization estimate, not verified facts."""
    amenities = room.get('amenities') or {}
    values = [amenity_state(amenities.get(c)) for c in codes]
    return 100 * sum(0.5 if v is None else v for v in values) / len(values) if values else 50.


def radar_scores(room, *, max_distance=None):
    """Six comparable 0..100 measures; independent from WSM's ranking weights.

    Price: 1-6m product-wide band; distance: 0-10km fixed or user's cap;
    amenities: group-average with unknown=0.5. Higher means more favourable.
    Neither rating nor room size is invented from missing data.
    """
    price = number(room.get('monthly_rent_million'))
    distance = number(room.get('distance_to_fpt_km'))
    dcap = number(max_distance)
    if not dcap or dcap <= 0:
        dcap = 10.0
    metrics = {
        'Giá': 100 * max(0, min(1, (6 - price) / 5)) if price is not None else 50.,
        'Gần FPT': 100 * max(0, min(1, 1 - distance / dcap)) if distance is not None else 50.,
        'Nội thất': _facility_score(room, DISPLAY_GROUPS['Nội thất']),
        'Không gian': _facility_score(room, DISPLAY_GROUPS['Không gian']),
        'An ninh': _facility_score(room, DISPLAY_GROUPS['An ninh']),
        'Xung quanh': _facility_score(room, DISPLAY_GROUPS['Xung quanh']),
    }
    return {k: round(v, 1) for k, v in metrics.items()}


def median_radar(rooms, *, max_distance=None):
    if not rooms:
        return {}
    records = [radar_scores(r, max_distance=max_distance) for r in rooms]
    return {k: round(median(row[k] for row in records), 1) for k in RADAR_KEYS}
