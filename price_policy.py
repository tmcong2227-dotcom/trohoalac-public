# -*- coding: utf-8 -*-
"""Luật giá 1.0-6.0 triệu/tháng dùng chung cho SQL-export và web public.

Dữ liệu giá ở đơn vị TRIỆU ĐỒNG/THÁNG, không tự sửa các mức sai.
Giá không xác định, khoảng giá ngược hoặc vượt giới hạn đều không công bố.
"""
from decimal import Decimal, InvalidOperation

MIN_PRICE_MILLION = Decimal("1.0")
MAX_PRICE_MILLION = Decimal("6.0")


def eligible_price(room):
    lo_raw = room.get("monthly_rent_million")
    hi_raw = room.get("rent_max_million")
    try:
        if lo_raw is None or isinstance(lo_raw, bool):
            return False
        lo = Decimal(str(lo_raw))
        if hi_raw is None:
            hi = lo
        else:
            if isinstance(hi_raw, bool):
                return False
            hi = Decimal(str(hi_raw))
    except (InvalidOperation, ValueError, TypeError):
        return False
    return (lo.is_finite() and hi.is_finite()
            and MIN_PRICE_MILLION <= lo <= hi <= MAX_PRICE_MILLION)
