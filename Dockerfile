FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python3 -m playwright install chromium && \
    python3 -m playwright install-deps chromium

COPY backend/ backend/
COPY frontend/ frontend/
COPY scoring_weights.yaml .

ENV PYTHONPATH=/app/backend

EXPOSE 8000 8501

# Start FastAPI + Streamlit via supervisord or just default to API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
