FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаём папки для данных и логов
RUN mkdir -p data/xml_data logs

EXPOSE 5000

CMD ["python", "run.py"]
