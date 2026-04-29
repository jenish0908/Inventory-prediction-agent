import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, Integer, cast

from app.models.database import AgentEvaluation, Prediction
from app.models.schemas import EvaluationFeedbackRequest, EvaluationOut, EvaluationSummary
from app.services.db import get_db

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("/summary", response_model=EvaluationSummary)
async def evaluation_summary(db: AsyncSession = Depends(get_db)):
    eval_result = await db.execute(
        select(
            func.avg(AgentEvaluation.accuracy_score).label("avg_accuracy"),
            func.avg(AgentEvaluation.cost_usd).label("avg_cost"),
            func.sum(cast(AgentEvaluation.hallucination_flag, Integer)).label("hallucination_count"),
            func.count(AgentEvaluation.id).label("total_evaluations"),
        )
    )
    eval_row = eval_result.one()

    pred_result = await db.execute(
        select(
            func.count(Prediction.id).label("total_predictions"),
            func.avg(Prediction.latency_ms).label("avg_latency"),
        )
    )
    pred_row = pred_result.one()

    total_evals = eval_row.total_evaluations or 0
    hallucination_count = int(eval_row.hallucination_count or 0)

    return EvaluationSummary(
        avg_accuracy_score=eval_row.avg_accuracy,
        avg_latency_ms=pred_row.avg_latency,
        avg_cost_usd=eval_row.avg_cost,
        hallucination_count=hallucination_count,
        hallucination_rate=(hallucination_count / total_evals) if total_evals > 0 else None,
        total_predictions=pred_row.total_predictions or 0,
        total_evaluations=total_evals,
    )


@router.post("/{prediction_id}/feedback", response_model=EvaluationOut, status_code=200)
async def submit_feedback(
    prediction_id: uuid.UUID,
    body: EvaluationFeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    pred_result = await db.execute(select(Prediction).where(Prediction.id == prediction_id))
    if pred_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Prediction not found")

    eval_result = await db.execute(
        select(AgentEvaluation).where(AgentEvaluation.prediction_id == prediction_id)
    )
    evaluation = eval_result.scalar_one_or_none()

    if evaluation is None:
        evaluation = AgentEvaluation(prediction_id=prediction_id)
        db.add(evaluation)

    evaluation.accuracy_score = body.accuracy_score
    evaluation.hallucination_flag = body.hallucination_flag
    evaluation.feedback = body.feedback

    await db.commit()
    await db.refresh(evaluation)
    return evaluation
