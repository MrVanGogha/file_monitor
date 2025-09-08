from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ScanTask
from app.repositories.scan_task_repository import ScanTaskRepository

from uuid import uuid4
from app.services.monitor_manager import monitor_manager

class ScanTaskService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ScanTaskRepository(session)

    async def create_task(
        self,
        task_name: Optional[str] = None,
        task_status: Optional[int] = 0,
        is_enabled: Optional[int] = 1,
        scan_dir: Optional[str] = None,
        scan_mode: Optional[int] = None,
    ) -> ScanTask:
        # 合法性校验（如状态范围）
        if task_status is not None and task_status not in (0, 1, 2, 3):
            raise ValueError("task_status must be one of 0,1,2,3")
        if is_enabled is not None and is_enabled not in (0, 1):
            raise ValueError("is_enabled must be 0 or 1")

        # 由后端生成唯一 scan_task_id
        scan_task_id = uuid4().hex
        # 极小概率碰撞时重试
        while await self.repo.get_by_scan_task_id(scan_task_id):
            scan_task_id = uuid4().hex

        task = ScanTask(
            scan_task_id=scan_task_id,
            task_name=task_name,
            task_status=task_status if task_status is not None else 0,
            is_enabled=is_enabled if is_enabled is not None else 1,
            scan_dir=scan_dir,
            scan_mode=scan_mode,
        )
        task = await self.repo.create(task)
        await self.session.commit()
        await self.session.refresh(task)
        # 创建完成后，若启用则启动监控
        if task.is_enabled == 1:
            await monitor_manager.start_task(
                task_id=task.id,
                scan_task_id=task.scan_task_id,
                scan_dir=task.scan_dir,
                scan_mode=task.scan_mode,
            )
        return task

    async def get_task(self, task_id: int) -> Optional[ScanTask]:
        return await self.repo.get_by_id(task_id)

    async def list_tasks(self, limit: int = 100, offset: int = 0) -> list[ScanTask]:
        return await self.repo.list(limit=limit, offset=offset)

    async def update_task(
        self,
        task_id: int,
        *,
        scan_task_id: Optional[str] = None,
        task_name: Optional[str] = None,
        task_status: Optional[int] = None,
        is_enabled: Optional[int] = None,
        scan_dir: Optional[str] = None,
        scan_mode: Optional[int] = None,
    ) -> Optional[ScanTask]:
        task = await self.repo.get_by_id(task_id)
        if not task:
            return None

        # 记录旧值，用于判断是否需要刷新
        old_is_enabled = task.is_enabled
        old_scan_dir = task.scan_dir
        old_scan_mode = task.scan_mode

        if task_name is not None:
            task.task_name = task_name
        if task_status is not None:
            if task_status not in (0, 1, 2, 3):
                raise ValueError("task_status must be one of 0,1,2,3")
            task.task_status = task_status
        if is_enabled is not None:
            if is_enabled not in (0, 1):
                raise ValueError("is_enabled must be 0 or 1")
            task.is_enabled = is_enabled
        if scan_dir is not None:
            task.scan_dir = scan_dir
        if scan_mode is not None:
            task.scan_mode = scan_mode

        await self.session.commit()
        await self.session.refresh(task)

        # 根据变更联动监控
      
        if old_is_enabled != task.is_enabled:
            if task.is_enabled == 1:
                await monitor_manager.start_task(
                    task_id=task.id,
                    scan_task_id=task.scan_task_id,
                    scan_dir=task.scan_dir,
                    scan_mode=task.scan_mode,
                )
            else:
                await monitor_manager.stop_task(task.id)
        else:
            # 未改变启用状态，但如果配置改变且当前是启用，则刷新
            if task.is_enabled == 1 and (old_scan_dir != task.scan_dir or old_scan_mode != task.scan_mode):
                await monitor_manager.refresh_task(
                    task_id=task.id,
                    scan_task_id=task.scan_task_id,
                    scan_dir=task.scan_dir,
                    scan_mode=task.scan_mode,
                )
        return task

    async def delete_task(self, task_id: int) -> bool:
        task = await self.repo.get_by_id(task_id)
        if not task:
            return False
        # 先停掉监控，再删除
        await monitor_manager.stop_task(task.id)
        await self.repo.delete(task)
        await self.session.commit()
        return True