#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from .config import LOG_DIR, NOTES_FILE, XML_DIR, SNAPSHOTS_DIR
sys.path.insert(0, str(Path(__file__).parent))

 

# Логирование
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / "server.log"
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
log = logging.getLogger(__name__)

# Импорт wbs_parser
log.info("Импорт модуля wbs_parser...")
try:
    from . import wbs_parser
    required_functions = [
        'get_projects_data_as_json',
        'task_status',
        'task_status_label',
        'get_departments_for_resources'
    ]
    missing = [f for f in required_functions if not hasattr(wbs_parser, f)]
    if missing:
        log.error(f"Отсутствуют функции: {missing}")
        sys.exit(1)
    get_projects_data = wbs_parser.get_projects_data_as_json
    task_status = wbs_parser.task_status
    task_status_label = wbs_parser.task_status_label
    log.info("✓ Модуль wbs_parser импортирован успешно")
except Exception as e:
    log.error(f"Ошибка импорта wbs_parser: {e}")
    sys.exit(1)

# Импорт аналитики
log.info("Импорт модуля analytics...")
try:
    from .analytics import (
        list_snapshots,
        single_snapshot_analytics,
        compare_snapshots,
        compute_resource_work_profile,
    )
    ANALYTICS_AVAILABLE = True
    log.info("✓ Модуль analytics импортирован успешно")
except ImportError as e:
    log.warning(f"⚠ Модуль analytics не доступен: {e}")
    ANALYTICS_AVAILABLE = False

# Flask
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"))

# Заметки
notes_storage = {}
notes_file = NOTES_FILE

def load_notes():
    global notes_storage
    if notes_file.exists():
        with open(notes_file, 'r', encoding='utf-8') as f:
            notes_storage = json.load(f)
        log.info(f"Загружено {len(notes_storage)} заметок")
    else:
        notes_storage = {}

def save_notes():
    with open(notes_file, 'w', encoding='utf-8') as f:
        json.dump(notes_storage, f, ensure_ascii=False, indent=2)
    log.info(f"Сохранено {len(notes_storage)} заметок")

load_notes()

# Маршруты
@app.route('/')
def index():
    log.info("Запрос главной страницы")
    return render_template('index.html')

@app.route('/analytics')
def analytics_page():
    if not ANALYTICS_AVAILABLE:
        return "<h1>Модуль аналитики недоступен</h1>", 500
    return render_template('analytics.html')

@app.route('/api/projects')
def api_projects():
    try:
        data = get_projects_data()
        if data and isinstance(data, dict) and "error" in data:
            return jsonify(data), 500
        return jsonify(data)
    except Exception as e:
        log.error(f"Ошибка получения данных: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes/<string:project_name>/<string:task_uid>', methods=['GET'])
def get_note(project_name, task_uid):
    key = f"{project_name}:{task_uid}"
    return jsonify({"note": notes_storage.get(key, "")})

@app.route('/api/notes/<string:project_name>/<string:task_uid>', methods=['POST'])
def save_note(project_name, task_uid):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Нет данных"}), 400
    note_text = data.get('note', '')
    key = f"{project_name}:{task_uid}"
    if note_text:
        notes_storage[key] = note_text
    elif key in notes_storage:
        del notes_storage[key]
    save_notes()
    return jsonify({"status": "ok", "note": note_text})

@app.route('/api/analytics/snapshots', methods=['GET'])
def api_analytics_snapshots():
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    snaps = list_snapshots()
    return jsonify(snaps)

@app.route('/api/analytics/single', methods=['GET'])
def api_analytics_single():
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    snap_id = request.args.get('snapshot', 'current')
    cutoff = request.args.get('cutoff', datetime.now().strftime('%Y-%m-%d'))
    result = single_snapshot_analytics(snap_id, cutoff)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/analytics/compare', methods=['GET'])
def api_analytics_compare():
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    snap1 = request.args.get('snap1', 'current')
    snap2 = request.args.get('snap2', 'current')
    cutoff1 = request.args.get('cutoff1', datetime.now().strftime('%Y-%m-%d'))
    cutoff2 = request.args.get('cutoff2', datetime.now().strftime('%Y-%m-%d'))
    result = compare_snapshots(snap1, snap2, cutoff1, cutoff2)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route('/api/analytics/resource_profile', methods=['GET'])
def api_resource_profile():
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    snap_id = request.args.get('snapshot', 'current')
    start = request.args.get('start')
    end = request.args.get('end')
    from .analytics import load_snapshot
    data = load_snapshot(snap_id)
    if "error" in data:
        return jsonify(data), 400
    today = datetime.now().date()
    start_date = start and datetime.strptime(start, "%Y-%m-%d").date() or today - timedelta(days=30)
    end_date = end and datetime.strptime(end, "%Y-%m-%d").date() or today + timedelta(days=90)
    profile = compute_resource_work_profile(data["all_tasks"], start_date, end_date)
    return jsonify(profile)

@app.route('/api/health')
def health():
    xml_count = len(list(XML_DIR.glob("*.xml"))) if XML_DIR.exists() else 0
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "xml_count": xml_count,
        "analytics_available": ANALYTICS_AVAILABLE,
        "notes_count": len(notes_storage)
    })

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("WBS Viewer + EVM + Analytics — Веб-сервер")
    print("=" * 60)
    print(f"Папка с XML:        {XML_DIR}")
    print(f"Папка снапшотов:    {SNAPSHOTS_DIR}")
    print(f"Файл заметок:       {notes_file}")
    print("Аналитика доступна:", ANALYTICS_AVAILABLE)
    if XML_DIR.exists():
        xml_files = list(XML_DIR.glob("*.xml"))
        print(f"Найдено XML файлов: {len(xml_files)}")
    else:
        print(f"ВНИМАНИЕ: Папка {XML_DIR} не найдена!")
    if SNAPSHOTS_DIR.exists():
        snap_folders = [f for f in SNAPSHOTS_DIR.iterdir() if f.is_dir()]
        print(f"Папок снапшотов: {len(snap_folders)}")
    print("\nСервер запускается...")
    print("Откройте в браузере:")
    print("  WBS Viewer:  http://127.0.0.1:5000")
    print("  Аналитика:   http://127.0.0.1:5000/analytics")
    print("=" * 60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
