# Pathology Hub Chat MVP — Cloud Run (HTTPS via *.run.app)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py prompts.py pathology_backend.py openai_synthesizer.py \
     figure_quality_filter.py secrets_helper.py who_section_mentions.py \
     literature_apis.py iterative_topic_retrieval.py ./
COPY static ./static

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
