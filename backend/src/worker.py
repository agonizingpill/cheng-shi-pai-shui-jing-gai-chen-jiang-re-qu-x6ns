import os
import socket
import time
from pathlib import Path

from redis import Redis

from .database import SessionLocal
from .schema_bootstrap import ensure_schema
from .services.cluster import cluster_batch
from .services.job_runtime import (
    JOB_QUEUE_KEY,
    LEASE_SECONDS,
    claim_job_by_id,
    reap_stale_jobs,
    reconcile_enqueued,
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SHARED_DIR = Path(os.getenv("SHARED_DIR", "/shared"))
# 认领指定 job 后立即退出（不写结果），用于演示「算到一半中断 → 接管」
CRASH_AFTER_CLAIM_JOB_ID = os.getenv("CRASH_AFTER_CLAIM_JOB_ID", "")
# 认领指定 job 后持租约挂起，睡过接管窗口后仍用旧 token 尝试出片，
# 用于演示旧进程迟到写入被 fencing 拦截
HANG_AFTER_CLAIM_JOB_ID = os.getenv("HANG_AFTER_CLAIM_JOB_ID", "")

queue = Redis.from_url(REDIS_URL, decode_responses=True)


def worker_id():
    return f"{socket.gethostname()}-{os.getpid()}"


def main():
    wid = worker_id()
    ensure_schema()
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    tick = 0
    while True:
        (SHARED_DIR / "worker-heartbeat").touch()
        db = SessionLocal()
        try:
            # 每 5 秒：收回租约超时的中断任务；兜底重新投递登记后丢失的消息
            if tick % 5 == 0:
                reaped = reap_stale_jobs(db, wid)
                for job_id in reaped:
                    queue.rpush(JOB_QUEUE_KEY, str(job_id))
                reconcile_enqueued(db, queue)
            item = queue.blpop(JOB_QUEUE_KEY, timeout=3)
            if item:
                job_id = int(item[1])
                # 原子认领：重复投递的消息在此被幂等吞掉（任务已非 queued）
                job = claim_job_by_id(db, job_id, wid)
                if job is None:
                    continue
                if str(job.id) == CRASH_AFTER_CLAIM_JOB_ID:
                    # 模拟进程崩溃：任务保持 running、租约将到期，等待接管
                    print(f"[fault-injection] worker {wid} crashes after claiming job {job.id}", flush=True)
                    return
                if str(job.id) == HANG_AFTER_CLAIM_JOB_ID:
                    # 睡过两个租约周期：期间任务会被其他 worker 收回并接手；
                    # 醒来后本进程仍用旧 fencing token 写回，由 cluster_batch 守卫拦截
                    print(f"[fault-injection] worker {wid} holds stale lease of job {job.id}, resumes after takeover window", flush=True)
                    time.sleep(LEASE_SECONDS * 2 + 5)
                cluster_batch(db, job.id, wid)
        finally:
            db.close()
        tick += 1
        time.sleep(1)


if __name__ == "__main__":
    main()
