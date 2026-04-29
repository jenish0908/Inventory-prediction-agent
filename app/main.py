from fastapi import FastAPI
from sqlalchemy import text

from app.api.products import router as products_router
from app.api.predictions import router as predictions_router
from app.api.evaluations import router as evaluations_router
from app.models.schemas import HealthResponse
from app.services.db import AsyncSessionLocal
from app.services.cache import ping_redis

app = FastAPI(
    title="Inventory Availability Prediction Agent",
    version="1.0.0",
    description="Multi-agent agentic system for inventory prediction and restocking recommendations",
)

app.include_router(products_router)
app.include_router(predictions_router)
app.include_router(evaluations_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    redis_ok = await ping_redis()

    return HealthResponse(
        status="ok" if (db_ok and redis_ok) else "degraded",
        db_connected=db_ok,
        redis_connected=redis_ok,
        agent_status="ready",
    )
