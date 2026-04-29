import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import Prediction
from app.models.schemas import (
    InventoryDecision,
    PredictionOut,
    BatchPredictRequest,
    BatchPredictResponse,
)
from app.agents.orchestrator import run_orchestrator, run_orchestrator_batch
from app.services.db import get_db

router = APIRouter(tags=["predictions"])


@router.post("/predict/{product_id}", response_model=InventoryDecision)
async def predict_single(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        return await run_orchestrator(product_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent pipeline failed: {e}")


@router.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch(body: BatchPredictRequest, db: AsyncSession = Depends(get_db)):
    if len(body.product_ids) > 20:
        raise HTTPException(status_code=400, detail="Batch limit is 20 products")
    if not body.product_ids:
        raise HTTPException(status_code=400, detail="product_ids must not be empty")

    raw_results = await run_orchestrator_batch(body.product_ids, db)

    decisions = []
    failed = 0
    for _, decision, error in raw_results:
        if decision is not None:
            decisions.append(decision)
        else:
            failed += 1

    return BatchPredictResponse(results=decisions, total=len(body.product_ids), failed=failed)


@router.get("/predictions/history/{product_id}", response_model=list[PredictionOut])
async def prediction_history(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Prediction)
        .where(Prediction.product_id == product_id)
        .order_by(Prediction.created_at.desc())
        .limit(30)
    )
    return result.scalars().all()
