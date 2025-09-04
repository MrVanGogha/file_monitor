import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

from sqlalchemy import select

from app.domain.models import ScanTask
from app.storage.db import SessionLocal


@dataclass
class _Worker:
    task: asyncio.Task
    stop_event: asyncio.Event
    scan_dir: Optional[str]
    scan_mode: Optional[int]


class MonitorManager:
    def __init__(self) -> None:
        self._workers: Dict[int, _Worker] = {}
        self._lock = asyncio.Lock()

    async def restore_on_startup(self) -> None:
        # 恢复所有 is_enabled=1 的任务
        if SessionLocal is None:
            return
        async with self._lock:
            async with SessionLocal() as session:  # type: ignore
                result = await session.execute(select(ScanTask).where(ScanTask.is_enabled == 1))
                tasks = result.scalars().all()
                for t in tasks:
                    # 避免重复
                    if t.id in self._workers:
                        continue
                    await self._start_locked(
                        task_id=t.id,
                        scan_task_id=t.scan_task_id,
                        scan_dir=t.scan_dir,
                        scan_mode=t.scan_mode,
                    )

    async def shutdown_all(self) -> None:
        async with self._lock:
            ids = list(self._workers.keys())
            for tid in ids:
                await self._stop_locked(tid)

    async def start_task(self, task_id: int, scan_task_id: str, scan_dir: Optional[str], scan_mode: Optional[int]) -> None:
        async with self._lock:
            # 已存在则先停止再启动（简化处理，避免重复）
            if task_id in self._workers:
                await self._stop_locked(task_id)
            await self._start_locked(task_id, scan_task_id, scan_dir, scan_mode)

    async def stop_task(self, task_id: int) -> None:
        async with self._lock:
            await self._stop_locked(task_id)

    async def refresh_task(self, task_id: int, scan_task_id: str, scan_dir: Optional[str], scan_mode: Optional[int]) -> None:
        async with self._lock:
            # 刷新 = 停止后按新配置启动
            if task_id in self._workers:
                await self._stop_locked(task_id)
            await self._start_locked(task_id, scan_task_id, scan_dir, scan_mode)

    async def _start_locked(self, task_id: int, scan_task_id: str, scan_dir: Optional[str], scan_mode: Optional[int]) -> None:
        stop_event = asyncio.Event()
        coro = self._worker_loop(task_id, scan_task_id, scan_dir, scan_mode, stop_event)
        task = asyncio.create_task(coro, name=f"scan-worker-{task_id}")
        self._workers[task_id] = _Worker(task=task, stop_event=stop_event, scan_dir=scan_dir, scan_mode=scan_mode)

    async def _stop_locked(self, task_id: int) -> None:
        worker = self._workers.pop(task_id, None)
        if not worker:
            return
        worker.stop_event.set()
        try:
            await asyncio.wait_for(worker.task, timeout=5.0)
        except asyncio.TimeoutError:
            worker.task.cancel()
            try:
                await worker.task
            except asyncio.CancelledError:
                pass

    async def _worker_loop(
        self,
        task_id: int,
        scan_task_id: str,
        scan_dir: Optional[str],
        scan_mode: Optional[int],
        stop_event: asyncio.Event,
    ) -> None:
        # 最小可用版：基于 asyncio 轮询 + Path 遍历；仅打印发现的文件
        # interval 可以后续放到配置
        interval = 2.0

        if scan_dir is None or not str(scan_dir).strip():
            print(f"[task={task_id} sid={scan_task_id}] scan_dir is empty, worker idle")
            # 空目录则空跑，直到被停止或配置被刷新
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            print(f"[task={task_id} sid={scan_task_id}] stopped (empty scan_dir)")
            return

        base = Path(scan_dir)
        if not base.exists() or not base.is_dir():
            print(f"[task={task_id} sid={scan_task_id}] scan_dir not exists or not dir: {scan_dir}")
            # 目录不存在则重试等待
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            print(f"[task={task_id} sid={scan_task_id}] stopped (dir missing)")
            return

        mode = 0 if scan_mode is None else int(scan_mode)

        def list_all_files() -> Set[Path]:
            files: Set[Path] = set()
            for p in base.rglob("*"):
                if p.is_file():
                    files.add(p)
            return files

        # 三种模式
        if mode == 2:
            # 全量一次
            snapshot = list_all_files()
            for f in sorted(snapshot):
                print(f"[task={task_id} sid={scan_task_id}] FULL: {f}")
            print(f"[task={task_id} sid={scan_task_id}] full scan completed, exit worker")
            return

        if mode == 1:
            # 增量：启动时做一份快照，不处理既有文件
            seen = list_all_files()
            print(f"[task={task_id} sid={scan_task_id}] incremental mode, baseline={len(seen)} files")
            while not stop_event.is_set():
                current = list_all_files()
                new_files = current - seen
                for f in sorted(new_files):
                    print(f"[task={task_id} sid={scan_task_id}] NEW: {f}")
                seen |= new_files
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            print(f"[task={task_id} sid={scan_task_id}] stopped (incremental)")
            return

        # 默认：0 全量+增量
        seen = list_all_files()
        for f in sorted(seen):
            print(f"[task={task_id} sid={scan_task_id}] FULL: {f}")
        print(f"[task={task_id} sid={scan_task_id}] switch to incremental monitoring")
        while not stop_event.is_set():
            current = list_all_files()
            new_files = current - seen
            for f in sorted(new_files):
                print(f"[task={task_id} sid={scan_task_id}] NEW: {f}")
            seen |= new_files
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
        print(f"[task={task_id} sid={scan_task_id}] stopped (full+incremental)")


# 单例实例
monitor_manager = MonitorManager()