#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WBS Parser + EVM (PMBOK) + Work + Assignments + Critical + Milestone
"""

import sys
import json
import logging
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.config import XML_DIR, DATA_DIR, BASE_DIR

LOG_DIR = BASE_DIR / "logs"

LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("wbs_parser")

FIELD_ID_PLAN = 188743767
FIELD_ID_ACTUAL = 188743769

# ===========================================================================
#  МАППИНГ СОТРУДНИК → ОТДЕЛ
# ===========================================================================
EMPLOYEE_DEPT: Dict[str, str] = {
    "Белов Максим (ТХ)": "Департамент проектирования",
    "Лёшина Галина": "ЭС",
    "Спиров Дмитрий": "ССиА",
    "Денисов Алексей": "ИО",
    "Субподряд": "Субподряд",
    "Налиухин Дмитрий": "Э",
    "Немченко Егор": "ГИП",
    "Слобожан Александра": "АСО",
    "Исавнин Максим": "ОГП",
    "Корсакова Софья": "АСО",
    "Буржинская Елена": "ЭС",
    "Насрединов Сергей": "ТХ",
    "Шилов Константин": "ССиА",
    "Крылова Светлана": "ТХ",
    "Костичева (Сафонова) Юлия": "ТХ",
    "Ящерицын Александр": "АСО",
    "Морозов Вадим": "АСО",
    "Блинов Захар": "АСО",
    "Храпова Ольга": "ИО",
    "Сикидин Игорь": "ССиА",
    "Говорков Станислав": "ГИП",
    "Барабанов Павел": "ОУП",
    "Андреева Ольга": "КР",
    "Ромашов Александр": "ЭС",
    "Насрединов Сергей (ИО)": "ИО",
    "Бердышева Маргарита": "ИО",
    "Кошкин Сергей": "ССиА",
    "Иванова Ольга": "КР",
    "Тихонов Денис": "АСО",
    "Канина Галина": "АСО",
    "Грибков Антон": "КР",
    "Байков Вадим": "ССиА",
    "Савенкова Алла": "ТХ",
    "Белов Максим": "Департамент проектирования",
    "Пелевин Александр": "ГИП",
    "Макшаков Антон": "ОУП",
    "Шкурат Александр": "ИО",
    "Тарасов Андрей": "ТХ",
    "Котов Кирилл": "ГИП",
    "Бытотова Светлана": "Э",
    "Грибанова Яна": "АСО",
    "Денисов Евгений": "ИО",
    "Нет": "Нет",
    "Сушков Иван": "ГИП",
    "Рустам Жолдакаев": "ГИП",
    "Заказчик": "Заказчик",
    "Галина Канина": "АСО",
    "Шкурат Александр, Белов Никита": "Общая задача",
    "Сергеев Максим": "КР",
    "Голубев Андрей": "КР",
    "Литвин Георгий": "АСО",
    "Белов Никита": "ИО",
    "Подрядчик": "Подрядчик",
    "Сушков Иван, Рустам Жолдакаев": "Общая задача",
    "Яцков Тимофей": "АСО",
    "Дорошенко Владимир": "ИО",
    "Касьянова Анна": "—",
    "Сметный отдел": "—",
    "Назаров Вадим": "—",
}


def get_departments_for_resources(resources: List[str]) -> List[str]:
    depts = set()
    for r in resources:
        r_stripped = r.strip()
        if r_stripped in EMPLOYEE_DEPT:
            depts.add(EMPLOYEE_DEPT[r_stripped])
        else:
            found = False
            for emp, dept in EMPLOYEE_DEPT.items():
                if r_stripped.lower() == emp.lower():
                    depts.add(dept)
                    found = True
                    break
            if not found:
                depts.add("—")
    return sorted(depts)


@dataclass
class Assignment:
    task_uid: str
    resource_uid: str
    work: float = 0.0
    actual_work: float = 0.0
    remaining_work: float = 0.0
    units: float = 1.0
    start: str = ""
    finish: str = ""


@dataclass
class Task:
    uid: str = ""
    id_: str = ""
    name: str = ""
    outline_level: int = 0
    outline_number: str = ""
    start: str = ""
    finish: str = ""
    duration: str = ""
    remaining_duration: str = ""
    percent_complete: int = 0
    summary: bool = False
    milestone: bool = False
    is_critical: bool = False
    resources: List[str] = field(default_factory=list)
    assignments: List[Assignment] = field(default_factory=list)
    children: List["Task"] = field(default_factory=list)
    file_source: str = ""
    cost: float = 0.0
    actual_cost: float = 0.0
    work: float = 0.0
    remaining_work: float = 0.0


def task_status(pct: int) -> str:
    if pct >= 100: return "done"
    elif pct > 0: return "inprogress"
    return "notstarted"


def task_status_label(pct: int) -> str:
    if pct >= 100: return "Завершена"
    elif pct > 0: return "В работе"
    return "Не начата"


def detect_namespace(xml_path: Path) -> dict:
    for _, elem in ET.iterparse(str(xml_path), events=["start"]):
        if elem.tag.startswith("{"):
            return {"ms": elem.tag.split("}")[0][1:]}
    return {}


def parse_duration_to_hours(dur_str: str) -> float:
    if not dur_str:
        return 0.0
    dur_str = dur_str.strip()
    if dur_str.startswith("PT"):
        dur_str = dur_str[2:]
    if "P" in dur_str and "T" not in dur_str:
        if dur_str.endswith("D"):
            try:
                days = float(dur_str[1:-1])
                return days * 8.0
            except:
                pass
    import re
    hours = 0.0
    minutes = 0.0
    h_match = re.search(r"(\d+(?:\.\d+)?)H", dur_str)
    m_match = re.search(r"(\d+(?:\.\d+)?)M", dur_str)
    if h_match:
        hours = float(h_match.group(1))
    if m_match:
        minutes = float(m_match.group(1))
    return hours + minutes / 60.0


def parse_msproject_xml(xml_path: Path) -> Tuple[List[Task], Dict[str, str]]:
    log.info(f"Парсинг: {xml_path.name}")
    ns = detect_namespace(xml_path)
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    def t(tag): return f"{{{ns['ms']}}}{tag}" if ns else tag

    resources_map = {}
    for res in root.iter(t("Resource")):
        ue = res.find(t("UID"))
        ne = res.find(t("Name"))
        if ue is not None and ne is not None:
            u = (ue.text or "").strip()
            n = (ne.text or "").strip()
            if u and n:
                resources_map[u] = n

    assignments_by_task: Dict[str, List[Assignment]] = {}
    for assign in root.iter(t("Assignment")):
        tu = assign.find(t("TaskUID"))
        ru = assign.find(t("ResourceUID"))
        if tu is None or ru is None:
            continue
        task_uid = (tu.text or "").strip()
        res_uid = (ru.text or "").strip()
        if not task_uid:
            continue

        work_el = assign.find(t("Work"))
        actual_work_el = assign.find(t("ActualWork"))
        remaining_work_el = assign.find(t("RemainingWork"))
        units_el = assign.find(t("Units"))
        start_el = assign.find(t("Start"))
        finish_el = assign.find(t("Finish"))

        work = parse_duration_to_hours(work_el.text) if work_el is not None else 0.0
        actual_work = parse_duration_to_hours(actual_work_el.text) if actual_work_el is not None else 0.0
        remaining_work = parse_duration_to_hours(remaining_work_el.text) if remaining_work_el is not None else 0.0
        units = 1.0
        if units_el is not None and units_el.text:
            try:
                units = float(units_el.text) / 100.0
            except:
                pass
        start = start_el.text[:10] if start_el is not None else ""
        finish = finish_el.text[:10] if finish_el is not None else ""

        ass = Assignment(
            task_uid=task_uid,
            resource_uid=res_uid,
            work=work,
            actual_work=actual_work,
            remaining_work=remaining_work,
            units=units,
            start=start,
            finish=finish,
        )
        assignments_by_task.setdefault(task_uid, []).append(ass)

    tasks = []
    for task_el in root.iter(t("Task")):
        uid_el = task_el.find(t("UID"))
        if uid_el is None:
            continue
        uid_val = (uid_el.text or "").strip()

        plan_val = None
        actual_val = None
        for ext in task_el.iterfind(t("ExtendedAttribute")):
            fid_el = ext.find(t("FieldID"))
            if fid_el is None or not fid_el.text:
                continue
            try:
                fid = int(fid_el.text)
            except ValueError:
                continue
            val_el = ext.find(t("Value"))
            if val_el is None or not val_el.text:
                continue
            val_str = val_el.text.strip()
            try:
                num = float(val_str.replace(" ", "").replace(",", "."))
            except ValueError:
                continue
            if fid == FIELD_ID_PLAN:
                plan_val = num
            elif fid == FIELD_ID_ACTUAL:
                actual_val = num

        if plan_val is None:
            cost_el = task_el.find(t("Cost"))
            if cost_el is not None and cost_el.text:
                try:
                    plan_val = float(cost_el.text.strip().replace(" ", "").replace(",", "."))
                except ValueError:
                    pass
        if actual_val is None:
            actual_cost_el = task_el.find(t("ActualCost"))
            if actual_cost_el is not None and actual_cost_el.text:
                try:
                    actual_val = float(actual_cost_el.text.strip().replace(" ", "").replace(",", "."))
                except ValueError:
                    pass
        if plan_val is None:
            plan_val = 0.0
        if actual_val is None:
            actual_val = 0.0

        work_el = task_el.find(t("Work"))
        work = parse_duration_to_hours(work_el.text) if work_el is not None else 0.0
        remaining_work_el = task_el.find(t("RemainingWork"))
        remaining_work = parse_duration_to_hours(remaining_work_el.text) if remaining_work_el is not None else 0.0

        duration_el = task_el.find(t("Duration"))
        duration = duration_el.text if duration_el is not None else ""
        remaining_duration_el = task_el.find(t("RemainingDuration"))
        remaining_duration = remaining_duration_el.text if remaining_duration_el is not None else ""

        is_critical = False
        crit_el = task_el.find(t("IsCritical"))
        if crit_el is not None and crit_el.text == "1":
            is_critical = True
        is_milestone = False
        mile_el = task_el.find(t("Milestone"))
        if mile_el is not None and mile_el.text == "1":
            is_milestone = True

        def gv(tag, default=""):
            el = task_el.find(t(tag))
            return (el.text or "").strip() if el is not None else default

        tsk = Task(
            uid=uid_val,
            id_=gv("ID"),
            name=gv("Name"),
            outline_level=int(gv("OutlineLevel", "0")),
            outline_number=gv("OutlineNumber"),
            start=gv("Start")[:10] if gv("Start") else "",
            finish=gv("Finish")[:10] if gv("Finish") else "",
            duration=duration,
            remaining_duration=remaining_duration,
            percent_complete=int(gv("PercentComplete", "0")),
            summary=gv("Summary", "0") == "1",
            milestone=is_milestone,
            is_critical=is_critical,
            resources=[],
            assignments=assignments_by_task.get(uid_val, []),
            file_source=xml_path.name,
            cost=plan_val,
            actual_cost=actual_val,
            work=work,
            remaining_work=remaining_work,
        )
        tasks.append(tsk)

    for tsk in tasks:
        res_names = []
        for ass in tsk.assignments:
            if ass.resource_uid in resources_map:
                res_names.append(resources_map[ass.resource_uid])
        tsk.resources = list(dict.fromkeys(res_names))

    log.info(f"  → {len(tasks)} задач, {len(resources_map)} ресурсов")
    return tasks, resources_map


def build_wbs_tree(flat_tasks: List[Task]) -> List[Task]:
    if not flat_tasks:
        return []
    roots, stack = [], []
    for tsk in flat_tasks:
        while stack and stack[-1].outline_level >= tsk.outline_level:
            stack.pop()
        if stack:
            stack[-1].children.append(tsk)
        else:
            roots.append(tsk)
        stack.append(tsk)
    return roots


def aggregate_costs(tasks: List[Task]) -> None:
    for task in tasks:
        if task.children:
            aggregate_costs(task.children)
            task.cost = sum(c.cost for c in task.children)
            task.actual_cost = sum(c.actual_cost for c in task.children)
            task.work = sum(c.work for c in task.children)
            task.remaining_work = sum(c.remaining_work for c in task.children)


def get_projects_data_as_json() -> Dict[str, Any]:
    log.info("=" * 60)
    log.info("WBS Parser — получение данных в формате JSON")
    log.info("=" * 60)

    if not XML_DIR.exists():
        return {"error": f"Папка {XML_DIR} не найдена!"}
    xml_files = sorted(XML_DIR.glob("*.xml"))
    if not xml_files:
        return {"error": f"Нет XML файлов в {XML_DIR}"}
    log.info(f"XML файлов: {len(xml_files)}")

    projects = []
    all_tasks_flat = []

    for fpath in xml_files:
        fname = fpath.name
        log.info(f"  {fname}")
        try:
            flat, _ = parse_msproject_xml(fpath)
            for t in flat:
                t.file_source = fname
                all_tasks_flat.append(t)
            tree = build_wbs_tree(flat)
            aggregate_costs(tree)
            projects.append({
                "name": fname,
                "tasks_count": len(flat),
                "tree": tree
            })
        except Exception as e:
            log.error(f"  ✗ {fname}: {e}")
            projects.append({"name": fname, "error": str(e), "tasks_count": 0})

    if not projects:
        return {"error": "Нет данных для отображения"}

    cnt_done = cnt_inprog = cnt_notstarted = 0
    total_tasks = 0
    total_summary = 0
    total_milestones = 0
    all_resources = set()
    all_departments = set()
    max_level = 0

    for t in all_tasks_flat:
        total_tasks += 1
        if t.summary:
            total_summary += 1
        if t.milestone:
            total_milestones += 1
        if not t.summary:
            st = task_status(t.percent_complete)
            if st == "done":
                cnt_done += 1
            elif st == "inprogress":
                cnt_inprog += 1
            else:
                cnt_notstarted += 1
        for r in t.resources:
            all_resources.add(r)
            for d in get_departments_for_resources([r]):
                all_departments.add(d)
        if t.outline_level > max_level:
            max_level = t.outline_level

    def task_to_dict(task: Task) -> Dict:
        return {
            "uid": task.uid,
            "id_": task.id_,
            "name": task.name,
            "outline_level": task.outline_level,
            "outline_number": task.outline_number,
            "start": task.start[:10] if task.start else "",
            "finish": task.finish[:10] if task.finish else "",
            "duration": task.duration,
            "remaining_duration": task.remaining_duration,
            "percent_complete": task.percent_complete,
            "summary": task.summary,
            "milestone": task.milestone,
            "is_critical": task.is_critical,
            "resources": task.resources,
            "departments": get_departments_for_resources(task.resources),
            "file_source": task.file_source,
            "status": task_status(task.percent_complete),
            "status_label": task_status_label(task.percent_complete),
            "cost": task.cost,
            "actual_cost": task.actual_cost,
            "work": round(task.work, 2),
            "remaining_work": round(task.remaining_work, 2),
            "children": [task_to_dict(child) for child in task.children]
        }

    projects_json = []
    for p in projects:
        if "error" in p:
            projects_json.append(p)
        else:
            projects_json.append({
                "name": p["name"],
                "tasks_count": p["tasks_count"],
                "tree": [task_to_dict(t) for t in p["tree"]]
            })

    total_cost = sum(t.cost for t in all_tasks_flat)
    total_actual_cost = sum(t.actual_cost for t in all_tasks_flat)
    total_work = sum(t.work for t in all_tasks_flat)
    total_remaining_work = sum(t.remaining_work for t in all_tasks_flat)

    return {
        "projects": projects_json,
        "stats": {
            "total_tasks": total_tasks,
            "total_summary": total_summary,
            "total_milestones": total_milestones,
            "cnt_notstarted": cnt_notstarted,
            "cnt_inprog": cnt_inprog,
            "cnt_done": cnt_done,
            "max_level": max_level if max_level >= 1 else 5,
            "total_cost": total_cost,
            "total_actual_cost": total_actual_cost,
            "total_work": total_work,
            "total_remaining_work": total_remaining_work,
        },
        "filters": {
            "all_resources": sorted(list(all_resources)),
            "all_departments": sorted(list(all_departments))
        }
    }


if __name__ == "__main__":
    print("WBS Parser")
    data = get_projects_data_as_json()
    if "error" in data:
        print(f"Ошибка: {data['error']}")
    else:
        print(f"Успешно загружено {len(data['projects'])} проектов")
def get_resource_work_map(tasks: List[Task]) -> Dict[str, Dict[str, float]]:
    res_map = {}
    for t in tasks:
        if t.summary:
            continue
        n_res = max(len(t.resources), 1)
        share_work = t.work / n_res
        share_remaining = t.remaining_work / n_res
        for res in t.resources:
            if res not in res_map:
                res_map[res] = {"work": 0.0, "remaining_work": 0.0, "actual_work": 0.0}
            res_map[res]["work"] += share_work
            res_map[res]["remaining_work"] += share_remaining
            res_map[res]["actual_work"] = res_map[res]["work"] - res_map[res]["remaining_work"]
    return res_map




