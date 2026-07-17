# Stage 1: Build frontend
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python application
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web
COPY scheduler ./scheduler
COPY alembic ./alembic
COPY alembic.ini .
COPY run.py .
COPY config.example.toml ./config.example.toml

# Copy frontend build from Stage 1
COPY --from=frontend-builder /build/dist ./frontend/dist

EXPOSE 8000

# Web + scheduler mode (default)
CMD ["python", "run.py", "--config", "/app/config.toml"]
