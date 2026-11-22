import json, os
from datetime import datetime, timezone
from math import pi
import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy import select
from ..models import AnalysisJob, RepairZone, SurveyBatch, SurveyPoint, WorkNotice
from .geometry import bounds, overlaps

EPS_METERS = 26.0
MIN_SAMPLES = 3

def build_input(db, batch):
    points = db.execute(select(SurveyPoint).where(SurveyPoint.batch_id == batch.id).order_by(SurveyPoint.id)).scalars().all()
    return [{"id": p.id, "point_code": p.point_code, "x": p.x, "y": p.y, "settlement_mm": p.settlement_mm, "coordinate_reference": p.coordinate_reference} for p in points]

def validate_datum(batch, points):
    refs = {batch.coordinate_reference, *(p["coordinate_reference"] for p in points)}
    return refs

def cluster_batch(db, job_id):
    job = db.get(AnalysisJob, job_id)
    if not job:
        return
    batch = db.get(SurveyBatch, job.batch_id)
    try:
        job.status = "running"; db.commit()
        points = job.input_summary["points"]
        refs = validate_datum(batch, points)
        if len(refs) != 1:
            batch.status = "blocked"
            job.status = "failed"
            job.error = "坐标基准不一致，禁止聚类"
            job.finished_at = datetime.now(timezone.utc)
            db.commit(); return
        matrix = np.array([[p["x"], p["y"]] for p in points], dtype=float)
        labels = DBSCAN(eps=EPS_METERS, min_samples=MIN_SAMPLES).fit_predict(matrix)
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
                zone_code=f"RZ-{batch.batch_code.replace('SURV-2026-', '')}-{label + 1:02d}",
                batch_id=batch.id, cluster_label=label, name=f"沉降热区 {label + 1}",
                status="proposed", point_ids=[p["id"] for p in members],
                center_x=round(center_x, 2), center_y=round(center_y, 2),
                average_settlement_mm=round(avg_settlement, 2), max_settlement_mm=round(max_settlement, 2),
                local_density=density, boundary=b, original_cluster_evidence={"algorithm": "DBSCAN", "eps_m": EPS_METERS, "min_samples": MIN_SAMPLES, "point_codes": [p["point_code"] for p in members], "label": label},
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
        job.result = {"algorithm": "DBSCAN + local density score", "eps_m": EPS_METERS, "min_samples": MIN_SAMPLES, "cluster_count": cluster_count, "noise_count": noise_count, "conflicted_zones": conflicts, "point_count": len(points), "formula": "local_density = cluster_points / bbox_area × 10000"}
        job.status = "succeeded"; job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        job.status = "failed"; job.error = str(exc); job.finished_at = datetime.now(timezone.utc); db.commit()
