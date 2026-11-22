"""分析任务的可靠运行时。

职责：
- ``claim_job``      原子认领队列任务（条件 UPDATE，并发 worker 只有一个赢）
- ``reap_stale_jobs`` 租约超时后把中断的 running 任务重新置回 queued，
  fencing token +1，使旧 worker 的迟到结果无法提交
- ``finalize_job``   带 fencing token 的条件提交，过期写入被拒绝并落事件
- ``reconcile_enqueued`` 兜底「已登记但消息没进 Redis」的任务
"""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..models import AnalysisJob, AnalysisJobEvent

JOB_QUEUE_KEY = "manhole_settlement_jobs"
LEASE_SECONDS = int(os.getenv("JOB_LEASE_SECONDS", "20"))
QUEUE_RECONCILE_AFTER_SECONDS = int(os.getenv("JOB_QUEUE_RECONCILE_SECONDS", "10"))

TERMINAL_STATUSES = ("succeeded", "failed")


def utcnow():
    return datetime.now(timezone.utc)


def add_event(db, job, event_type, worker_id=None, detail=None):
    db.add(
        AnalysisJobEvent(
            job_id=job.id,
            event_type=event_type,
            worker_id=worker_id,
            detail=detail or {},
        )
    )


def claim_job(db, worker_id):
    """原子认领最老的 queued 任务。成功返回带新租约的 job，否则 None。"""
    now = utcnow()
    candidate = db.execute(
        select(AnalysisJob)
        .where(AnalysisJob.status == "queued")
        .order_by(AnalysisJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if candidate is None:
        return None
    candidate.status = "running"
    candidate.worker_id = worker_id
    candidate.attempts += 1
    candidate.fencing_token += 1
    candidate.started_at = now
    candidate.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    add_event(
        db,
        candidate,
        "claimed",
        worker_id,
        {"attempt": candidate.attempts, "fencing_token": candidate.fencing_token},
    )
    db.commit()
    db.refresh(candidate)
    return candidate


def claim_job_by_id(db, job_id, worker_id):
    """原子认领指定 id 的 queued 任务（Redis 消息驱动路径）。"""
    now = utcnow()
    job = db.execute(
        select(AnalysisJob)
        .where(AnalysisJob.id == job_id)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None or job.status != "queued":
        db.rollback()
        return None
    job.status = "running"
    job.worker_id = worker_id
    job.attempts += 1
    job.fencing_token += 1
    job.started_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    add_event(
        db,
        job,
        "claimed",
        worker_id,
        {"attempt": job.attempts, "fencing_token": job.fencing_token},
    )
    db.commit()
    db.refresh(job)
    return job


def _requeue(db, job, reason, worker_id=None):
    now = utcnow()
    job.status = "queued"
    job.worker_id = None
    job.lease_expires_at = None
    job.fencing_token += 1  # 旧 worker 此后的提交全部作废
    add_event(
        db,
        job,
        "requeued",
        worker_id,
        {"reason": reason, "next_fencing_token": job.fencing_token},
    )
    return now


def reap_stale_jobs(db, reaper_id):
    """把租约过期仍在 running 的任务收回队列，等待其他 worker 接手。"""
    now = utcnow()
    stale = db.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.status == "running",
            AnalysisJob.lease_expires_at.is_not(None),
            AnalysisJob.lease_expires_at < now,
        )
        .with_for_update(skip_locked=True)
    ).scalars().all()
    requeued = []
    for job in stale:
        _requeue(db, job, "lease_expired", reaper_id)
        requeued.append(job.id)
    if requeued:
        db.commit()
    return requeued


def reconcile_enqueued(db, redis_queue):
    """outbox 兜底：登记已久仍未被认领的 queued 任务，重新投递消息。

    Redis 消息丢失（或 rpush 前进程崩溃）时任务会永远停在 queued。
    重复投递是安全的：``claim_job`` 的条件更新保证只被消费一次。
    """
    cutoff = utcnow() - timedelta(seconds=QUEUE_RECONCILE_AFTER_SECONDS)
    orphaned = db.execute(
        select(AnalysisJob).where(
            AnalysisJob.status == "queued",
            AnalysisJob.enqueued_at.is_not(None),
            AnalysisJob.enqueued_at < cutoff,
        )
    ).scalars().all()
    for job in orphaned:
        redis_queue.rpush(JOB_QUEUE_KEY, str(job.id))
        add_event(db, job, "redis_repush", detail={"queue": JOB_QUEUE_KEY})
    if orphaned:
        db.commit()
    return [job.id for job in orphaned]


def finalize_job(db, job, status, *, result=None, error=None,
                 worker_id=None, fencing_token=None):
    """带 fencing 的终态提交。

    返回 (accepted, job)。``fencing_token`` 与当前任务不一致（该任务已被
    接管、token 已递增）时拒绝写入，并记录 ``stale_write_rejected`` 事件，
    保证旧 worker 的迟到结果不会覆盖接手方出片。
    """
    if fencing_token is not None and fencing_token != job.fencing_token:
        add_event(
            db,
            job,
            "stale_write_rejected",
            worker_id,
            {
                "stale_token": fencing_token,
                "current_token": job.fencing_token,
                "attempted_status": status,
            },
        )
        db.commit()
        return False, job

    if job.status in TERMINAL_STATUSES:
        add_event(
            db,
            job,
            "duplicate_finish_ignored",
            worker_id,
            {"attempted_status": status, "current_status": job.status},
        )
        db.commit()
        return False, job

    now = utcnow()
    job.status = status
    job.result = result
    job.error = error
    job.finished_at = now
    job.lease_expires_at = None
    add_event(
        db,
        job,
        "succeeded" if status == "succeeded" else "failed",
        worker_id,
        {"fencing_token": job.fencing_token},
    )
    db.commit()
    return True, job


def touch_lease(db, job, worker_id):
    """长任务续租，避免正常执行被误判为中断。"""
    job.lease_expires_at = utcnow() + timedelta(seconds=LEASE_SECONDS)
    db.commit()
