FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better Docker layer caching
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Copy application source
COPY app ./app

EXPOSE 8000

CMD [
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000"
]