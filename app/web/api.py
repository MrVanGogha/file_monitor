from fastapi import APIRouter
from app.web.users import router as users_router
from app.web.scan_tasks import router as scan_tasks_router
api_router = APIRouter()
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(scan_tasks_router, prefix="/scan-tasks", tags=["scan_tasks"])