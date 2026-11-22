"""Business queries over authoritative project records."""

from .operations_reconciliation import RECONCILIATION_VIEWS

from .road_reopening import VIEW as ROAD_REOPENING

VIEWS = {
    'permit-coordination': (
        '道路施工许可对照',
        '比较同道路、非撤销的封道许可时段，列出每项通知许可缺口和并发通行冲突，供排班避让。',
        ['施工道路', '通知', '片区', '许可证', '开工', '完工', '重叠封道数'],
        """
SELECT n.road_name,n.notice_code,z.zone_code,COALESCE(NULLIF(n.permit_no,''),'缺许可证'),n.starts_at,n.ends_at,
       (SELECT COUNT(*) FROM work_notices other WHERE other.id<>n.id AND other.road_name=n.road_name
        AND n.lane_closure_required AND other.lane_closure_required AND other.status<>'cancelled'
        AND other.starts_at<n.ends_at AND other.ends_at>n.starts_at)
FROM work_notices n LEFT JOIN repair_zones z ON z.id=n.zone_id WHERE n.status<>'cancelled' ORDER BY n.starts_at,n.notice_code
""",
    ),
    'resurvey-recovery': (
        '维修片区复测变化',
        '对照片区沉降前后值并计算恢复比例，直观核对复测是否反弹。',
        ['片区', '复测号', '施工前 mm', '施工后 mm', '改善 mm', '恢复 %', '核验状态'],
        """
SELECT z.zone_code,r.record_code,r.settlement_before_mm,r.settlement_after_mm,
       r.settlement_before_mm-r.settlement_after_mm,
       100.0*(r.settlement_before_mm-r.settlement_after_mm)/NULLIF(r.settlement_before_mm,0),r.status
FROM resurveys r JOIN repair_zones z ON z.id=r.zone_id ORDER BY r.measured_at DESC,r.id
""",
    ),
    **RECONCILIATION_VIEWS,
    'road-reopening': ROAD_REOPENING,
}
