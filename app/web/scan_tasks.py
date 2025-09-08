from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.scan_task import ScanTaskCreate, ScanTaskRead, ScanTaskUpdate
from app.services.scan_task_service import ScanTaskService
from app.storage.db import get_db

router = APIRouter()


@router.post("/", response_model=ScanTaskRead, status_code=status.HTTP_201_CREATED)
async def create_scan_task(payload: ScanTaskCreate, db: AsyncSession = Depends(get_db)):
    service = ScanTaskService(db)
    try:
        task = await service.create_task(
            task_name=payload.task_name,
            task_status=payload.task_status,
            is_enabled=payload.is_enabled,
            scan_dir=payload.scan_dir,
            scan_mode=payload.scan_mode,
        )
        return task
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{task_id}", response_model=ScanTaskRead)
async def get_scan_task(task_id: int, db: AsyncSession = Depends(get_db)):
    service = ScanTaskService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ScanTask not found")
    return task


@router.get("/", response_model=List[ScanTaskRead])
async def list_scan_tasks(limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db)):
    service = ScanTaskService(db)
    return await service.list_tasks(limit=limit, offset=offset)


@router.put("/{task_id}", response_model=ScanTaskRead)
async def update_scan_task(task_id: int, payload: ScanTaskUpdate, db: AsyncSession = Depends(get_db)):
    service = ScanTaskService(db)
    try:
        task = await service.update_task(
            task_id,
            scan_task_id=payload.scan_task_id,
            task_name=payload.task_name,
            task_status=payload.task_status,
            is_enabled=payload.is_enabled,
            scan_dir=payload.scan_dir,
            scan_mode=payload.scan_mode,
        )
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ScanTask not found")
        return task
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{task_id}/enable", response_model=ScanTaskRead, status_code=status.HTTP_200_OK)
async def enable_scan_task(task_id: int, db: AsyncSession = Depends(get_db)):
    
    service = ScanTaskService(db)
    task = await service.update_task(task_id, is_enabled=1)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ScanTask not found")
    return task

@router.post("/{task_id}/disable", response_model=ScanTaskRead, status_code=status.HTTP_200_OK)
async def disable_scan_task(task_id: int, db: AsyncSession = Depends(get_db)):
    service = ScanTaskService(db)
    task = await service.update_task(task_id, is_enabled=0)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ScanTask not found")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan_task(task_id: int, db: AsyncSession = Depends(get_db)):
    service = ScanTaskService(db)
    ok = await service.delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ScanTask not found")
    return {"ok": True}