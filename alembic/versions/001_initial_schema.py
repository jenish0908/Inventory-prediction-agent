"""initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("supplier_id", UUID(as_uuid=True), nullable=False),
        sa.Column("lead_time_days", sa.Integer, nullable=False),
        sa.Column("reorder_point", sa.Integer, nullable=False),
        sa.Column("current_stock", sa.Integer, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "sales_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("units_sold", sa.Integer, nullable=False),
        sa.Column("sale_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sales_history_product_id", "sales_history", ["product_id"])
    op.create_index("ix_sales_history_sale_date", "sales_history", ["sale_date"])

    op.create_table(
        "predictions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predicted_demand_7d", sa.Integer, nullable=False),
        sa.Column("confidence_score", sa.Float, nullable=False),
        sa.Column("restock_recommended", sa.Boolean, nullable=False),
        sa.Column("restock_quantity", sa.Integer, nullable=False),
        sa.Column("priority_level", sa.String(20), nullable=False),
        sa.Column("agent_reasoning", sa.Text, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_predictions_product_id", "predictions", ["product_id"])
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])

    op.create_table(
        "agent_evaluations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("prediction_id", UUID(as_uuid=True), sa.ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("accuracy_score", sa.Float, nullable=True),
        sa.Column("hallucination_flag", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("feedback", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_agent_evaluations_prediction_id", "agent_evaluations", ["prediction_id"])


def downgrade() -> None:
    op.drop_table("agent_evaluations")
    op.drop_table("predictions")
    op.drop_table("sales_history")
    op.drop_table("products")
