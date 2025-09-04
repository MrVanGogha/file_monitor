from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base
from typing import Optional
from sqlalchemy import Integer, String, text

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(unique=True, index=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



class ScanTask(Base):
    __tablename__ = "scan_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    scan_task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="任务唯一标识")
    task_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="任务名称")
    task_status: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), comment="任务状态：0-待执行 1-执行中 2-成功 3-失败")
    is_enabled: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), comment="启用状态：0-禁用 1-启用")

    scan_dir: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="扫描目录")
    scan_mode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="扫描模式：0-全量+增量 1-增量 2-全量")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())