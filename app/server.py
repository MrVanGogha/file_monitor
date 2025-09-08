from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.settings import Settings
from app.storage.db import init_db, dispose_db
from app.storage.redis_client import init_redis, close_redis
from app.web.api import api_router
from app.services.monitor_manager import monitor_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialize resources
    settings = Settings()

    await init_db(settings)
    await init_redis(settings)
    # 启动后恢复任务
    await monitor_manager.restore_on_startup()
    try:
        yield
    finally:
        # 先停止监控，再清理资源
        await monitor_manager.shutdown_all()
        await close_redis()
        await dispose_db()


def create_app() -> FastAPI:
    settings = Settings()

    application = FastAPI(title="File Monitor API", version="0.1.0")

    # Include routers
    application.include_router(api_router, prefix=settings.api_prefix)

    # Set lifespan after router creation
    application.router.lifespan_context = lifespan  # type: ignore[attr-defined]

    return application