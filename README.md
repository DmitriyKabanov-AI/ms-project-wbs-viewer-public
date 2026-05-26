# MS Project WBS Viewer + EVM Analytics

Веб-приложение для просмотра WBS (структуры декомпозиции работ) проектов MS Project, расчёта метрик EVM (PV, EV, AC, CPI, SPI), анализа загрузки ресурсов и сравнения срезов «Было / Стало».  
Включает тесты (pytest) и полностью контейнеризировано (Docker).

## 🚀 Быстрый старт

### Локально (Python 3.11+)

```bash
pip install -r requirements.txt
python run.py
```

Откройте `http://localhost:5000`

### Docker

```bash
docker build -t wbs-viewer .
docker run -p 5000:5000 -v $(pwd)/data:/app/data wbs-viewer
```

## 📊 Возможности

- Древовидный просмотр WBS с фильтрацией, поиском, экспортом в Excel
- Метрики EVM (PV, EV, AC, CPI, SPI) с S-кривой
- Аналитика «Было / Стало» – сравнение двух срезов проектов
- Профиль загрузки ресурсов (понедельный), тепловая карта трудозатрат
- Заметки по задачам (сохраняются в JSON)
- Интерактивные графики на Chart.js

## 📂 Структура данных

- `data/xml_data/` – текущие XML-файлы проектов
- `data/xml_snapshots/` – папки с историческими срезами (например, `Было`, `Стало`)
- `logs/` – логи сервера
- `notes.json` – заметки по задачам

## 🧪 Тестирование

```bash
pytest tests/ -v
```

## 🛠 Технологии

- Flask, Jinja2
- Chart.js (фронтенд)
- wbs_parser – парсинг MS Project XML
- pandas, openpyxl (экспорт Excel)
- pytest

## 📄 Лицензия

MIT

## 👤 Автор

[Dmitriy Kabanov](https://github.com/DmitriyKabanov-AI)