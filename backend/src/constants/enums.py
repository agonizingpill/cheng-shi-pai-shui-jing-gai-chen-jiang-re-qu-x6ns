ROLE_OPERATOR = "operator"
ROLE_SUPERVISOR = "supervisor"
ROLE_VIEWER = "viewer"
BATCH_STATUSES = ["open", "blocked", "ready", "queued", "clustered"]
ZONE_STATUSES = ["proposed", "needs_split", "ready_for_notice", "notice_sent", "repairing", "awaiting_resurvey", "closed", "split"]
NOTICE_STATUSES = ["draft", "submitted", "acknowledged", "active", "completed", "cancelled"]
JOB_STATUSES = ["queued", "running", "succeeded", "failed"]
JOB_EVENTS = [
    "enqueued", "claimed", "requeued", "redis_repush", "manual_repush",
    "enqueue_retry", "succeeded", "failed", "stale_write_rejected",
    "duplicate_finish_ignored",
]
