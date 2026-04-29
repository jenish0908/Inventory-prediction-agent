import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Float, Boolean, Text, Date, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False)
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    sales_history: Mapped[list["SalesHistory"]] = relationship("SalesHistory", back_populates="product")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="product")


class SalesHistory(Base):
    __tablename__ = "sales_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship("Product", back_populates="sales_history")


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    predicted_demand_7d: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    restock_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    restock_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_level: Mapped[str] = mapped_column(String(20), nullable=False)
    agent_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship("Product", back_populates="predictions")
    evaluation: Mapped["AgentEvaluation"] = relationship("AgentEvaluation", back_populates="prediction", uselist=False)


class AgentEvaluation(Base):
    __tablename__ = "agent_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("predictions.id"), nullable=False)
    accuracy_score: Mapped[float] = mapped_column(Float, nullable=True)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    prediction: Mapped["Prediction"] = relationship("Prediction", back_populates="evaluation")
