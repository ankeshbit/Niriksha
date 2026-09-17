FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr libzbar0 libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD sh -c "python -m backend.schema_migration && \
    uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1"
