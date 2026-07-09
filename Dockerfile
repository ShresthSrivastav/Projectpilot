# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
RUN mkdir -p /app/chroma_data /app/generated_projects /app/memory_store && \
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
    find . -type f -name '*.pyc' -delete
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 5000 8501
