from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserCreate, UserRead
from app.services.user_service import UserService
from app.storage.db import get_db
from app.storage.redis_client import get_redis

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    service = UserService(db, redis_client=redis)
    try:
        user = await service.create_user(username=payload.username, email=payload.email, password=payload.password)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    service = UserService(db, redis_client=redis)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/", response_model=List[UserRead])
async def list_users(limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db)):
    service = UserService(db)
    return await service.list_users(limit=limit, offset=offset)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    service = UserService(db, redis_client=redis)
    await service.delete_user(user_id)
    return {"ok": True}