# Static Chat no-AI content map — Cloud Run
# Large JSON is served from GCS (api_exposed); this image is HTML/JS/CSS only.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY serve.py ./
COPY index.html ./www/
COPY static ./www/static/
# Tiny placeholder so /data/ exists; real index loads from GCS.
RUN mkdir -p ./www/data && printf '%s\n' '{"schema_version":"placeholder","note":"Load from GCS api_exposed"}' > ./www/data/README.json

EXPOSE 8080

CMD ["python", "serve.py"]
