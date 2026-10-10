FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 HOST=0.0.0.0
WORKDIR /app
COPY serve.py ./
COPY index.html ./www/
COPY static ./www/static/
COPY lectures ./www/lectures/
COPY content ./www/content/
EXPOSE 8080
CMD ["python", "serve.py"]
