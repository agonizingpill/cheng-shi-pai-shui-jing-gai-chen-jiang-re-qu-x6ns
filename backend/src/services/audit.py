from ..models import AuditLog

def record(db, actor_id, action, entity_type, entity_id=None, detail=None):
    db.add(AuditLog(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id else None, detail=detail or {}))
