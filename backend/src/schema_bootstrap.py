"""幂等结构初始化。

项目未引入 Alembic，使用 ``create_all`` 建新表，并对已存在的旧库
补 ``analysis_jobs`` 可靠任务字段。所有语句均可重复执行。
"""
from sqlalchemy import text
from .database import engine

_JOB_COLUMNS = {
    "worker_id": "VARCHAR(80)",
    "lease_expires_at": "TIMESTAMP WITH TIME ZONE",
    "attempts": "INTEGER NOT NULL DEFAULT 0",
    "fencing_token": "INTEGER NOT NULL DEFAULT 0",
    "enqueued_at": "TIMESTAMP WITH TIME ZONE",
    "started_at": "TIMESTAMP WITH TIME ZONE",
}


def ensure_schema():
    from .models import Base  # 保证模型已注册

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'analysis_jobs'"
                )
            )
        }
        for name, ddl in _JOB_COLUMNS.items():
            if name not in existing:
                conn.execute(
                    text(f"ALTER TABLE analysis_jobs ADD COLUMN {name} {ddl}")
                )
