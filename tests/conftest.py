import sys
import os
from pathlib import Path
import pytest

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import XML_DIR, SNAPSHOTS_DIR, BASE_DIR

@pytest.fixture
def app():
    """Flask app for testing"""
    from src.server import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client