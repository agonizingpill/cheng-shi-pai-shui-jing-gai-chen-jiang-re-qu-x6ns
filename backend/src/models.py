from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(60), unique=True, nullable=False)
    display_name = Column(String(80), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class ManholeAsset(Base):
    __tablename__ = "manhole_assets"
    id = Column(Integer, primary_key=True)
    asset_code = Column(String(60), unique=True, nullable=False)
    street_name = Column(String(120), nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    coordinate_reference = Column(String(40), nullable=False)
    cover_type = Column(String(40), nullable=False)
    depth_mm = Column(Float, nullable=False)
    status = Column(String(30), nullable=False, default="active")
    last_inspected_at = Column(DateTime(timezone=True), nullable=False)

class SurveyBatch(Base):
    __tablename__ = "survey_batches"
    id = Column(Integer, primary_key=True)
    batch_code = Column(String(60), unique=True, nullable=False)
    measured_at = Column(DateTime(timezone=True), nullable=False)
    instrument = Column(String(100), nullable=False)
    coordinate_reference = Column(String(40), nullable=False)
    status = Column(String(30), nullable=False, default="open")
    notes = Column(Text, nullable=True)
    points = relationship("SurveyPoint", back_populates="batch", cascade="all, delete-orphan")

class SurveyPoint(Base):
    __tablename__ = "survey_points"
    id = Column(Integer, primary_key=True)
    point_code = Column(String(60), unique=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("survey_batches.id"), nullable=False)
    manhole_id = Column(Integer, ForeignKey("manhole_assets.id"), nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    elevation_mm = Column(Float, nullable=False)
    settlement_mm = Column(Float, nullable=False)
    coordinate_reference = Column(String(40), nullable=False)
    measured_at = Column(DateTime(timezone=True), nullable=False)
    quality_status = Column(String(30), nullable=False, default="unchecked")
    cluster_label = Column(Integer, nullable=True)
    local_density = Column(Float, nullable=True)
    batch = relationship("SurveyBatch", back_populates="points")
    manhole = relationship("ManholeAsset")
    __table_args__ = (UniqueConstraint("batch_id", "manhole_id", name="uq_survey_batch_manhole"),)

class RepairZone(Base):
    __tablename__ = "repair_zones"
    id = Column(Integer, primary_key=True)
    zone_code = Column(String(60), unique=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("survey_batches.id"), nullable=False)
    cluster_label = Column(Integer, nullable=False)
    name = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False, default="proposed")
    point_ids = Column(JSON, nullable=False, default=list)
    center_x = Column(Float, nullable=False)
    center_y = Column(Float, nullable=False)
    average_settlement_mm = Column(Float, nullable=False)
    max_settlement_mm = Column(Float, nullable=False)
    local_density = Column(Float, nullable=False)
    boundary = Column(JSON, nullable=False, default=dict)
    original_cluster_evidence = Column(JSON, nullable=False, default=dict)
    split_from_id = Column(Integer, ForeignKey("repair_zones.id"), nullable=True)
    conflict_notice_id = Column(Integer, ForeignKey("work_notices.id"), nullable=True)
    split_reason = Column(Text, nullable=True)

class WorkNotice(Base):
    __tablename__ = "work_notices"
    id = Column(Integer, primary_key=True)
    notice_code = Column(String(60), unique=True, nullable=False)
    zone_id = Column(Integer, ForeignKey("repair_zones.id"), nullable=True)
    road_name = Column(String(120), nullable=False)
    contractor = Column(String(120), nullable=False)
    permit_no = Column(String(80), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    boundary = Column(JSON, nullable=False, default=dict)
    status = Column(String(30), nullable=False, default="draft")
    lane_closure_required = Column(Boolean, nullable=False, default=False)
    conflict_note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

class Resurvey(Base):
    __tablename__ = "resurveys"
    id = Column(Integer, primary_key=True)
    record_code = Column(String(60), unique=True, nullable=False)
    zone_id = Column(Integer, ForeignKey("repair_zones.id"), nullable=False)
    measured_at = Column(DateTime(timezone=True), nullable=False)
    settlement_before_mm = Column(Float, nullable=False)
    settlement_after_mm = Column(Float, nullable=False)
    delta_mm = Column(Float, nullable=False)
    pass_fail = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="submitted")
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id = Column(Integer, primary_key=True)
    job_code = Column(String(60), unique=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("survey_batches.id"), nullable=False)
    status = Column(String(30), nullable=False, default="queued")
    input_summary = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(80), nullable=False)
    entity_id = Column(String(80), nullable=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
