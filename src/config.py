import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv('WBS_DATA_DIR', BASE_DIR / 'data'))
XML_DIR = DATA_DIR / os.getenv('WBS_XML_DIR', 'xml_data')
SNAPSHOTS_DIR = DATA_DIR / os.getenv('WBS_SNAPSHOTS_DIR', 'xml_snapshots')
LOG_DIR = Path(os.getenv('WBS_LOG_DIR', BASE_DIR / 'logs'))
NOTES_FILE = DATA_DIR / 'notes.json'

# Создаём все необходимые папки
for d in [DATA_DIR, XML_DIR, SNAPSHOTS_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
