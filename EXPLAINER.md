# Inventory Availability Prediction Agent — Complete Explainer

Everything you need to understand, run, and extend this project.

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Tech Stack — Why Each Tool](#2-tech-stack--why-each-tool)
3. [Architecture Deep Dive](#3-architecture-deep-dive)
4. [File-by-File Walkthrough](#4-file-by-file-walkthrough)
5. [Database Schema](#5-database-schema)
6. [Agent Logic Explained](#6-agent-logic-explained)
7. [API Endpoints Reference](#7-api-endpoints-reference)
8. [Redis Caching Strategy](#8-redis-caching-strategy)
9. [Cost Tracking & Evaluation Framework](#9-cost-tracking--evaluation-framework)
10. [Setup & Running](#10-setup--running)
11. [Request Lifecycle (End-to-End Flow)](#11-request-lifecycle-end-to-end-flow)
12. [Demo Data](#12-demo-data)
13. [Common Questions](#13-common-questions)

---

## 1. What This Project Does

This is an **autonomous inventory management backend**. Given a product ID, it:

1. Fetches the product's last 30 days of sales from PostgreSQL
2. Sends that data to **3 AI sub-agents** running in parallel (all powered by Claude)
3. Each agent analyzes a different aspect of the inventory situation
4. A root **orchestrator** combines all three results into one final decision
5. That decision tells you: *Should we restock? How much? How urgently? Why?*
6. The result is cached in Redis for 5 minutes so repeat calls are instant
7. Every run is saved to the database with cost, latency, and agent reasoning

The system also tracks its own performance — every prediction logs how accurate it was, how long it took, and how much it cost in Claude API fees.

---

## 2. Tech Stack — Why Each Tool

| Tool | Role | Why this choice |
|---|---|---|
| **FastAPI** | HTTP API framework | Async-native, automatic OpenAPI docs, fast |
| **Anthropic SDK** | Claude API calls | Direct SDK gives full control over tokens/cost |
| **LangChain** | Agent orchestration layer | Provides the agent abstraction scaffolding |
| **PostgreSQL** | Primary database | Reliable, UUID support, excellent with SQLAlchemy |
| **asyncpg** | Postgres async driver | Non-blocking DB calls — won't stall the event loop |
| **Redis** | Response cache | Sub-millisecond reads, TTL support built-in |
| **SQLAlchemy (async)** | ORM | Type-safe DB models, works with asyncpg |
| **Pydantic v2** | Data validation | Fast, strict validation on all inputs and outputs |
| **Alembic** | DB migrations | Version-controlled schema changes |
| **Docker Compose** | Local environment | Single command spins up app + postgres + redis |

**Why Anthropic SDK directly instead of LangChain's Claude wrapper?**
Using the SDK directly gives you exact token counts, which is required for accurate cost tracking. LangChain's wrapper abstracts this away.

---

## 3. Architecture Deep Dive

```
HTTP Request
     │
     ▼
FastAPI (app/main.py)
     │
     ▼
predictions router (app/api/predictions.py)
     │
     ├── Check Redis cache ──► Cache HIT → return immediately (<10ms)
     │
     └── Cache MISS
              │
              ▼
         OrchestratorAgent (app/agents/orchestrator.py)
              │
              ├──── asyncio.gather() ────────────────────────┐
              │                                              │
              ▼                                              ▼
   DemandForecastingAgent                    CatalogValidationAgent
   (app/agents/demand_forecasting.py)        (app/agents/catalog_validation.py)
              │                                              │
              └──────────── both complete ──────────────────┘
                                   │
                                   ▼
                        AnomalyDetectionAgent
                        (app/agents/anomaly_detection.py)
                        [needs demand result as input]
                                   │
                                   ▼
                        Orchestrator aggregates
                        → builds InventoryDecision
                        → saves to PostgreSQL
                        → saves cost to agent_evaluations
                        → stores in Redis cache
                                   │
                                   ▼
                          JSON response to client
```

**Key design decision:** Demand and Catalog agents run in parallel (they only need product data). Anomaly detection runs after demand is done because it needs the predicted demand number as an input.

---

## 4. File-by-File Walkthrough

### `app/config.py`
Loads all environment variables using `pydantic-settings`. Every other file imports `settings` from here. No `.env` values are hardcoded anywhere else.

```python
settings.anthropic_api_key   # your Claude API key
settings.database_url        # asyncpg connection string
settings.redis_url           # redis connection string
settings.claude_model        # claude-3-5-haiku-20241022
settings.cache_ttl           # 300 seconds (5 minutes)
```

---

### `app/models/database.py`
SQLAlchemy ORM definitions for all 4 tables. Uses the modern SQLAlchemy 2.0 `Mapped` + `mapped_column` style with full Python type annotations.

| Class | Table |
|---|---|
| `Product` | `products` |
| `SalesHistory` | `sales_history` |
| `Prediction` | `predictions` |
| `AgentEvaluation` | `agent_evaluations` |

Relationships are defined so you can do `product.predictions` or `prediction.evaluation` in Python without writing SQL.

---

### `app/models/schemas.py`
Pydantic v2 schemas — separate from the ORM models. These are what FastAPI uses to validate incoming request bodies and serialize outgoing responses.

Key schemas:

| Schema | Used for |
|---|---|
| `ProductCreate` | POST /products request body |
| `ProductOut` | GET /products response |
| `DemandForecastResult` | Output of the demand agent |
| `AnomalyDetectionResult` | Output of the anomaly agent |
| `CatalogValidationResult` | Output of the catalog agent |
| `InventoryDecision` | Final orchestrator output (returned by POST /predict) |
| `BatchPredictRequest` | POST /predict/batch request body |
| `EvaluationSummary` | GET /evaluations/summary response |

---

### `app/services/db.py`
Creates the async SQLAlchemy engine and session factory. The `get_db()` function is a FastAPI dependency — every endpoint that needs the database injects it via `Depends(get_db)`.

```python
async def my_endpoint(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
```

---

### `app/services/cache.py`
A thin async wrapper around `redis.asyncio`. Three functions:

- `cache_get(key)` — returns a dict or None
- `cache_set(key, value, ttl)` — serializes to JSON, stores with TTL
- `ping_redis()` — used by the health check endpoint

The Redis client is a module-level singleton — it connects once and reuses the connection.

---

### `app/agents/demand_forecasting.py`
**What it does:** Asks Claude to analyze 30 days of sales data and predict the next 7 days of demand.

**Input to Claude:**
- Product name and category
- 30 days of daily sales (date + units_sold)
- Current stock level and reorder point

**Output from Claude (JSON):**
```json
{
  "predicted_demand_next_7_days": 126,
  "confidence_score": 0.87,
  "trend_direction": "up",
  "reasoning": "Sales have increased 15% week-over-week..."
}
```

**System prompt enforces:** JSON-only output, no markdown fences.

---

### `app/agents/anomaly_detection.py`
**What it does:** Given the actual demand forecast, detects if anything is wrong with the inventory situation.

**Input to Claude:**
- Current stock
- Predicted 7-day demand
- Reorder point, lead time, average daily sales

**Output from Claude (JSON):**
```json
{
  "anomaly_type": "stockout_risk",
  "severity": "high",
  "recommended_action": "Place an emergency order immediately."
}
```

**Anomaly types:**
- `stockout_risk` — stock will run out before replenishment arrives
- `overstock_risk` — stock far exceeds what will be sold (waste/cost risk)
- `unusual_depletion` — demand is spiking vs. historical average
- `none` — all healthy

---

### `app/agents/catalog_validation.py`
**What it does:** Validates product metadata for completeness and business-logic correctness.

**Checks Claude makes:**
- Are any fields missing or zero?
- Is the lead time unusually long (>30 days)?
- Is the reorder point set to 0 (meaning no automatic reorder will trigger)?
- Does the current stock make sense for the category?

**Output from Claude (JSON):**
```json
{
  "catalog_health_score": 0.75,
  "missing_fields": [],
  "validation_warnings": ["Lead time of 35 days is unusually high for dairy products"]
}
```

---

### `app/agents/orchestrator.py`
The brain of the system. Steps:

1. Check Redis cache — return immediately if found
2. Load product + 30-day sales from PostgreSQL
3. `asyncio.gather()` demand + catalog agents in parallel
4. Run anomaly agent with real demand number
5. Calculate restock quantity using the formula:
   ```
   restock = predicted_demand_7d + (daily_avg × lead_time_days) + safety_buffer
   safety_buffer = predicted_demand_7d × 0.5
   ```
6. Determine priority level (low / medium / high / critical) based on:
   - Days of stock remaining
   - Anomaly severity
   - Whether stock is below reorder point
7. Build `InventoryDecision`
8. Save `Prediction` row + `AgentEvaluation` row (with cost) to DB
9. Cache result in Redis for 5 minutes
10. Return decision

---

### `app/api/products.py`
Three endpoints: list all products, create a product, get one product by ID. Standard CRUD with SQLAlchemy async queries.

---

### `app/api/predictions.py`
- `POST /predict/{product_id}` — calls the orchestrator for one product
- `POST /predict/batch` — calls `run_orchestrator_batch()` which uses `asyncio.gather` to run up to 20 products in parallel. Failed individual predictions don't crash the whole batch.
- `GET /predictions/history/{product_id}` — last 30 prediction records

---

### `app/api/evaluations.py`
- `GET /evaluations/summary` — aggregates accuracy, latency, cost, hallucination rate across all predictions using SQL `AVG()` and `SUM()`
- `POST /evaluations/{prediction_id}/feedback` — lets a human rate a prediction (accuracy 0–1, was there a hallucination, free-text notes). Upserts into `agent_evaluations`.

---

### `app/main.py`
Creates the FastAPI app, registers all three routers, and defines the `/health` endpoint which pings both PostgreSQL and Redis.

---

### `alembic/`
Database migration setup.

- `alembic.ini` — Alembic config; database URL is overridden at runtime from the env var
- `alembic/env.py` — migration runner; strips `+asyncpg` from the URL for sync Alembic use
- `alembic/versions/001_initial_schema.py` — creates all 4 tables with indexes

---

### `scripts/seed_demo_data.py`
Creates a realistic test dataset:
- 10 products across dairy, beverages, snacks
- 30 days of sales history per product
- Realistic variance using `random.gauss(avg, variance)`
- Two low-stock products with an upward sales trend (Whole Milk 1L at 8 units, Orange Juice 1L at 12 units) — these will immediately trigger `critical` restock recommendations

---

### `docker-compose.yml`
Defines three containers:

| Service | Image | Port |
|---|---|---|
| `app` | Built from Dockerfile | 8000 |
| `postgres` | postgres:16-alpine | 5432 |
| `redis` | redis:7-alpine | 6379 |

The app container waits for both postgres and redis health checks before starting. All data is persisted in named Docker volumes (`postgres_data`, `redis_data`).

---

### `Dockerfile`
- Base: `python:3.11-slim`
- Installs `gcc` and `libpq-dev` (required to compile asyncpg/psycopg2)
- Copies and installs `requirements.txt`
- Runs uvicorn with `--reload` (hot-reload on code changes when volume is mounted)

---

## 5. Database Schema

```
products
├── id              UUID (primary key, auto-generated)
├── name            VARCHAR(255)
├── category        VARCHAR(100)  e.g. "dairy", "beverages", "snacks"
├── supplier_id     UUID
├── lead_time_days  INT           days from order to delivery
├── reorder_point   INT           minimum stock before reorder triggers
├── current_stock   INT
└── created_at      TIMESTAMP WITH TIME ZONE

sales_history
├── id              UUID (primary key)
├── product_id      UUID → products.id (CASCADE DELETE)
├── units_sold      INT
├── sale_date       DATE
└── created_at      TIMESTAMP WITH TIME ZONE

predictions
├── id              UUID (primary key)
├── product_id      UUID → products.id (CASCADE DELETE)
├── predicted_demand_7d   INT
├── confidence_score      FLOAT  (0.0 to 1.0)
├── restock_recommended   BOOLEAN
├── restock_quantity      INT
├── priority_level        VARCHAR(20)  low/medium/high/critical
├── agent_reasoning       TEXT         full natural language explanation
├── latency_ms            INT          total pipeline time
└── created_at      TIMESTAMP WITH TIME ZONE

agent_evaluations
├── id              UUID (primary key)
├── prediction_id   UUID → predictions.id (CASCADE DELETE)
├── accuracy_score  FLOAT (nullable — filled in via human feedback)
├── hallucination_flag  BOOLEAN
├── cost_usd        FLOAT  automatically calculated from token counts
├── feedback        TEXT (nullable — filled in via human feedback)
└── created_at      TIMESTAMP WITH TIME ZONE
```

**Indexes created:**
- `sales_history.product_id` — fast lookup of a product's sales
- `sales_history.sale_date` — fast range queries
- `predictions.product_id` — fast history lookup
- `predictions.created_at` — fast recent-first ordering
- `agent_evaluations.prediction_id` — fast join

---

## 6. Agent Logic Explained

### How Claude is called

Every agent follows the same pattern:

```python
response = await client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    system="You are a specialist. Return only JSON.",
    messages=[{"role": "user", "content": <formatted prompt>}]
)
raw_json = response.content[0].text.strip()
data = json.loads(raw_json)
```

The system prompt for every agent enforces **JSON-only output** with no markdown code fences. This makes parsing reliable.

### Why claude-3-5-haiku?

- Fastest Claude model available
- Cheapest — keeps per-prediction cost under $0.001
- Still highly capable for structured JSON extraction tasks
- Suitable for production volume at low cost

### Cost calculation

```python
cost = (input_tokens × $0.00000025) + (output_tokens × $0.00000125)
```

These are the actual Haiku pricing rates. The token counts come directly from `response.usage.input_tokens` and `response.usage.output_tokens` in the API response.

### Restock quantity formula

```
daily_demand = predicted_demand_7d ÷ 7
lead_time_demand = daily_demand × lead_time_days
safety_buffer = predicted_demand_7d × 0.5
needed = predicted_demand_7d + lead_time_demand + safety_buffer - current_stock
restock_quantity = max(needed, reorder_point)
```

This ensures you order enough to cover:
- The next 7 days of demand
- Demand during the lead time (while waiting for delivery)
- A 50% safety buffer for unexpected spikes

### Priority level logic

| Condition | Priority |
|---|---|
| Not restocking | `low` |
| Anomaly severity is high OR days of stock ≤ 2 | `critical` |
| Anomaly severity is medium OR days of stock ≤ 5 | `high` |
| Stock ≤ reorder point | `medium` |
| Everything else | `low` |

---

## 7. API Endpoints Reference

### `GET /health`
No auth required. Returns system status.
```json
{"status": "ok", "db_connected": true, "redis_connected": true, "agent_status": "ready"}
```

---

### `GET /products`
Returns all products with current stock levels.

---

### `POST /products`
Create a new product.
```json
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

### `POST /predict/{product_id}`
Run the full 3-agent pipeline. First call hits Claude (~1–3 seconds). Second call within 5 minutes hits Redis (<10ms).

Returns `InventoryDecision`:
```json
{
  "product_id": "...",
  "restock_recommended": true,
  "restock_quantity": 185,
  "priority_level": "critical",
  "reasoning": "Demand forecast: 126 units over next 7 days (confidence: 87%, trend: up)...",
  "demand_forecast": {
    "predicted_demand_next_7_days": 126,
    "confidence_score": 0.87,
    "trend_direction": "up",
    "reasoning": "Sales have increased 22% over the past two weeks..."
  },
  "anomaly_detection": {
    "anomaly_type": "stockout_risk",
    "severity": "high",
    "recommended_action": "Place emergency restock order immediately."
  },
  "catalog_validation": {
    "catalog_health_score": 0.95,
    "missing_fields": [],
    "validation_warnings": []
  },
  "latency_ms": 1423,
  "cost_usd": 0.00038
}
```

---

### `POST /predict/batch`
Run predictions for up to 20 products in parallel.
```json
{ "product_ids": ["uuid1", "uuid2", "uuid3"] }
```
Returns `{"results": [...], "total": 3, "failed": 0}`. Partial failures are captured — one failed product won't crash the others.

---

### `GET /predictions/history/{product_id}`
Last 30 prediction records for a product.

---

### `GET /evaluations/summary`
Aggregated performance dashboard across all predictions:
```json
{
  "avg_accuracy_score": 0.88,
  "avg_latency_ms": 1350.4,
  "avg_cost_usd": 0.00041,
  "hallucination_count": 0,
  "hallucination_rate": 0.0,
  "total_predictions": 12,
  "total_evaluations": 12
}
```

---

### `POST /evaluations/{prediction_id}/feedback`
Submit human feedback on a specific prediction.
```json
{
  "accuracy_score": 0.92,
  "hallucination_flag": false,
  "feedback": "Restock quantity was accurate. Demand spike was correctly identified."
}
```

---

## 8. Redis Caching Strategy

**Cache key format:** `prediction:{product_id}`

**TTL:** 300 seconds (5 minutes)

**What gets cached:** The full `InventoryDecision` object, serialized to JSON.

**Cache invalidation:** TTL-based only. The cache expires naturally after 5 minutes. There is no manual invalidation — if you need a fresh prediction before 5 minutes, the simplest approach is to call the endpoint after the TTL expires.

**Why 5 minutes?** Inventory levels and sales patterns don't change second-by-second. A 5-minute cache eliminates redundant Claude API calls (and costs) for repeated requests while keeping the data fresh enough for operational decisions.

**Latency impact:**
- Cache MISS (first call): 1,000–3,000ms (3 Claude API calls, 2 parallel)
- Cache HIT (repeat call within 5 min): < 10ms

---

## 9. Cost Tracking & Evaluation Framework

Every single prediction run automatically records:

| Field | Where | How |
|---|---|---|
| `latency_ms` | `predictions` table | `time.monotonic()` before/after agent pipeline |
| `cost_usd` | `agent_evaluations` table | `(input_tokens × 0.00000025) + (output_tokens × 0.00000125)` |
| `hallucination_flag` | `agent_evaluations` table | Defaults `false`; set by human feedback |
| `accuracy_score` | `agent_evaluations` table | Set by human feedback (0.0–1.0) |

**Human feedback loop:**
1. Run a prediction: `POST /predict/{id}`
2. The system acts on the recommendation
3. Later, you observe what actually happened (did stock run out? was the restock quantity right?)
4. Submit feedback: `POST /evaluations/{prediction_id}/feedback`
5. Check the dashboard: `GET /evaluations/summary`

Over time this gives you:
- **avg_accuracy_score** — is the AI actually correct?
- **hallucination_rate** — is the AI making up data?
- **avg_cost_usd** — what is each prediction costing?
- **avg_latency_ms** — is the system fast enough?

This is a simplified version of how production LLM systems are monitored.

---

## 10. Setup & Running

### Prerequisites
- Docker Desktop installed and running
- An Anthropic API key (get one at console.anthropic.com)

### Step 1 — Configure environment
```bash
cd inventory-prediction-agent
cp .env.example .env
```
Open `.env` and replace `sk-ant-your-key-here` with your real key.

### Step 2 — Start all containers
```bash
docker-compose up --build -d
```
This builds the Python image, starts PostgreSQL and Redis, and waits for health checks before starting the app. First build takes ~2 minutes (downloading images + installing packages).

### Step 3 — Run database migrations
```bash
docker-compose exec app alembic upgrade head
```
Creates all 4 tables in PostgreSQL.

### Step 4 — Seed demo data
```bash
docker-compose exec app python -m scripts.seed_demo_data
```
Output shows all 10 products and flags the two with low stock.

### Step 5 — Verify everything works
```bash
curl http://localhost:8000/health
```
Should return `"status": "ok"` with both `db_connected` and `redis_connected` true.

### Step 6 — Run your first prediction
```bash
# Get product IDs
curl http://localhost:8000/products | python -m json.tool

# Pick a UUID from the output and run:
curl -X POST http://localhost:8000/predict/<product_id>
```

### Useful commands

```bash
# View app logs
docker-compose logs -f app

# Stop everything
docker-compose down

# Stop and delete all data (fresh start)
docker-compose down -v

# Open interactive docs in browser
open http://localhost:8000/docs
```

### Running without Docker (local dev)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Make sure PostgreSQL and Redis are running locally, then:
alembic upgrade head
python -m scripts.seed_demo_data
uvicorn app.main:app --reload
```

---

## 11. Request Lifecycle (End-to-End Flow)

Here is exactly what happens when you call `POST /predict/abc-123`:

```
1. FastAPI receives request at /predict/abc-123
   └── predictions router calls run_orchestrator(product_id, db)

2. Orchestrator checks Redis
   └── cache_get("prediction:abc-123")
   └── If HIT → return immediately (skip all steps below)

3. Orchestrator queries PostgreSQL
   └── SELECT * FROM products WHERE id = 'abc-123'
   └── SELECT * FROM sales_history WHERE product_id = 'abc-123'
      ORDER BY sale_date DESC LIMIT 30

4. asyncio.gather() fires TWO Claude calls in parallel:
   ┌── DemandForecastingAgent
   │   └── Sends 30-day sales data to claude-3-5-haiku
   │   └── Gets back: predicted_demand=126, confidence=0.87, trend="up"
   │   └── Returns result + token counts
   │
   └── CatalogValidationAgent
       └── Sends product metadata to claude-3-5-haiku
       └── Gets back: health_score=0.95, no warnings
       └── Returns result + token counts

5. AnomalyDetectionAgent runs (uses demand result from step 4)
   └── Sends: stock=8, demand=126, reorder_point=50, lead_time=3 days
   └── Gets back: anomaly_type="stockout_risk", severity="high"
   └── Returns result + token counts

6. Orchestrator calculates:
   └── restock_recommended = true (stock 8 < reorder_point 50)
   └── restock_quantity = 126 + (126/7 × 3) + 63 - 8 = 235 units
   └── priority_level = "critical" (severity=high AND days_of_stock≈0.4)
   └── reasoning = combined natural language from all 3 agents

7. Orchestrator saves to PostgreSQL:
   └── INSERT INTO predictions (product_id, predicted_demand_7d=126, ...)
   └── INSERT INTO agent_evaluations (prediction_id, cost_usd=0.00038, ...)

8. Orchestrator caches result:
   └── cache_set("prediction:abc-123", decision, ttl=300)

9. Response returned as JSON InventoryDecision
   └── Total time: ~1,400ms
```

---

## 12. Demo Data

The seed script creates exactly 10 products:

| # | Product | Category | Stock | Reorder Point | Status |
|---|---|---|---|---|---|
| 1 | Whole Milk 1L | dairy | 8 | 50 | CRITICAL LOW |
| 2 | Greek Yogurt 500g | dairy | 120 | 30 | OK |
| 3 | Cheddar Cheese 200g | dairy | 95 | 40 | OK |
| 4 | Orange Juice 1L | beverages | 12 | 60 | CRITICAL LOW |
| 5 | Sparkling Water 500ml | beverages | 340 | 80 | OK |
| 6 | Energy Drink 250ml | beverages | 200 | 50 | OK |
| 7 | Green Tea 330ml | beverages | 175 | 40 | OK |
| 8 | Potato Chips 150g | snacks | 280 | 70 | OK |
| 9 | Granola Bar 40g | snacks | 190 | 50 | OK |
| 10 | Dark Chocolate 100g | snacks | 85 | 30 | OK |

Products 1 and 4 have an **upward sales trend** built into their generated history (3% daily increase) — this makes the demand forecast more interesting and realistic.

---

## 13. Common Questions

**Q: Why does the first prediction take 1–3 seconds?**
Three Claude API calls are being made (two in parallel, one sequential). Network latency to Anthropic's API + model inference time accounts for this. The cache makes all subsequent calls within 5 minutes instant.

**Q: What happens if Claude returns invalid JSON?**
`json.loads()` will raise a `JSONDecodeError`. This propagates as a 500 error. In production you would add a retry loop with a more explicit prompt. The Claude Haiku model is very reliable at producing valid JSON with the current prompts.

**Q: Can I use a different Claude model?**
Yes. Change `claude_model` in `.env` (or `app/config.py`). `claude-3-5-sonnet-20241022` gives higher quality predictions at ~10x higher cost. `claude-3-haiku-20240307` is slightly cheaper but older.

**Q: How do I add a new product via API instead of the seed script?**
```bash
curl -X POST http://localhost:8000/products \
  -H "Content-Type: application/json" \
  -d '{"name":"...","category":"snacks","supplier_id":"11111111-1111-1111-1111-111111111111","lead_time_days":5,"reorder_point":30,"current_stock":100}'
```
Then add sales history records directly to the `sales_history` table, or extend the API with a `POST /sales` endpoint.

**Q: How accurate is the demand forecasting?**
It depends on the quality and volume of historical data. With only 30 days of history, it will identify obvious trends but won't detect annual seasonality. Use `POST /evaluations/{id}/feedback` to score predictions after you observe real outcomes — this tells you how well the model is performing on your specific data.

**Q: What does "hallucination" mean here?**
In this context, a hallucination means the agent returned a number or recommendation that is logically inconsistent with the input data — for example, predicting 5 units demand when all 30 days averaged 50 units/day with no downward trend. You flag these manually via the feedback endpoint.

**Q: How do I scale this to handle more products?**
The batch endpoint handles up to 20 products per call with full parallelism. For more, you would add a task queue (Celery + Redis) so predictions run as background jobs rather than blocking HTTP requests.
