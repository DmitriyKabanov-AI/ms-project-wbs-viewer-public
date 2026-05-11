#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WBS Viewer Server - Веб-сервер для просмотра WBS + Аналитика «Было / Стало»
"""

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

# Добавляем текущую папку в путь
sys.path.insert(0, str(Path(__file__).parent))

# ===========================================================================
#  НАСТРОЙКА ЛОГИРОВАНИЯ (в файл и консоль)
# ===========================================================================
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / "server.log"

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
log = logging.getLogger(__name__)

# ===========================================================================
#  ИМПОРТ ИЗ wbs_parser
# ===========================================================================

log.info("Импорт модуля wbs_parser...")

try:
    import src.wbs_parser as wbs_parser

    required_functions = [
        'get_projects_data_as_json',
        'task_status',
        'task_status_label',
        'get_departments_for_resources'
    ]

    missing = []
    for func in required_functions:
        if hasattr(wbs_parser, func):
            log.info(f"  ✓ {func} найдена")
        else:
            log.error(f"  ✗ {func} не найдена")
            missing.append(func)

    if missing:
        log.error(f"Отсутствуют функции: {missing}")
        sys.exit(1)

    get_projects_data = wbs_parser.get_projects_data_as_json
    task_status = wbs_parser.task_status
    task_status_label = wbs_parser.task_status_label
    get_departments = wbs_parser.get_departments_for_resources

    log.info("✓ Модуль wbs_parser импортирован успешно")

except ImportError as e:
    log.error(f"Ошибка импорта wbs_parser: {e}")
    sys.exit(1)
except Exception as e:
    log.error(f"Ошибка при импорте: {e}")
    sys.exit(1)

# ===========================================================================
#  ИМПОРТ МОДУЛЯ АНАЛИТИКИ
# ===========================================================================

log.info("Импорт модуля analytics...")

try:
    from src.analytics import (
        list_snapshots,
        single_snapshot_analytics,
        compare_snapshots,
        compute_resource_work_profile,
    )
    log.info("✓ Модуль analytics импортирован успешно")
    ANALYTICS_AVAILABLE = True
except ImportError as e:
    log.warning(f"⚠ Модуль analytics не доступен: {e}")
    ANALYTICS_AVAILABLE = False

# ===========================================================================
#  НАСТРОЙКА FLASK
# ===========================================================================

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"))

# ===========================================================================
#  ХРАНИЛИЩЕ ЗАМЕТОК
# ===========================================================================

notes_storage = {}
notes_file = Path(__file__).parent.parent / "data" / "notes.json"


def load_notes():
    """Загружает заметки из файла"""
    global notes_storage
    if notes_file.exists():
        try:
            with open(notes_file, 'r', encoding='utf-8') as f:
                notes_storage = json.load(f)
            log.info(f"Загружено {len(notes_storage)} заметок")
        except Exception as e:
            log.error(f"Ошибка загрузки заметок: {e}")
            notes_storage = {}
    else:
        log.info("Файл заметок не найден, создаем новый")
        notes_storage = {}


def save_notes():
    """Сохраняет заметки в файл"""
    try:
        with open(notes_file, 'w', encoding='utf-8') as f:
            json.dump(notes_storage, f, ensure_ascii=False, indent=2)
        log.info(f"Сохранено {len(notes_storage)} заметок")
    except Exception as e:
        log.error(f"Ошибка сохранения заметок: {e}")


# Загружаем заметки при старте
load_notes()

# ===========================================================================
#  ОСНОВНЫЕ СТРАНИЦЫ
# ===========================================================================

@app.route('/')
def index():
    """Главная страница — WBS Viewer"""
    log.info("Запрос главной страницы")
    return render_template('index.html')


@app.route('/analytics')
def analytics_page():
    """Страница аналитики «Было / Стало»"""
    if not ANALYTICS_AVAILABLE:
        return "<h1>Модуль аналитики недоступен</h1><p>Проверьте наличие папки analytics/</p>", 500
    log.info("Запрос страницы аналитики")
    return render_template('analytics.html')


# ===========================================================================
#  API — ПРОЕКТЫ
# ===========================================================================

@app.route('/api/projects')
def api_projects():
    """Возвращает данные о проектах в формате JSON"""
    log.info("Запрос на получение данных проектов")
    try:
        data = get_projects_data()
        if data and isinstance(data, dict) and "error" in data:
            log.error(f"Ошибка в данных: {data['error']}")
            return jsonify(data), 500
        log.info(f"Успешно получено {len(data.get('projects', []))} проектов")
        return jsonify(data)
    except Exception as e:
        log.error(f"Ошибка получения данных: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ===========================================================================
#  API — ЗАМЕТКИ
# ===========================================================================

@app.route('/api/notes/<string:project_name>/<string:task_uid>', methods=['GET'])
def get_note(project_name, task_uid):
    """Возвращает заметку для конкретной задачи"""
    key = f"{project_name}:{task_uid}"
    note = notes_storage.get(key, "")
    return jsonify({"note": note})


@app.route('/api/notes/<string:project_name>/<string:task_uid>', methods=['POST'])
def save_note(project_name, task_uid):
    """Сохраняет заметку для конкретной задачи"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Нет данных"}), 400

        note_text = data.get('note', '')
        key = f"{project_name}:{task_uid}"

        if note_text:
            notes_storage[key] = note_text
            log.info(f"Сохранена заметка для {key}: {len(note_text)} символов")
        elif key in notes_storage:
            del notes_storage[key]
            log.info(f"Удалена заметка для {key}")

        save_notes()
        return jsonify({"status": "ok", "note": note_text})
    except Exception as e:
        log.error(f"Ошибка сохранения заметки: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/notes/all', methods=['GET'])
def get_all_notes():
    """Возвращает все заметки"""
    return jsonify(notes_storage)


# ===========================================================================
#  API — АНАЛИТИКА
# ===========================================================================

@app.route('/api/analytics/snapshots', methods=['GET'])
def api_analytics_snapshots():
    """Список доступных снапшотов"""
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    try:
        snaps = list_snapshots()
        return jsonify(snaps)
    except Exception as e:
        log.error(f"Ошибка получения снапшотов: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/analytics/single', methods=['GET'])
def api_analytics_single():
    """Аналитика по одному срезу"""
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    try:
        snap_id = request.args.get('snapshot', 'current')
        cutoff = request.args.get('cutoff', datetime.now().strftime('%Y-%m-%d'))
        log.info(f"Аналитика: snapshot={snap_id}, cutoff={cutoff}")
        result = single_snapshot_analytics(snap_id, cutoff)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        log.error(f"Ошибка аналитики: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/analytics/compare', methods=['GET'])
def api_analytics_compare():
    """Сравнение двух срезов"""
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    try:
        snap1 = request.args.get('snap1', 'current')
        snap2 = request.args.get('snap2', 'current')
        cutoff1 = request.args.get('cutoff1', datetime.now().strftime('%Y-%m-%d'))
        cutoff2 = request.args.get('cutoff2', datetime.now().strftime('%Y-%m-%d'))
        log.info(f"Сравнение: {snap1}({cutoff1}) vs {snap2}({cutoff2})")
        result = compare_snapshots(snap1, snap2, cutoff1, cutoff2)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        log.error(f"Ошибка сравнения: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/analytics/resource_profile', methods=['GET'])
def api_resource_profile():
    """Понедельный профиль загрузки ресурсов (часы)"""
    if not ANALYTICS_AVAILABLE:
        return jsonify({"error": "Модуль аналитики недоступен"}), 500
    try:
        snap_id = request.args.get('snapshot', 'current')
        start = request.args.get('start')
        end = request.args.get('end')
        
        from src.analytics import load_snapshot
        data = load_snapshot(snap_id)
        if "error" in data:
            return jsonify(data), 400
        
        today = datetime.now().date()
        start_date = today - timedelta(days=30)
        end_date = today + timedelta(days=90)
        
        if start:
            try:
                start_date = datetime.strptime(start, "%Y-%m-%d").date()
            except:
                pass
        if end:
            try:
                end_date = datetime.strptime(end, "%Y-%m-%d").date()
            except:
                pass
        
        profile = compute_resource_work_profile(data["all_tasks"], start_date, end_date)
        return jsonify(profile)
    except Exception as e:
        log.error(f"Ошибка профиля ресурсов: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ===========================================================================
#  HEALTH CHECK
# ===========================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка работоспособности сервера"""
    xml_dir = Path(__file__).parent.parent / "data" / "xml_data"
    xml_count = len(list(xml_dir.glob("*.xml"))) if xml_dir.exists() else 0

    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "xml_count": xml_count,
        "notes_count": len(notes_storage),
        "analytics_available": ANALYTICS_AVAILABLE,
    })


# ===========================================================================
#  ЗАПУСК СЕРВЕРА
# ===========================================================================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("WBS Viewer + EVM + Analytics — Веб-сервер")
    print("=" * 60)

    xml_dir = Path(__file__).parent.parent / "data" / "xml_data"
    snap_dir = Path(__file__).parent.parent / "data" / "xml_snapshots"
    print(f"Папка с XML:        {xml_dir}")
    print(f"Папка снапшотов:    {snap_dir}")
    print(f"Файл заметок:       {notes_file}")
    print(f"Аналитика доступна: {ANALYTICS_AVAILABLE}")

    if xml_dir.exists():
        xml_files = list(xml_dir.glob("*.xml"))
        print(f"Найдено XML файлов: {len(xml_files)}")
    else:
        print(f"ВНИМАНИЕ: Папка {xml_dir} не найдена!")

    if snap_dir.exists():
        snap_folders = [f for f in snap_dir.iterdir() if f.is_dir()]
        print(f"Папок снапшотов: {len(snap_folders)}")
        for sf in snap_folders:
            cnt = len(list(sf.glob("*.xml")))
            print(f"  • {sf.name}: {cnt} XML")
    else:
        print("Папка xml_snapshots/ не найдена, будет создана.")

    print("\nСервер запускается...")
    print("Откройте в браузере:")
    print("  WBS Viewer:  http://127.0.0.1:5000")
    print("  Аналитика:   http://127.0.0.1:5000/analytics")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)