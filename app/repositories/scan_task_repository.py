from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ScanTask


class ScanTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, task_id: int) -> Optional[ScanTask]:
        return await self.session.get(ScanTask, task_id)

    async def get_by_scan_task_id(self, scan_task_id: str) -> Optional[ScanTask]:
        result = await self.session.execute(select(ScanTask).where(ScanTask.scan_task_id == scan_task_id))
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100, offset: int = 0) -> list[ScanTask]:
        result = await self.session.execute(select(ScanTask).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def create(self, task: ScanTask) -> ScanTask:
        self.session.add(task)
        await self.session.flush()
        return task

    async def delete(self, task: ScanTask) -> None:
        await self.session.delete(task)