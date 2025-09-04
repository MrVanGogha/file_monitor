from typing import Optional
from pydantic import BaseModel, Field


class ScanTaskBase(BaseModel):
    task_name: Optional[str] = Field(default=None, description="任务名称")
    task_status: Optional[int] = Field(default=None, description="任务状态：0-待执行 1-执行中 2-成功 3-失败")
    is_enabled: Optional[int] = Field(default=None, description="启用状态：0-禁用 1-启用")
    scan_dir: Optional[str] = Field(default=None, description="扫描目录")
    scan_mode: Optional[int] = Field(default=None, description="扫描模式：0-全量+增量 1-增量 2-全量")


class ScanTaskCreate(ScanTaskBase):
    # 为便捷起见，创建时允许直接设置这些字段的值；若未传，使用数据库默认
    task_status: Optional[int] = 0
    is_enabled: Optional[int] = 1
    # 推荐创建时提供扫描目录和模式
    scan_dir: Optional[str] = None
    scan_mode: Optional[int] = None


class ScanTaskUpdate(ScanTaskBase):
    # 全部可选，用于部分更新
    scan_task_id: Optional[str] = None


class ScanTaskRead(BaseModel):
    id: int
    scan_task_id: str
    task_name: Optional[str]
    task_status: int
    is_enabled: int
    scan_dir: Optional[str]
    scan_mode: Optional[int]

    class Config:
        from_attributes = True