#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from pathlib import Path

# Добавляем корневую папку в путь поиска модулей
sys.path.insert(0, str(Path(__file__).parent))

from src.server import app

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 MS Project WBS Viewer")
    print("=" * 60)
    print("📊 WBS Viewer:  http://127.0.0.1:5000")
    print("📈 Аналитика:   http://127.0.0.1:5000/analytics")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
