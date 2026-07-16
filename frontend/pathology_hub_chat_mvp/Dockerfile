# Pathology Hub Chat MVP — Cloud Run (HTTPS via *.run.app)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py prompts.py pathology_backend.py openai_synthesizer.py \
     figure_quality_filter.py secrets_helper.py who_section_mentions.py ./
COPY static ./static

# Do not ship local venv, caches, or prebuild outputs
EXPOSE 8080

CMD exec uvicorn app:app --host 0.0.0.0 --port "${PORT}" --workers 1
