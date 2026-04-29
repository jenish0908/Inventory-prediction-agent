# Inventory Availability Prediction Agent

A production-ready multi-agent AI system that autonomously predicts product availability and generates restocking recommendations — built with FastAPI, Groq (Llama 3), PostgreSQL, and Redis.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Groq](https://img.shields.io/badge/AI-Groq%20Llama%203-orange)
![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2016-blue)
![Redis](https://img.shields.io/badge/Cache-Redis%207-red)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)

---

## What It Does

Given a product ID, the system:

1. Fetches the last 30 days of sales history from PostgreSQL
2. Runs **3 AI sub-agents in parallel** using Groq (Llama 3.1 8B)
3. Combines all outputs into a single inventory decision
4. Caches the result in Redis for 5 minutes
5. Persists every prediction with latency, cost, and reasoning to the database

Every prediction answers: **Should we restock? How much? How urgently? Why?**

---

## Architecture

```
POST /predict/{product_id}
         │
         ├── Redis Cache HIT? ──► Return instantly (<10ms)
         │
         └── Cache MISS
                  │
                  ▼
         OrchestratorAgent
                  │
         asyncio.gather()
         ┌────────┴────────┐
         ▼                 ▼
  DemandForecast     CatalogValidation
     Agent               Agent
         │                 │
         └────────┬────────┘
                  ▼
          AnomalyDetection
              Agent
                  │
                  ▼
          InventoryDecision
          (saved to DB + cached)
```

### The 3 Sub-Agents

| Agent | Input | Output |
|---|---|---|
| **DemandForecastingAgent** | 30-day sales history | `predicted_demand_7d`, `confidence_score`, `trend_direction` |
| **AnomalyDetectionAgent** | Stock level + predicted demand | `anomaly_type`, `severity`, `recommended_action` |
| **CatalogValidationAgent** | Product metadata | `catalog_health_score`, `missing_fields`, `warnings` |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI (async) |
| AI | Groq API — `llama-3.1-8b-instant` (free tier) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| Cache | Redis 7 (5-min TTL per product) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Containerization | Docker + Docker Compose |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A free [Groq API key](https://console.groq.com) (no credit card required)

---

## Getting Your Free Groq API Key

> Takes less than 2 minutes. No credit card needed.

1. Go to **[https://console.groq.com](https://console.groq.com)**
2. Sign up with email or Google account
3. Click **"API Keys"** in the left sidebar
4. Click **"Create API Key"**, give it a name, click **"Submit"**
5. Copy the key — it starts with `gsk_...`

Free tier limits: **30 requests/min · 14,400 requests/day**

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-username/inventory-prediction-agent.git
cd inventory-prediction-agent
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set your Groq API key:

```env
GROQ_API_KEY=gsk_your_key_here
```

### 3. Start all services

```bash
docker-compose up --build -d
```

This starts the FastAPI app, PostgreSQL, and Redis. First build takes ~2 minutes.

### 4. Run database migrations

```bash
docker-compose exec app alembic upgrade head
```

### 5. Seed demo data

```bash
docker-compose exec app python -m scripts.seed_demo_data
```

Creates 10 products across 3 categories with 30 days of sales history. Two products have critically low stock to immediately trigger restock recommendations.

### 6. Verify everything is running

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "db_connected": true,
  "redis_connected": true,
  "agent_status": "ready"
}
```

**Interactive API docs:** http://localhost:8000/docs

---

## API Reference

### Health Check

```http
GET /health
```

```json
{
  "status": "ok",
  "db_connected": true,
  "redis_connected": true,
  "agent_status": "ready"
}
```

---

### List Products

```http
GET /products
```

---

### Create Product

```http
POST /products
Content-Type: application/json

{
  "name": "Butter 250g",
  "category": "dairy",
  "supplier_id": "11111111-1111-1111-1111-111111111111",
  "lead_time_days": 3,
  "reorder_point": 40,
  "current_stock": 15
}
```

---

### Run Prediction

```http
POST /predict/{product_id}
```

**Example response:**

```json
{
  "product_id": "41081583-b4ae-4514-a715-707f8b53909c",
  "restock_recommended": true,
  "restock_quantity": 50,
  "priority_level": "critical",
  "reasoning": "Demand forecast: 24 units over next 7 days (confidence: 73%, trend: stable). Anomaly: stockout_risk at high severity. Catalog health: 70%...",
  "demand_forecast": {
    "predicted_demand_next_7_days": 24,
    "confidence_score": 0.73,
    "trend_direction": "stable",
    "reasoning": "Sales show stable demand with slight daily fluctuation..."
  },
  "anomaly_detection": {
    "anomaly_type": "stockout_risk",
    "severity": "high",
    "recommended_action": "Reorder 42 units immediately. Lead time is 3 days."
  },
  "catalog_validation": {
    "catalog_health_score": 0.95,
    "missing_fields": [],
    "validation_warnings": []
  },
  "latency_ms": 612,
  "cost_usd": 0.0
}
```

> Second call within 5 minutes is served from Redis cache (<10ms).

---

### Batch Prediction

```http
POST /predict/batch
Content-Type: application/json

{
  "product_ids": [
    "uuid-1",
    "uuid-2",
    "uuid-3"
  ]
}
```

Runs up to 20 predictions in parallel. Failed individual products don't affect the rest.

---

### Prediction History

```http
GET /predictions/history/{product_id}
```

Returns last 30 predictions for a product.

---

### Evaluation Dashboard

```http
GET /evaluations/summary
```

```json
{
  "avg_accuracy_score": 0.91,
  "avg_latency_ms": 612.4,
  "avg_cost_usd": 0.0,
  "hallucination_count": 0,
  "hallucination_rate": 0.0,
  "total_predictions": 24,
  "total_evaluations": 24
}
```

---

### Submit Human Feedback

```http
POST /evaluations/{prediction_id}/feedback
Content-Type: application/json

{
  "accuracy_score": 0.92,
  "hallucination_flag": false,
  "feedback": "Restock quantity was accurate. Demand trend correctly identified."
}
```

---

## Project Structure

```
inventory-prediction-agent/
├── app/
│   ├── main.py                  # FastAPI app, router registration, /health
│   ├── config.py                # Environment config via pydantic-settings
│   ├── agents/
│   │   ├── orchestrator.py      # Root agent — parallel execution + DB persistence
│   │   ├── demand_forecasting.py
│   │   ├── anomaly_detection.py
│   │   └── catalog_validation.py
│   ├── api/
│   │   ├── products.py          # GET/POST /products
│   │   ├── predictions.py       # POST /predict, /predict/batch, GET /history
│   │   └── evaluations.py       # GET /summary, POST /feedback
│   ├── models/
│   │   ├── database.py          # SQLAlchemy ORM models
│   │   └── schemas.py           # Pydantic v2 schemas
│   └── services/
│       ├── db.py                # Async SQLAlchemy session
│       ├── cache.py             # Redis get/set helpers
│       └── gemini.py            # Groq client (shared across agents)
├── alembic/                     # Database migrations
│   └── versions/
│       └── 001_initial_schema.py
├── scripts/
│   ├── seed_demo_data.py        # Seeds 10 products + 30 days sales history
│   └── list_models.py           # Diagnostic: lists available AI models
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

---

## Database Schema

```
products          → stores product catalog
sales_history     → daily units sold per product (30-day window used for forecasting)
predictions       → every agent pipeline run with reasoning + latency
agent_evaluations → cost tracking + human feedback for self-improvement loop
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key from console.groq.com |
| `DATABASE_URL` | No | Defaults to local PostgreSQL in Docker |
| `REDIS_URL` | No | Defaults to local Redis in Docker |
| `APP_ENV` | No | `development` or `production` |
| `GROQ_MODEL` | No | Defaults to `llama-3.1-8b-instant` |

---

## Useful Commands

```bash
# View live app logs
docker-compose logs -f app

# Restart app after code changes
docker-compose restart app

# Open a shell inside the app container
docker-compose exec app bash

# Stop all services
docker-compose down

# Stop and delete all data (full reset)
docker-compose down -v
```

---

## How the Evaluation Framework Works

Every prediction automatically records:
- **`latency_ms`** — total time for all 3 agent calls
- **`cost_usd`** — always `0.0` on Groq free tier
- **`hallucination_flag`** — set via human feedback

Submit feedback after observing real-world outcomes:
```bash
curl -X POST http://localhost:8000/evaluations/<prediction_id>/feedback \
  -H "Content-Type: application/json" \
  -d '{"accuracy_score": 0.9, "hallucination_flag": false, "feedback": "Spot on."}'
```

Monitor over time via `GET /evaluations/summary` to track accuracy trends, catch hallucinations, and measure system performance.

---

## License

MIT
