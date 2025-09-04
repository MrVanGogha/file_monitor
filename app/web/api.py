from fastapi import APIRouter, Depends, status

from app.web.users import router as users_router
from pydantic import BaseModel
from typing import Optional, Literal, Any
import json
import time
from app.storage.redis_client import get_redis

from app.web.scan_tasks import router as scan_tasks_router
api_router = APIRouter()
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(scan_tasks_router, prefix="/scan-tasks", tags=["scan_tasks"])

class VideoSlicingTaskIn(BaseModel):
    video_id: str
    source: str  # 支持 http(s) 或 s3 等自定义协议
    priority: Literal["low", "normal", "high"] = "normal"
    opts: Optional[dict[str, Any]] = None
    ts: Optional[int] = None  # 毫秒时间戳，可不传


@api_router.post("/tasks/video/slicing", status_code=status.HTTP_201_CREATED)
async def enqueue_video_slicing_task(payload: VideoSlicingTaskIn, redis=Depends(get_redis)):
    fields = {
        "video_id": payload.video_id,
        "source": payload.source,
        "priority": payload.priority,
        "opts": json.dumps(payload.opts) if payload.opts is not None else "",
        "ts": str(payload.ts if payload.ts is not None else int(time.time() * 1000)),
    }
    msg_id = await redis.xadd(
        "stream:video.slicing.task",
        fields,
        maxlen=10000,        # 可选：限制流长度
        approximate=True,    # 可选：使用近似裁剪以提升性能
    )
    return {"message_id": msg_id}