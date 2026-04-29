from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import Product
from app.models.schemas import ProductCreate, ProductOut
from app.services.db import get_db

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).order_by(Product.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(body: ProductCreate, db: AsyncSession = Depends(get_db)):
    product = Product(**body.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
