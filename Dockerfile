FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DINKYDASH_CONFIG=/data/config.yaml

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py generate.py ./
COPY dinkydash/ ./dinkydash/
COPY web/ ./web/
COPY web/static/ ./web/static/

EXPOSE 5000

CMD ["python", "app.py"]
