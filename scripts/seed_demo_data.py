"""
Seed script: inserts 10 products across 3 categories + 30 days of sales history each.
At least 2 products have critically low stock to trigger restock recommendations.

Run (from project root): python -m scripts.seed_demo_data
"""

import asyncio
import random
import uuid
from datetime import date, timedelta

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.models.database import Product, SalesHistory
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SUPPLIER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
SUPPLIER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
SUPPLIER_C = uuid.UUID("33333333-3333-3333-3333-333333333333")

PRODUCT_SPECS = [
    # Dairy — index 0 has critically low stock
    dict(name="Whole Milk 1L",       category="dairy",     supplier_id=SUPPLIER_A, lead_time_days=3, reorder_point=50, current_stock=8,   avg_daily_sales=18, variance=4),
    dict(name="Greek Yogurt 500g",   category="dairy",     supplier_id=SUPPLIER_A, lead_time_days=3, reorder_point=30, current_stock=120,  avg_daily_sales=8,  variance=2),
    dict(name="Cheddar Cheese 200g", category="dairy",     supplier_id=SUPPLIER_B, lead_time_days=5, reorder_point=40, current_stock=95,   avg_daily_sales=10, variance=3),
    # Beverages — index 3 has critically low stock
    dict(name="Orange Juice 1L",     category="beverages", supplier_id=SUPPLIER_B, lead_time_days=4, reorder_point=60, current_stock=12,   avg_daily_sales=22, variance=6),
    dict(name="Sparkling Water 500ml",category="beverages",supplier_id=SUPPLIER_B, lead_time_days=2, reorder_point=80, current_stock=340,  avg_daily_sales=35, variance=8),
    dict(name="Energy Drink 250ml",  category="beverages", supplier_id=SUPPLIER_C, lead_time_days=7, reorder_point=50, current_stock=200,  avg_daily_sales=15, variance=5),
    dict(name="Green Tea 330ml",     category="beverages", supplier_id=SUPPLIER_C, lead_time_days=6, reorder_point=40, current_stock=175,  avg_daily_sales=12, variance=3),
    # Snacks
    dict(name="Potato Chips 150g",   category="snacks",    supplier_id=SUPPLIER_A, lead_time_days=5, reorder_point=70, current_stock=280,  avg_daily_sales=28, variance=7),
    dict(name="Granola Bar 40g",     category="snacks",    supplier_id=SUPPLIER_C, lead_time_days=4, reorder_point=50, current_stock=190,  avg_daily_sales=20, variance=5),
    dict(name="Dark Chocolate 100g", category="snacks",    supplier_id=SUPPLIER_B, lead_time_days=8, reorder_point=30, current_stock=85,   avg_daily_sales=9,  variance=2),
]


async def seed():
    random.seed(42)
    today = date.today()

    async with SessionLocal() as session:
        await session.execute(text("TRUNCATE agent_evaluations, predictions, sales_history, products CASCADE"))
        await session.commit()

        inserted_products = []

        for spec in PRODUCT_SPECS:
            avg_daily = spec["avg_daily_sales"]
            variance = spec["variance"]

            product = Product(
                name=spec["name"],
                category=spec["category"],
                supplier_id=spec["supplier_id"],
                lead_time_days=spec["lead_time_days"],
                reorder_point=spec["reorder_point"],
                current_stock=spec["current_stock"],
            )
            session.add(product)
            await session.flush()

            # Apply a subtle upward trend to the two low-stock products to make forecasting interesting
            is_trending_up = spec["current_stock"] < spec["reorder_point"]

            for days_ago in range(29, -1, -1):
                sale_date = today - timedelta(days=days_ago)
                trend_multiplier = 1.0 + (0.03 * (29 - days_ago)) if is_trending_up else 1.0
                units = max(1, int(random.gauss(avg_daily * trend_multiplier, variance)))
                session.add(SalesHistory(product_id=product.id, units_sold=units, sale_date=sale_date))

            inserted_products.append((spec["name"], spec["current_stock"], spec["reorder_point"]))

        await session.commit()

    print(f"\nSeeded {len(PRODUCT_SPECS)} products, each with 30 days of sales history.\n")
    print("Product overview:")
    print(f"  {'Name':<28} {'Stock':>6} {'Reorder':>8} {'Status'}")
    print("  " + "-" * 55)
    for name, stock, reorder in inserted_products:
        status = "⚠  LOW STOCK" if stock < reorder else "OK"
        print(f"  {name:<28} {stock:>6} {reorder:>8}   {status}")


if __name__ == "__main__":
    asyncio.run(seed())
