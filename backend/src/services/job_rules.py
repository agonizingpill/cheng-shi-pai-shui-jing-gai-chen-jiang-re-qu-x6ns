"""可靠任务相关的纯函数规则（不依赖数据库与三方库，便于离线单测）。"""

# 任务终态
TERMINAL_STATUSES = ("succeeded", "failed")
# 送算接口在何种既有状态下必须复用同一个 job，而不是新建任务
REUSE_STATUSES = ("queued", "running", "succeeded", "failed")


def should_reuse_job(latest_status):
    """回执丢失后的重试、排队中、运行中、已出片、失败重试都不新增任务。"""
    return latest_status in REUSE_STATUSES


def is_stale_write(job, *, worker_id, fencing_token):
    """fencing 判定：token 不匹配或 worker 已换人，旧进程的出片必须拒绝。"""
    if job is None:
        return True
    if fencing_token != job.get("fencing_token"):
        return True
    if worker_id != job.get("worker_id"):
        return True
    if job.get("status") != "running":
        return True
    return False


def next_fencing_token(current):
    """每次接管/重试递增 fencing token，使旧租约内的写入全部失效。"""
    return int(current) + 1


def lease_expired(lease_expires_at, now):
    """租约是否到期（None 表示未持有租约，不算超时）。"""
    if lease_expires_at is None:
        return False
    return lease_expires_at < now


def snapshot_params(input_summary, default_eps, default_min_samples):
    """重跑必须沿用送算时锁定的聚类尺度；缺快照才回退系统默认口径。"""
    params = (input_summary or {}).get("params") or {}
    return (
        float(params.get("eps_m", default_eps)),
        int(params.get("min_samples", default_min_samples)),
    )


def deterministic_zone_code(batch_code, cluster_label):
    """片区编号由批次码 + 簇号确定性生成：重试不产生新编号，可按原编号查询。"""
    return f"RZ-{batch_code.replace('SURV-2026-', '')}-{cluster_label + 1:02d}"
