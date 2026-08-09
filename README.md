# Payment Workflow API

A FastAPI starter for payment-workflow services, with environment-based configuration, CORS, health checks, and tests.

## Quick start

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive API documentation.

## Endpoints

- `GET /api/v1/health` — liveness check
- `GET /api/v1/health/ready` — readiness check

## Quality checks

```bash
ruff check .
pytest
```
