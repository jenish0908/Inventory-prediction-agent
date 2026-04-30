"""
Seed script: inserts 55 products across 11 categories + 30 days of sales history each.
Mix of low-stock, healthy, and overstock scenarios to exercise all agent logic.

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

SUPPLIER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")  # FreshFarm Co.
SUPPLIER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")  # QuickStock Ltd.
SUPPLIER_C = uuid.UUID("33333333-3333-3333-3333-333333333333")  # Prime Distributors Inc.
SUPPLIER_D = uuid.UUID("44444444-4444-4444-4444-444444444444")  # NationWide Goods
SUPPLIER_E = uuid.UUID("55555555-5555-5555-5555-555555555555")  # Metro Wholesale

# fmt: off
PRODUCT_SPECS = [
    # ── DAIRY (5 products) ────────────────────────────────────────────────────
    dict(name="Whole Milk 1L",          category="dairy",        supplier_id=SUPPLIER_A, lead_time_days=2,  reorder_point=50,  current_stock=8,    avg_daily=18, variance=4,  trend="up"),    # critically low
    dict(name="Greek Yogurt 500g",      category="dairy",        supplier_id=SUPPLIER_A, lead_time_days=2,  reorder_point=30,  current_stock=120,  avg_daily=8,  variance=2,  trend="stable"),
    dict(name="Cheddar Cheese 200g",    category="dairy",        supplier_id=SUPPLIER_B, lead_time_days=3,  reorder_point=40,  current_stock=95,   avg_daily=10, variance=3,  trend="stable"),
    dict(name="Paneer 250g",            category="dairy",        supplier_id=SUPPLIER_A, lead_time_days=2,  reorder_point=35,  current_stock=22,   avg_daily=14, variance=3,  trend="up"),    # low stock
    dict(name="Butter 100g",            category="dairy",        supplier_id=SUPPLIER_C, lead_time_days=3,  reorder_point=25,  current_stock=310,  avg_daily=6,  variance=2,  trend="stable"), # overstock

    # ── BEVERAGES (6 products) ────────────────────────────────────────────────
    dict(name="Orange Juice 1L",        category="beverages",    supplier_id=SUPPLIER_B, lead_time_days=3,  reorder_point=60,  current_stock=12,   avg_daily=22, variance=6,  trend="up"),    # critically low
    dict(name="Sparkling Water 500ml",  category="beverages",    supplier_id=SUPPLIER_B, lead_time_days=2,  reorder_point=80,  current_stock=340,  avg_daily=35, variance=8,  trend="stable"),
    dict(name="Energy Drink 250ml",     category="beverages",    supplier_id=SUPPLIER_C, lead_time_days=4,  reorder_point=50,  current_stock=200,  avg_daily=15, variance=5,  trend="stable"),
    dict(name="Green Tea 330ml",        category="beverages",    supplier_id=SUPPLIER_C, lead_time_days=3,  reorder_point=40,  current_stock=175,  avg_daily=12, variance=3,  trend="stable"),
    dict(name="Cold Coffee 250ml",      category="beverages",    supplier_id=SUPPLIER_D, lead_time_days=3,  reorder_point=55,  current_stock=30,   avg_daily=20, variance=5,  trend="up"),    # low stock
    dict(name="Coconut Water 200ml",    category="beverages",    supplier_id=SUPPLIER_E, lead_time_days=4,  reorder_point=45,  current_stock=260,  avg_daily=18, variance=4,  trend="stable"),

    # ── SNACKS (6 products) ───────────────────────────────────────────────────
    dict(name="Potato Chips 150g",      category="snacks",       supplier_id=SUPPLIER_A, lead_time_days=4,  reorder_point=70,  current_stock=280,  avg_daily=28, variance=7,  trend="stable"),
    dict(name="Granola Bar 40g",        category="snacks",       supplier_id=SUPPLIER_C, lead_time_days=4,  reorder_point=50,  current_stock=190,  avg_daily=20, variance=5,  trend="stable"),
    dict(name="Dark Chocolate 100g",    category="snacks",       supplier_id=SUPPLIER_B, lead_time_days=5,  reorder_point=30,  current_stock=85,   avg_daily=9,  variance=2,  trend="stable"),
    dict(name="Roasted Almonds 200g",   category="snacks",       supplier_id=SUPPLIER_D, lead_time_days=5,  reorder_point=40,  current_stock=18,   avg_daily=16, variance=4,  trend="up"),    # low stock
    dict(name="Popcorn 100g",           category="snacks",       supplier_id=SUPPLIER_E, lead_time_days=3,  reorder_point=60,  current_stock=420,  avg_daily=22, variance=6,  trend="down"),  # overstock
    dict(name="Rice Crackers 150g",     category="snacks",       supplier_id=SUPPLIER_A, lead_time_days=4,  reorder_point=35,  current_stock=140,  avg_daily=11, variance=3,  trend="stable"),

    # ── PRODUCE (5 products) ──────────────────────────────────────────────────
    dict(name="Tomatoes 500g",          category="produce",      supplier_id=SUPPLIER_A, lead_time_days=1,  reorder_point=80,  current_stock=25,   avg_daily=40, variance=10, trend="up"),    # critically low
    dict(name="Spinach 250g",           category="produce",      supplier_id=SUPPLIER_A, lead_time_days=1,  reorder_point=50,  current_stock=110,  avg_daily=20, variance=6,  trend="stable"),
    dict(name="Carrots 1kg",            category="produce",      supplier_id=SUPPLIER_B, lead_time_days=2,  reorder_point=40,  current_stock=160,  avg_daily=15, variance=4,  trend="stable"),
    dict(name="Bell Peppers 3pc",       category="produce",      supplier_id=SUPPLIER_C, lead_time_days=1,  reorder_point=35,  current_stock=20,   avg_daily=18, variance=5,  trend="up"),    # low stock
    dict(name="Onions 1kg",             category="produce",      supplier_id=SUPPLIER_D, lead_time_days=2,  reorder_point=60,  current_stock=380,  avg_daily=25, variance=7,  trend="stable"),

    # ── FROZEN (5 products) ───────────────────────────────────────────────────
    dict(name="Frozen Peas 500g",       category="frozen",       supplier_id=SUPPLIER_B, lead_time_days=3,  reorder_point=40,  current_stock=95,   avg_daily=12, variance=3,  trend="stable"),
    dict(name="Frozen Pizza 350g",      category="frozen",       supplier_id=SUPPLIER_C, lead_time_days=4,  reorder_point=30,  current_stock=14,   avg_daily=12, variance=4,  trend="up"),    # low stock
    dict(name="Ice Cream 500ml",        category="frozen",       supplier_id=SUPPLIER_D, lead_time_days=3,  reorder_point=50,  current_stock=220,  avg_daily=18, variance=6,  trend="stable"),
    dict(name="Frozen Corn 400g",       category="frozen",       supplier_id=SUPPLIER_E, lead_time_days=3,  reorder_point=35,  current_stock=130,  avg_daily=10, variance=3,  trend="stable"),
    dict(name="Frozen Fries 750g",      category="frozen",       supplier_id=SUPPLIER_A, lead_time_days=4,  reorder_point=45,  current_stock=480,  avg_daily=20, variance=5,  trend="down"),  # overstock

    # ── BAKERY (5 products) ───────────────────────────────────────────────────
    dict(name="White Bread 400g",       category="bakery",       supplier_id=SUPPLIER_A, lead_time_days=1,  reorder_point=60,  current_stock=15,   avg_daily=30, variance=8,  trend="up"),    # critically low
    dict(name="Whole Wheat Bread 400g", category="bakery",       supplier_id=SUPPLIER_A, lead_time_days=1,  reorder_point=40,  current_stock=80,   avg_daily=18, variance=4,  trend="stable"),
    dict(name="Croissant 4pc",          category="bakery",       supplier_id=SUPPLIER_B, lead_time_days=1,  reorder_point=30,  current_stock=70,   avg_daily=14, variance=4,  trend="stable"),
    dict(name="Muffins 6pc",            category="bakery",       supplier_id=SUPPLIER_C, lead_time_days=2,  reorder_point=25,  current_stock=55,   avg_daily=10, variance=3,  trend="stable"),
    dict(name="Pita Bread 6pc",         category="bakery",       supplier_id=SUPPLIER_D, lead_time_days=2,  reorder_point=20,  current_stock=12,   avg_daily=8,  variance=2,  trend="up"),    # low stock

    # ── MEAT (4 products) ─────────────────────────────────────────────────────
    dict(name="Chicken Breast 500g",    category="meat",         supplier_id=SUPPLIER_B, lead_time_days=2,  reorder_point=50,  current_stock=20,   avg_daily=22, variance=5,  trend="up"),    # critically low
    dict(name="Minced Beef 500g",       category="meat",         supplier_id=SUPPLIER_C, lead_time_days=2,  reorder_point=35,  current_stock=90,   avg_daily=14, variance=4,  trend="stable"),
    dict(name="Salmon Fillet 300g",     category="meat",         supplier_id=SUPPLIER_D, lead_time_days=3,  reorder_point=25,  current_stock=60,   avg_daily=9,  variance=3,  trend="stable"),
    dict(name="Eggs 12pc",              category="meat",         supplier_id=SUPPLIER_A, lead_time_days=2,  reorder_point=70,  current_stock=350,  avg_daily=30, variance=8,  trend="stable"),

    # ── HOUSEHOLD (5 products) ────────────────────────────────────────────────
    dict(name="Dish Soap 500ml",        category="household",    supplier_id=SUPPLIER_C, lead_time_days=5,  reorder_point=40,  current_stock=180,  avg_daily=8,  variance=2,  trend="stable"),
    dict(name="Laundry Detergent 1kg",  category="household",    supplier_id=SUPPLIER_D, lead_time_days=5,  reorder_point=30,  current_stock=11,   avg_daily=7,  variance=2,  trend="up"),    # low stock
    dict(name="Toilet Paper 6pc",       category="household",    supplier_id=SUPPLIER_E, lead_time_days=4,  reorder_point=50,  current_stock=240,  avg_daily=15, variance=4,  trend="stable"),
    dict(name="Floor Cleaner 1L",       category="household",    supplier_id=SUPPLIER_A, lead_time_days=5,  reorder_point=25,  current_stock=95,   avg_daily=5,  variance=2,  trend="stable"),
    dict(name="Garbage Bags 30pc",      category="household",    supplier_id=SUPPLIER_B, lead_time_days=6,  reorder_point=20,  current_stock=130,  avg_daily=4,  variance=1,  trend="stable"),

    # ── PERSONAL CARE (5 products) ────────────────────────────────────────────
    dict(name="Shampoo 200ml",          category="personal_care",supplier_id=SUPPLIER_D, lead_time_days=6,  reorder_point=35,  current_stock=16,   avg_daily=8,  variance=2,  trend="up"),    # low stock
    dict(name="Conditioner 200ml",      category="personal_care",supplier_id=SUPPLIER_D, lead_time_days=6,  reorder_point=30,  current_stock=75,   avg_daily=6,  variance=2,  trend="stable"),
    dict(name="Toothpaste 100g",        category="personal_care",supplier_id=SUPPLIER_E, lead_time_days=5,  reorder_point=40,  current_stock=165,  avg_daily=9,  variance=2,  trend="stable"),
    dict(name="Body Lotion 300ml",      category="personal_care",supplier_id=SUPPLIER_C, lead_time_days=6,  reorder_point=25,  current_stock=90,   avg_daily=5,  variance=2,  trend="stable"),
    dict(name="Face Wash 150ml",        category="personal_care",supplier_id=SUPPLIER_B, lead_time_days=6,  reorder_point=30,  current_stock=50,   avg_daily=7,  variance=2,  trend="stable"),

    # ── GRAINS (5 products) ───────────────────────────────────────────────────
    dict(name="Basmati Rice 1kg",       category="grains",       supplier_id=SUPPLIER_E, lead_time_days=5,  reorder_point=50,  current_stock=22,   avg_daily=18, variance=5,  trend="up"),    # low stock
    dict(name="Rolled Oats 500g",       category="grains",       supplier_id=SUPPLIER_A, lead_time_days=4,  reorder_point=40,  current_stock=160,  avg_daily=12, variance=3,  trend="stable"),
    dict(name="Whole Wheat Pasta 500g", category="grains",       supplier_id=SUPPLIER_B, lead_time_days=5,  reorder_point=35,  current_stock=210,  avg_daily=10, variance=3,  trend="stable"),
    dict(name="Quinoa 500g",            category="grains",       supplier_id=SUPPLIER_C, lead_time_days=6,  reorder_point=25,  current_stock=80,   avg_daily=6,  variance=2,  trend="stable"),
    dict(name="Bread Flour 1kg",        category="grains",       supplier_id=SUPPLIER_D, lead_time_days=4,  reorder_point=30,  current_stock=9,    avg_daily=10, variance=3,  trend="up"),    # low stock

    # ── CONDIMENTS (4 products) ───────────────────────────────────────────────
    dict(name="Tomato Ketchup 500g",    category="condiments",   supplier_id=SUPPLIER_C, lead_time_days=5,  reorder_point=30,  current_stock=140,  avg_daily=8,  variance=2,  trend="stable"),
    dict(name="Olive Oil 500ml",        category="condiments",   supplier_id=SUPPLIER_E, lead_time_days=6,  reorder_point=25,  current_stock=13,   avg_daily=6,  variance=2,  trend="up"),    # low stock
    dict(name="Soy Sauce 200ml",        category="condiments",   supplier_id=SUPPLIER_D, lead_time_days=5,  reorder_point=20,  current_stock=88,   avg_daily=4,  variance=1,  trend="stable"),
    dict(name="Honey 250g",             category="condiments",   supplier_id=SUPPLIER_B, lead_time_days=7,  reorder_point=20,  current_stock=65,   avg_daily=3,  variance=1,  trend="stable"),
]
# fmt: on


async def seed():
    random.seed(42)
    today = date.today()

    async with SessionLocal() as session:
        await session.execute(
            text("TRUNCATE agent_evaluations, predictions, sales_history, products CASCADE")
        )
        await session.commit()

        inserted = []

        for spec in PRODUCT_SPECS:
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

            for days_ago in range(29, -1, -1):
                sale_date = today - timedelta(days=days_ago)
                progress = (29 - days_ago) / 29  # 0.0 → 1.0 over 30 days

                if spec["trend"] == "up":
                    multiplier = 1.0 + 0.04 * progress * 29
                elif spec["trend"] == "down":
                    multiplier = 1.0 - 0.02 * progress * 29
                else:
                    multiplier = 1.0

                units = max(1, int(random.gauss(spec["avg_daily"] * multiplier, spec["variance"])))
                session.add(SalesHistory(product_id=product.id, units_sold=units, sale_date=sale_date))

            inserted.append((spec["name"], spec["category"], spec["current_stock"], spec["reorder_point"]))

        await session.commit()

    categories = sorted(set(r[1] for r in inserted))
    print(f"\nSeeded {len(inserted)} products across {len(categories)} categories.\n")

    for cat in categories:
        cat_products = [r for r in inserted if r[1] == cat]
        print(f"  {cat.upper()} ({len(cat_products)} products)")
        for name, _, stock, reorder in cat_products:
            if stock < reorder:
                status = "⚠  LOW"
            elif stock > reorder * 5:
                status = "↑  OVERSTOCK"
            else:
                status = "OK"
            print(f"    {name:<30} stock={stock:>4}  reorder={reorder:>3}  {status}")
        print()


if __name__ == "__main__":
    asyncio.run(seed())
