#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analytics Engine — Аналитика «Было / Стало» с Work, Critical, Milestone, RAG, прогнозом
"""

import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

log = logging.getLogger("analytics")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
XML_DIR = DATA_DIR / "xml_data"
SNAPSHOTS_DIR = DATA_DIR / "xml_snapshots"
SNAPSHOTS_DIR.mkdir(exist_ok=True)

import sys
sys.path.insert(0, str(BASE_DIR))
from src.wbs_parser import (
    parse_msproject_xml, build_wbs_tree, aggregate_costs,
    task_status, task_status_label, get_departments_for_resources, Task,
    get_resource_work_map
)

# ------------------------------------------------------------
#  СПИСОК СНАПШОТОВ
# ------------------------------------------------------------
def list_snapshots() -> List[Dict[str, Any]]:
    snaps = [{
        "id": "current",
        "label": "Текущие данные (xml_data/)",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "xml_count": len(list(XML_DIR.glob("*.xml"))) if XML_DIR.exists() else 0,
    }]
    if SNAPSHOTS_DIR.exists():
        for folder in sorted(SNAPSHOTS_DIR.iterdir()):
            if folder.is_dir() and not folder.name.startswith("."):
                cnt = len(list(folder.glob("*.xml")))
                if cnt > 0:
                    snaps.append({
                        "id": folder.name,
                        "label": folder.name + " (" + str(cnt) + " файлов)",
                        "date": folder.name,
                        "xml_count": cnt,
                    })
    return snaps

def _resolve_snapshot_dir(snap_id: str) -> Path:
    if snap_id == "current":
        return XML_DIR
    return SNAPSHOTS_DIR / snap_id

def load_snapshot(snap_id: str) -> Dict[str, Any]:
    xml_dir = _resolve_snapshot_dir(snap_id)
    if not xml_dir.exists():
        return {"error": "Папка не найдена: " + str(xml_dir)}
    xml_files = sorted(xml_dir.glob("*.xml"))
    if not xml_files:
        return {"error": "Нет XML в " + str(xml_dir)}
    projects: Dict[str, Dict] = {}
    all_tasks: List[Task] = []
    for fpath in xml_files:
        try:
            flat, res_map = parse_msproject_xml(fpath)
            for t in flat:
                t.file_source = fpath.name
            tree = build_wbs_tree(list(flat))
            aggregate_costs(tree)
            projects[fpath.name] = {
                "name": fpath.name,
                "tasks": flat,
                "tree": tree,
            }
            all_tasks.extend(flat)
        except Exception as e:
            log.error("Ошибка парсинга %s: %s", fpath.name, e)
    return {"projects": projects, "all_tasks": all_tasks}

# ------------------------------------------------------------
#  PV (Planned Value) — линейная интерполяция
# ------------------------------------------------------------
def _pv_pct(start_s: str, finish_s: str, cutoff: date) -> float:
    if not start_s or not finish_s:
        return 0.0
    try:
        s = datetime.strptime(start_s[:10], "%Y-%m-%d").date()
        f = datetime.strptime(finish_s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0.0
    total = (f - s).days
    if total <= 0:
        return 100.0 if cutoff >= f else 0.0
    if cutoff <= s:
        return 0.0
    if cutoff >= f:
        return 100.0
    return round((cutoff - s).days / total * 100, 2)

# ------------------------------------------------------------
#  RAG статус
# ------------------------------------------------------------
def _rag_status(spi: float, overdue_pct: float, no_resource_pct: float = 0.0) -> str:
    if spi < 0.7 or overdue_pct > 20 or no_resource_pct > 30:
        return "red"
    if spi < 0.9 or overdue_pct > 10:
        return "yellow"
    return "green"

# ------------------------------------------------------------
#  МЕТРИКИ ПРОЕКТА (с Work, прогнозом, RAG)
# ------------------------------------------------------------
def compute_project_metrics(proj: Dict, cutoff: date) -> Dict[str, Any]:
    tasks = proj["tasks"]
    leaf = [t for t in tasks if not t.summary]
    total = len(leaf)
    done = sum(1 for t in leaf if t.percent_complete >= 100)
    inprog = sum(1 for t in leaf if 0 < t.percent_complete < 100)
    nostart = total - done - inprog

    bac = sum(t.cost for t in leaf)
    ev = sum(t.cost * t.percent_complete / 100.0 for t in leaf)
    ac = sum(t.actual_cost for t in leaf)
    pv = sum(t.cost * _pv_pct(t.start, t.finish, cutoff) / 100.0 for t in leaf)

    cv = ev - ac
    sv = ev - pv
    cpi = round(ev / ac, 3) if ac else 0.0
    spi = round(ev / pv, 3) if pv else 0.0

    # Work
    total_work = sum(t.work for t in leaf)
    remaining_work = sum(t.remaining_work for t in leaf)

    # Просрочки
    overdue = []
    for t in leaf:
        if t.finish and t.percent_complete < 100:
            try:
                fd = datetime.strptime(t.finish[:10], "%Y-%m-%d").date()
                if fd < cutoff:
                    overdue.append({
                        "uid": t.uid, "name": t.name,
                        "finish": t.finish[:10],
                        "percent": t.percent_complete,
                        "delay_days": (cutoff - fd).days,
                        "resources": t.resources,
                        "is_critical": t.is_critical,
                    })
            except (ValueError, TypeError):
                pass
    overdue_count = len(overdue)
    overdue_pct = round(overdue_count / total * 100, 1) if total else 0

    # Доля задач без ресурса
    no_resource = sum(1 for t in leaf if not t.resources)
    no_resource_pct = round(no_resource / total * 100, 1) if total else 0

    # RAG статус
    rag = _rag_status(spi, overdue_pct, no_resource_pct)

    # Прогнозная дата финиша (на основе SPI и оставшейся длительности)
    forecast_finish = None
    if spi > 0 and pv > 0:
        all_finishes = [datetime.strptime(t.finish[:10], "%Y-%m-%d").date() for t in leaf if t.finish]
        if all_finishes:
            planned_finish = max(all_finishes)
            remaining_days = (planned_finish - cutoff).days
            if remaining_days > 0:
                forecast_days = remaining_days / spi
                forecast_finish = cutoff + timedelta(days=int(forecast_days))
                forecast_finish = forecast_finish.strftime("%Y-%m-%d")

    return {
        "total": total, "done": done, "in_progress": inprog,
        "not_started": nostart,
        "completion_pct": round(done / total * 100, 1) if total else 0,
        "bac": round(bac, 2), "ev": round(ev, 2), "ac": round(ac, 2),
        "pv": round(pv, 2), "cv": round(cv, 2), "sv": round(sv, 2),
        "cpi": cpi, "spi": spi,
        "overdue_count": overdue_count,
        "overdue_tasks": sorted(overdue, key=lambda x: -x["delay_days"]),
        "total_work": round(total_work, 2),
        "remaining_work": round(remaining_work, 2),
        "rag_status": rag,
        "forecast_finish": forecast_finish,
        "no_resource_pct": no_resource_pct,
    }

# ------------------------------------------------------------
#  МЕТРИКИ ИСПОЛНИТЕЛЕЙ (с учётом Work и загрузки)
# ------------------------------------------------------------
def compute_resource_metrics(all_tasks: List[Task], cutoff: date) -> List[Dict]:
    bucket: Dict[str, Dict] = {}
    for t in all_tasks:
        if t.summary:
            continue
        n_res = max(len(t.resources), 1)
        share = 1.0 / n_res

        for res in (t.resources or ["—без ресурса—"]):
            if res not in bucket:
                dept = get_departments_for_resources([res])
                bucket[res] = {
                    "name": res,
                    "department": dept[0] if dept else "—",
                    "total": 0, "done": 0, "inprog": 0, "nostart": 0,
                    "bac": 0.0, "ev": 0.0, "ac": 0.0,
                    "work": 0.0, "remaining_work": 0.0,
                    "overdue": [], "delay_sum": 0,
                }
            b = bucket[res]
            b["total"] += 1
            if t.percent_complete >= 100:
                b["done"] += 1
            elif t.percent_complete > 0:
                b["inprog"] += 1
            else:
                b["nostart"] += 1

            b["ev"] += t.cost * t.percent_complete / 100.0 * share
            b["bac"] += t.cost * share
            b["ac"] += t.actual_cost * share
            b["work"] += t.work * share
            b["remaining_work"] += t.remaining_work * share

            if t.finish and t.percent_complete < 100:
                try:
                    fd = datetime.strptime(t.finish[:10], "%Y-%m-%d").date()
                    if fd < cutoff:
                        delay = (cutoff - fd).days
                        b["overdue"].append({
                            "uid": t.uid, "name": t.name,
                            "project": t.file_source,
                            "finish": t.finish[:10],
                            "percent": t.percent_complete,
                            "delay_days": delay,
                            "is_critical": t.is_critical,
                        })
                        b["delay_sum"] += delay
                except (ValueError, TypeError):
                    pass

    result = []
    for res, b in bucket.items():
        completion = round(b["done"] / b["total"] * 100, 1) if b["total"] else 0
        weighted = round(b["ev"] / b["bac"] * 100, 1) if b["bac"] > 0 else completion

        ev_ratio = b["ev"] / b["bac"] if b["bac"] > 0 else 0
        penalty = min(b["delay_sum"] / 200.0, 1.0)
        pi = round(ev_ratio * (1 - penalty * 0.5) * 100, 1)
        color = "green" if pi >= 60 else ("yellow" if pi >= 30 else "red")

        result.append({
            "name": res, "department": b["department"],
            "total": b["total"], "done": b["done"],
            "inprog": b["inprog"], "nostart": b["nostart"],
            "completion_pct": completion,
            "weighted_pct": weighted,
            "ev": round(b["ev"], 2), "bac": round(b["bac"], 2),
            "ac": round(b["ac"], 2),
            "work": round(b["work"], 2),
            "remaining_work": round(b["remaining_work"], 2),
            "overdue_count": len(b["overdue"]),
            "overdue_tasks": sorted(b["overdue"], key=lambda x: -x["delay_days"]),
            "delay_sum": b["delay_sum"],
            "delay_avg": round(b["delay_sum"] / len(b["overdue"]), 1) if b["overdue"] else 0,
            "productivity_index": pi,
            "status_color": color,
        })
    result.sort(key=lambda x: x["productivity_index"])
    return result

# ------------------------------------------------------------
#  ТАЙМЛАЙН PV / EV / AC
# ------------------------------------------------------------
def compute_weekly_timeline(all_tasks: List[Task], cutoff: date) -> Dict[str, Any]:
    leaf = [t for t in all_tasks if not t.summary]
    if not leaf:
        return {"labels": [], "pv": [], "ev": 0, "ac": 0, "bac": 0}
    starts = []
    finishes = []
    for t in leaf:
        if t.start:
            try:
                starts.append(datetime.strptime(t.start[:10], "%Y-%m-%d").date())
            except:
                pass
        if t.finish:
            try:
                finishes.append(datetime.strptime(t.finish[:10], "%Y-%m-%d").date())
            except:
                pass
    if not starts or not finishes:
        return {"labels": [], "pv": [], "ev": 0, "ac": 0, "bac": 0}
    min_date = min(starts)
    max_date = max(max(finishes), cutoff)
    ev = sum(t.cost * t.percent_complete / 100.0 for t in leaf)
    ac = sum(t.actual_cost for t in leaf)
    bac = sum(t.cost for t in leaf)
    total_days = (max_date - min_date).days
    step = timedelta(days=30) if total_days > 365 else timedelta(days=7)
    labels = []
    pv_values = []
    current = min_date
    while current <= max_date:
        pv = sum(t.cost * _pv_pct(t.start, t.finish, current) / 100.0 for t in leaf)
        labels.append(current.strftime("%Y-%m-%d"))
        pv_values.append(round(pv, 2))
        current += step
    if labels and labels[-1] != max_date.strftime("%Y-%m-%d"):
        pv = sum(t.cost * _pv_pct(t.start, t.finish, max_date) / 100.0 for t in leaf)
        labels.append(max_date.strftime("%Y-%m-%d"))
        pv_values.append(round(pv, 2))
    return {
        "labels": labels,
        "pv": pv_values,
        "ev": round(ev, 2),
        "ac": round(ac, 2),
        "bac": round(bac, 2),
    }

# ------------------------------------------------------------
#  ТЕПЛОВАЯ КАРТА (по Work вместо количества задач)
# ------------------------------------------------------------
def compute_resource_project_matrix(all_tasks: List[Task]) -> Dict[str, Any]:
    matrix: Dict[str, Dict[str, Any]] = {}
    resources_set = set()
    projects_set = set()
    for t in all_tasks:
        if t.summary:
            continue
        n_res = max(len(t.resources), 1)
        share_work = t.work / n_res
        for res in (t.resources or ["—"]):
            resources_set.add(res)
            projects_set.add(t.file_source)
            key = res + "||" + t.file_source
            if key not in matrix:
                matrix[key] = {"work": 0.0}
            matrix[key]["work"] += share_work
    data_list = []
    for key, val in matrix.items():
        parts = key.split("||", 1)
        data_list.append({
            "resource": parts[0],
            "project": parts[1] if len(parts) > 1 else "",
            "work": round(val["work"], 2),
        })
    return {
        "resources": sorted(resources_set),
        "projects": sorted(projects_set),
        "data": data_list,
    }

# ------------------------------------------------------------
#  ДИНАМИКА ПРОСРОЧЕК
# ------------------------------------------------------------
def compute_overdue_dynamics(all_tasks: List[Task], cutoff: date) -> Dict[str, Any]:
    leaf = [t for t in all_tasks if not t.summary and t.finish]
    if not leaf:
        return {"labels": [], "counts": []}
    finishes = []
    for t in leaf:
        try:
            finishes.append(datetime.strptime(t.finish[:10], "%Y-%m-%d").date())
        except:
            pass
    if not finishes:
        return {"labels": [], "counts": []}
    min_finish = min(finishes)
    start_point = min_finish - timedelta(days=min_finish.weekday())
    labels = []
    counts = []
    current = start_point
    while current <= cutoff:
        overdue_count = 0
        for t in leaf:
            if t.percent_complete >= 100:
                continue
            try:
                fd = datetime.strptime(t.finish[:10], "%Y-%m-%d").date()
                if fd < current:
                    overdue_count += 1
            except:
                pass
        labels.append(current.strftime("%Y-%m-%d"))
        counts.append(overdue_count)
        current += timedelta(days=7)
    return {"labels": labels, "counts": counts}

# ------------------------------------------------------------
#  ПОНЕДЕЛЬНЫЙ ПРОФИЛЬ ЗАГРУЗКИ РЕСУРСОВ (НОВОЕ)
# ------------------------------------------------------------
def compute_resource_work_profile(all_tasks: List[Task], start_date: date, end_date: date) -> Dict[str, Any]:
    """
    Возвращает для каждого ресурса понедельные трудозатраты (часы).
    Упрощённо: равномерно распределяем work между start и finish задачи.
    """
    if not all_tasks:
        return {"weeks": [], "data": []}
    
    # Генерируем список недель между start_date и end_date
    weeks = []
    current = start_date
    while current <= end_date:
        weeks.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=7)
    
    if not weeks:
        return {"weeks": [], "data": []}
    
    # Инициализируем профиль: ресурс -> массив часов по неделям
    profile = {}
    
    for task in all_tasks:
        if task.summary or not task.start or not task.finish:
            continue
        try:
            t_start = datetime.strptime(task.start[:10], "%Y-%m-%d").date()
            t_finish = datetime.strptime(task.finish[:10], "%Y-%m-%d").date()
        except:
            continue
        
        # Пропускаем задачи, которые не пересекаются с окном
        if t_finish < start_date or t_start > end_date:
            continue
        
        # Обрезаем до окна
        actual_start = max(t_start, start_date)
        actual_finish = min(t_finish, end_date)
        total_days = (actual_finish - actual_start).days + 1
        if total_days <= 0:
            continue
        
        # Распределяем work равномерно по дням
        work_per_day = task.work / total_days if total_days > 0 else 0
        
        # Для каждого ресурса задачи
        n_res = max(len(task.resources), 1)
        share_work_per_day = work_per_day / n_res
        
        for res in (task.resources or ["—без ресурса—"]):
            if res not in profile:
                profile[res] = [0.0] * len(weeks)
            # Для каждой недели, которая попадает в интервал, добавляем часы
            for i, week_start_str in enumerate(weeks):
                week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
                week_end = week_start + timedelta(days=6)
                # Пересечение недели с [actual_start, actual_finish]
                inter_start = max(actual_start, week_start)
                inter_end = min(actual_finish, week_end)
                if inter_start <= inter_end:
                    days_in_week = (inter_end - inter_start).days + 1
                    profile[res][i] += share_work_per_day * days_in_week
    
    # Преобразуем в список для JSON
    data = []
    for resource, values in profile.items():
        data.append({
            "resource": resource,
            "values": [round(v, 1) for v in values]
        })
    
    return {"weeks": weeks, "data": data}

# ------------------------------------------------------------
#  ОДИНОЧНЫЙ СРЕЗ
# ------------------------------------------------------------
def single_snapshot_analytics(snap_id: str, cutoff_str: str) -> Dict[str, Any]:
    try:
        cutoff = datetime.strptime(cutoff_str, "%Y-%m-%d").date() if cutoff_str else date.today()
    except:
        cutoff = date.today()
    data = load_snapshot(snap_id)
    if "error" in data:
        return data
    project_metrics = []
    for pname, pdata in data["projects"].items():
        m = compute_project_metrics(pdata, cutoff)
        m["project"] = pname
        project_metrics.append(m)
    resource_metrics = compute_resource_metrics(data["all_tasks"], cutoff)
    timeline = compute_weekly_timeline(data["all_tasks"], cutoff)
    heatmap = compute_resource_project_matrix(data["all_tasks"])
    overdue_dynamics = compute_overdue_dynamics(data["all_tasks"], cutoff)

    total_projects = len(project_metrics)
    red_count = sum(1 for p in project_metrics if p.get("rag_status") == "red")
    yellow_count = sum(1 for p in project_metrics if p.get("rag_status") == "yellow")
    green_count = total_projects - red_count - yellow_count

    return {
        "snapshot": snap_id,
        "cutoff": cutoff.strftime("%Y-%m-%d"),
        "projects": project_metrics,
        "resources": resource_metrics,
        "timeline": timeline,
        "heatmap": heatmap,
        "overdue_dynamics": overdue_dynamics,
        "rag_summary": {"red": red_count, "yellow": yellow_count, "green": green_count},
    }

# ------------------------------------------------------------
#  СРАВНЕНИЕ ДВУХ СРЕЗОВ
# ------------------------------------------------------------
def _delta(a, b, key):
    va = (a or {}).get(key, 0) or 0
    vb = (b or {}).get(key, 0) or 0
    return round(vb - va, 2)

def compare_snapshots(snap1: str, snap2: str,
                      cutoff1_str: str, cutoff2_str: str) -> Dict[str, Any]:
    try:
        c1 = datetime.strptime(cutoff1_str, "%Y-%m-%d").date() if cutoff1_str else date.today()
    except:
        c1 = date.today()
    try:
        c2 = datetime.strptime(cutoff2_str, "%Y-%m-%d").date() if cutoff2_str else date.today()
    except:
        c2 = date.today()
    d1 = load_snapshot(snap1)
    d2 = load_snapshot(snap2)
    if "error" in d1:
        return d1
    if "error" in d2:
        return d2

    all_proj = sorted(set(list(d1["projects"].keys()) + list(d2["projects"].keys())))
    proj_cmp = []
    for pn in all_proj:
        m1 = compute_project_metrics(d1["projects"][pn], c1) if pn in d1["projects"] else None
        m2 = compute_project_metrics(d2["projects"][pn], c2) if pn in d2["projects"] else None
        entry = {"project": pn, "before": m1, "after": m2}
        if m1 and m2:
            entry["delta"] = {
                k: _delta(m1, m2, k)
                for k in ["done", "in_progress", "not_started",
                           "completion_pct", "ev", "ac", "cv", "sv",
                           "overdue_count", "total_work", "remaining_work"]
            }
        proj_cmp.append(entry)

    res1 = compute_resource_metrics(d1["all_tasks"], c1)
    res2 = compute_resource_metrics(d2["all_tasks"], c2)
    r1_map = {r["name"]: r for r in res1}
    r2_map = {r["name"]: r for r in res2}
    all_res = sorted(set(list(r1_map.keys()) + list(r2_map.keys())))
    res_cmp = []
    for rn in all_res:
        rb = r1_map.get(rn)
        ra = r2_map.get(rn)
        entry = {
            "resource": rn,
            "department": (ra or rb or {}).get("department", "—"),
            "before": rb, "after": ra,
        }
        if rb and ra:
            entry["delta"] = {
                k: _delta(rb, ra, k)
                for k in ["total", "done", "ev", "overdue_count",
                           "delay_sum", "productivity_index", "work", "remaining_work"]
            }
        res_cmp.append(entry)

    timeline1 = compute_weekly_timeline(d1["all_tasks"], c1)
    timeline2 = compute_weekly_timeline(d2["all_tasks"], c2)
    overdue1 = compute_overdue_dynamics(d1["all_tasks"], c1)
    overdue2 = compute_overdue_dynamics(d2["all_tasks"], c2)
    heatmap1 = compute_resource_project_matrix(d1["all_tasks"])
    heatmap2 = compute_resource_project_matrix(d2["all_tasks"])
    top_ev1 = sorted(res1, key=lambda x: x["ev"], reverse=True)[:10]
    top_ev2 = sorted(res2, key=lambda x: x["ev"], reverse=True)[:10]

    return {
        "snap1": snap1, "snap2": snap2,
        "cutoff1": c1.strftime("%Y-%m-%d"),
        "cutoff2": c2.strftime("%Y-%m-%d"),
        "projects": proj_cmp,
        "resources": res_cmp,
        "timeline1": timeline1,
        "timeline2": timeline2,
        "overdue_dynamics1": overdue1,
        "overdue_dynamics2": overdue2,
        "heatmap1": heatmap1,
        "heatmap2": heatmap2,
        "top_ev1": top_ev1,
        "top_ev2": top_ev2,
    }