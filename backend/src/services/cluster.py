import numpy as np
from datetime import datetime, timezone
from sklearn.cluster import DBSCAN
from sqlalchemy import select
from ..models import AnalysisJob, RepairZone, SurveyBatch, SurveyPoint, WorkNotice
from ..services.job_runtime import add_event, finalize_job
from ..services.job_rules import deterministic_zone_code, snapshot_params
from .geometry import bounds, overlaps

EPS_METERS = 26.0
MIN_SAMPLES = 3


def utcnow():
    return datetime.now(timezone.utc)

def build_input(db, batch):
    points = db.execute(select(SurveyPoint).where(SurveyPoint.batch_id == batch.id).order_by(SurveyPoint.id)).scalars().all()
    return [{"id": p.id, "point_code": p.point_code, "x": p.x, "y": p.y, "settlement_mm": p.settlement_mm, "coordinate_reference": p.coordinate_reference} for p in points]

def validate_datum(batch, points):
    refs = {batch.coordinate_reference, *(p["coordinate_reference"] for p in points)}
    return refs

def _snapshot_params(job):
    """沿用送算时锁定的聚类尺度；旧任务缺快照时回退系统固定口径。"""
    return snapshot_params(job.input_summary, EPS_METERS, MIN_SAMPLES)

def cluster_batch(db, job_id, worker_id):
    claimed = db.get(AnalysisJob, job_id)
    if not claimed:
        return
    expected_token = claimed.fencing_token
    try:
        # 写回前锁任务行：若已被租约接管（worker_id/token 变化），本次出片整体作废
        job = db.execute(
            select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
        ).scalar_one()
        if (
            job.status != "running"
            or job.worker_id != worker_id
            or job.fencing_token != expected_token
        ):
            db.rollback()
            _reject_stale(db, job_id, worker_id, expected_token, "pre_write_guard")
            return

        batch = db.get(SurveyBatch, job.batch_id)
        eps_m, min_samples = _snapshot_params(job)
        points = job.input_summary["points"]
        refs = validate_datum(batch, points)
        if len(refs) != 1:
            batch.status = "blocked"
            job.error = "坐标基准不一致，禁止聚类"
            _finish_locked(db, job, "failed", None, worker_id, expected_token)
            db.commit()
            return

        matrix = np.array([[p["x"], p["y"]] for p in points], dtype=float)
        labels = DBSCAN(eps=eps_m, min_samples=min_samples).fit_predict(matrix)
        existing = db.execute(select(RepairZone).where(RepairZone.batch_id == batch.id)).scalars().all()
        for zone in existing:
            db.delete(zone)
        db.flush()
        cluster_count = 0; noise_count = 0; zone_rows = []
        for label in sorted(set(int(x) for x in labels)):
            members = [p for p, current in zip(points, labels) if int(current) == label]
            if label == -1:
                noise_count += len(members); continue
            cluster_count += 1
            b = bounds(members)
            center_x = sum(p["x"] for p in members) / len(members)
            center_y = sum(p["y"] for p in members) / len(members)
            avg_settlement = sum(p["settlement_mm"] for p in members) / len(members)
            max_settlement = max(p["settlement_mm"] for p in members)
            area = max(1, (b["max_x"] - b["min_x"]) * (b["max_y"] - b["min_y"]))
            density = round(len(members) / area * 10000, 3)
            zone = RepairZone(
                zone_code=deterministic_zone_code(batch.batch_code, label),
                batch_id=batch.id, cluster_label=label, name=f"沉降热区 {label + 1}",
                status="proposed", point_ids=[p["id"] for p in members],
                center_x=round(center_x, 2), center_y=round(center_y, 2),
                average_settlement_mm=round(avg_settlement, 2), max_settlement_mm=round(max_settlement, 2),
                local_density=density, boundary=b, original_cluster_evidence={"algorithm": "DBSCAN", "eps_m": eps_m, "min_samples": min_samples, "point_codes": [p["point_code"] for p in members], "label": label, "job_code": job.job_code, "fencing_token": expected_token},
            )
            db.add(zone); zone_rows.append((zone, b))
        db.flush()
        notices = db.execute(select(WorkNotice).where(WorkNotice.status.in_(["active", "acknowledged"]))).scalars().all()
        conflicts = 0
        for zone, zone_bounds in zone_rows:
            for notice in notices:
                if overlaps(zone_bounds, notice.boundary):
                    zone.status = "needs_split"
                    zone.conflict_notice_id = notice.id
                    zone.split_reason = f"与 {notice.road_name} 在建边界重叠，需按施工边界拆分"
                    conflicts += 1
                    break
        point_models = {p.id: p for p in db.execute(select(SurveyPoint).where(SurveyPoint.batch_id == batch.id)).scalars().all()}
        for p in points:
            if p["id"] in point_models:
                model_point = point_models[p["id"]]
                model_point.cluster_label = next((z.cluster_label for z, _ in zone_rows if model_point.id in (z.point_ids or [])), None)
                model_point.local_density = next((z.local_density for z, _ in zone_rows if model_point.id in (z.point_ids or [])), None)
                model_point.quality_status = "clustered"
        batch.status = "clustered"
        result = {"algorithm": "DBSCAN + local density score", "eps_m": eps_m, "min_samples": min_samples, "cluster_count": cluster_count, "noise_count": noise_count, "conflicted_zones": conflicts, "point_count": len(points), "formula": "local_density = cluster_points / bbox_area × 10000", "zone_codes": [z.zone_code for z, _ in zone_rows], "job_code": job.job_code, "attempt": job.attempts}
        _finish_locked(db, job, "succeeded", result, worker_id, expected_token)
        db.commit()
    except Exception as exc:
        db.rollback()
        _mark_failure(db, job_id, worker_id, expected_token, str(exc))

def _finish_locked(db, job, status, result, worker_id, expected_token):
    """行锁持有期间的终态写入，token 不可能在本事务内被改动。"""
    job.status = status
    job.result = result
    job.lease_expires_at = None
    if status == "failed":
        job.error = job.error or "聚类执行失败"
        job.finished_at = utcnow()
    else:
        job.finished_at = utcnow()
    add_event(
        db,
        job,
        "succeeded" if status == "succeeded" else "failed",
        worker_id,
        {"fencing_token": expected_token},
    )

def _reject_stale(db, job_id, worker_id, expected_token, phase):
    job = db.get(AnalysisJob, job_id)
    if not job:
        return
    add_event(
        db,
        job,
        "stale_write_rejected",
        worker_id,
        {"phase": phase, "stale_token": expected_token, "current_token": job.fencing_token, "current_status": job.status},
    )
    db.commit()

def _mark_failure(db, job_id, worker_id, expected_token, message):
    job = db.execute(
        select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
    ).scalar_one_or_none()
    if not job:
        return
    # 已被接手或已终态：失败同样不能覆盖接手方结果
    finalize_job(
        db,
        job,
        "failed",
        error=message,
        worker_id=worker_id,
        fencing_token=expected_token,
    )
