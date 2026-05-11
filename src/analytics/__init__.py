#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль аналитики «Было / Стало» по проектам и исполнителям.

## Содержит:
- analytics_engine.py — расчёт EVM, метрик исполнителей, сравнение срезов
"""

from .analytics_engine import (
    list_snapshots,
    load_snapshot,
    single_snapshot_analytics,
    compare_snapshots,
    compute_project_metrics,
    compute_resource_metrics,
    compute_weekly_timeline,
    compute_resource_project_matrix,
    compute_overdue_dynamics,
    compute_resource_work_profile,   # новая функция для профиля загрузки
)

__all__ = [
    "list_snapshots",
    "load_snapshot",
    "single_snapshot_analytics",
    "compare_snapshots",
    "compute_project_metrics",
    "compute_resource_metrics",
    "compute_weekly_timeline",
    "compute_resource_project_matrix",
    "compute_overdue_dynamics",
    "compute_resource_work_profile",
]