import pytest
from datetime import date
from src.analytics.analytics_engine import _pv_pct, _rag_status

def test_pv_pct():
    # Задача с 1 по 10 января, срез 5 января
    pv = _pv_pct("2025-01-01", "2025-01-10", date(2025,1,5))
    # 4 дня прошло из 9 (разница в днях: 10-1=9, 5-1=4) -> 44.44%
    assert 44 <= pv <= 45

def test_rag_status():
    assert _rag_status(0.6, 0, 0) == "red"
    assert _rag_status(0.8, 15, 0) == "yellow"
    assert _rag_status(0.95, 5, 0) == "green"
    assert _rag_status(0.9, 25, 0) == "red"      # overdue >20%
    assert _rag_status(0.85, 12, 35) == "red"    # no resource >30%