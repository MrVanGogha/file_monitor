import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

from sqlalchemy import select

from app.domain.models import ScanTask
from app.storage import db as db
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer
from app.storage.redis_client import get_redis


@dataclass
class _Worker:
    task: asyncio.Task
    stop_event: asyncio.Event
    scan_dir: Optional[str]
    scan_mode: Optional[int]


class MonitorManager:
    """扫描任务的统一管理器：负责任务的启动、停止、刷新与恢复，并维护后台工作协程与状态。"""

    def __init__(self) -> None:
        self._workers: Dict[int, _Worker] = {}
        self._lock = asyncio.Lock()

    async def restore_on_startup(self) -> None:
        """在应用启动时恢复数据库中 is_enabled=1 的任务，并按配置启动对应的后台监控协程（避免重复启动）。"""
        if db.SessionLocal is None:
            return
        async with self._lock:
            async with db.SessionLocal() as session:  
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
        """停止并清理当前所有运行中的扫描任务（优雅退出，必要时强制取消）。"""
        async with self._lock:
            ids = list(self._workers.keys())
            for tid in ids:
                await self._stop_locked(tid)

    async def start_task(self, task_id: int, scan_task_id: str, scan_dir: Optional[str], scan_mode: Optional[int]) -> None:
        """按给定配置启动单个扫描任务；若已存在同一 task_id 的任务，则先停止再重新启动（避免重复）。"""
        async with self._lock:
            # 已存在则先停止再启动（简化处理，避免重复）
            if task_id in self._workers:
                await self._stop_locked(task_id)
            await self._start_locked(task_id, scan_task_id, scan_dir, scan_mode)

    async def stop_task(self, task_id: int) -> None:
        """停止指定 task_id 的扫描任务，等待后台协程退出并释放资源。"""
        async with self._lock:
            await self._stop_locked(task_id)

    async def refresh_task(self, task_id: int, scan_task_id: str, scan_dir: Optional[str], scan_mode: Optional[int]) -> None:
        """使用新配置刷新指定任务，相当于先停止旧任务再按新参数启动。"""
        async with self._lock:
            # 刷新 = 停止后按新配置启动
            if task_id in self._workers:
                await self._stop_locked(task_id)
            await self._start_locked(task_id, scan_task_id, scan_dir, scan_mode)

    async def _start_locked(self, task_id: int, scan_task_id: str, scan_dir: Optional[str], scan_mode: Optional[int]) -> None:
        """在持有内部锁的前提下创建并登记后台工作协程与停止事件，用于启动任务的内部实现。"""
        stop_event = asyncio.Event()
        coro = self._worker_loop(task_id, scan_task_id, scan_dir, scan_mode, stop_event)
        task = asyncio.create_task(coro, name=f"scan-worker-{task_id}")
        self._workers[task_id] = _Worker(task=task, stop_event=stop_event, scan_dir=scan_dir, scan_mode=scan_mode)

    async def _stop_locked(self, task_id: int) -> None:
        """在持有内部锁的前提下停止并回收任务协程：先尝试优雅等待，超时则取消。"""
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

    async def _process_file(self, task_id: int, scan_task_id: str, path: Path, source: str) -> None:
        """统一的文件处理入口。当前实现为占位（休眠3秒）；可在此编排业务处理并在完成后更新去重集合。"""
        source_cn = {"FULL": "全量", "NEW": "新增"}.get(source, source)
        print(f"[task={task_id} sid={scan_task_id}] {source_cn} 文件: {path}")
        await asyncio.sleep(3)

    async def _worker_loop(
        self,
        task_id: int,
        scan_task_id: str,
        scan_dir: Optional[str],
        scan_mode: Optional[int],
        stop_event: asyncio.Event,
    ) -> None:
        """单个扫描任务的后台工作协程。
        - 模式0：全量扫描后切换到增量监听（watchdog），并补偿全量期间产生的新增文件
        - 模式1：仅增量监听（watchdog），以当前目录快照为基线，不处理既有文件
        - 模式2：仅执行一次全量扫描，完成后直接退出
        同时使用 Redis 记录已处理文件以实现幂等与去重；stop_event 用于优雅停止。
        """
        # 最小可用版：全量=递归遍历；增量=watchdog 监听（先启动监听，再做全量，避免窗口）
        interval = 2.0

        if scan_dir is None or not str(scan_dir).strip():
            print(f"[task={task_id} sid={scan_task_id}] 扫描目录为空，工作协程空闲")
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            print(f"[task={task_id} sid={scan_task_id}] 已停止（扫描目录为空）")
            return

        base = Path(scan_dir)
        if not base.exists() or not base.is_dir():
            print(f"[task={task_id} sid={scan_task_id}] 扫描目录不存在或不是目录: {scan_dir}")
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
            print(f"[task={task_id} sid={scan_task_id}] 已停止（目录缺失）")
            return

        mode = 0 if scan_mode is None else int(scan_mode)

        def list_all_files() -> Set[Path]:
            files: Set[Path] = set()
            for p in base.rglob("*"):
                if p.is_file():
                    files.add(p)
            return files

        loop = asyncio.get_running_loop()
        queue: "asyncio.Queue[Path]" = asyncio.Queue(maxsize=10000)

        # Redis：加载该任务已处理过的文件集合（以字符串路径保存）
        redis = await get_redis()
        redis_key = f"scan:seen:{scan_task_id}"
        processed_strs = await redis.smembers(redis_key)
        seen: Set[str] = set(processed_strs)

        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        class _NewFileHandler(FileSystemEventHandler):
            def on_created(self, event) -> None:
                try:
                    if getattr(event, "is_directory", False):
                        return
                    path = Path(event.src_path)
                    loop.call_soon_threadsafe(queue.put_nowait, path)
                except Exception:
                    pass

            def on_moved(self, event) -> None:
                try:
                    if getattr(event, "is_directory", False):
                        return
                    dest = Path(event.dest_path)
                    loop.call_soon_threadsafe(queue.put_nowait, dest)
                except Exception:
                    pass

        def _start_observer() -> Observer:
            observer = Observer()
            handler = _NewFileHandler()
            observer.schedule(handler, str(base), recursive=True)
            observer.start()
            return observer

        # 模式2：全量一次
        if mode == 2:
            snapshot = list_all_files()
            for f in sorted(snapshot):
                fstr = str(f)
                if fstr in seen:
                    continue
                await self._process_file(task_id, scan_task_id, f, source="FULL")
                await redis.sadd(redis_key, fstr)
                seen.add(fstr)
            print(f"[task={task_id} sid={scan_task_id}] 全量扫描完成，退出工作协程")
            return

        # 模式1：仅增量（先启动监听，然后以当前目录为基线，不处理既有文件）
        if mode == 1:
            observer = _start_observer()
            print(f"[task={task_id} sid={scan_task_id}] 已启动增量监听（watchdog），目录: {scan_dir}")
            baseline = list_all_files()
            print(f"[task={task_id} sid={scan_task_id}] 仅增量模式，基线文件数: {len(baseline)}")
            try:
                while not stop_event.is_set():
                    try:
                        p = await asyncio.wait_for(queue.get(), timeout=interval)
                        try:
                            if p.is_file():
                                pstr = str(p)
                                if pstr not in seen:
                                    await self._process_file(task_id, scan_task_id, p, source="NEW")
                                    await redis.sadd(redis_key, pstr)
                                    seen.add(pstr)
                        finally:
                            queue.task_done()
                    except asyncio.TimeoutError:
                        pass
            finally:
                try:
                    observer.stop()
                finally:
                    try:
                        await asyncio.to_thread(observer.join, 3.0)
                    except Exception:
                        pass
                print(f"[task={task_id} sid={scan_task_id}] 已停止（增量/监听）")
            return

        # 默认：模式0 全量+增量（先启动监听，做全量，然后进入增量）
        observer = _start_observer()
        print(f"[task={task_id} sid={scan_task_id}] 已启动监听（全量前置阶段），目录: {scan_dir}")
        try:
            # 全量阶段
            snapshot = list_all_files()
            for f in sorted(snapshot):
                if stop_event.is_set():
                    break
                fstr = str(f)
                if fstr in seen:
                    continue
                await self._process_file(task_id, scan_task_id, f, source="FULL")
                await redis.sadd(redis_key, fstr)
                seen.add(fstr)

            # 直接切换到增量循环（不做 get_nowait 排空补偿）
            print(f"[task={task_id} sid={scan_task_id}] 切换到增量监听（watchdog）")
            while not stop_event.is_set():
                try:
                    p = await asyncio.wait_for(queue.get(), timeout=interval)
                    try:
                        if p.is_file():
                            pstr = str(p)
                            if pstr not in seen:
                                await self._process_file(task_id, scan_task_id, p, source="NEW")
                                await redis.sadd(redis_key, pstr)
                                seen.add(pstr)
                    finally:
                        queue.task_done()
                except asyncio.TimeoutError:
                    pass
        finally:
            try:
                observer.stop()
            finally:
                try:
                    await asyncio.to_thread(observer.join, 3.0)
                except Exception:
                    pass
            print(f"[task={task_id} sid={scan_task_id}] 已停止（全量+增量/监听）")
        return
 




# 单例实例
monitor_manager = MonitorManager()