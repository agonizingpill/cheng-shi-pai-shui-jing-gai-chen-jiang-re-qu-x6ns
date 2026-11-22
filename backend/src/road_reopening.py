"""道路封闭解除核对."""

VIEW = (
    '道路封闭解除核对',
    '交叉核对封道许可、维修区状态、最后一次复测及许可截止。只有已完工并有主管验收的片区进入解封确认。',
    ['道路', '许可', '片区', '许可截止', '施工单状态', '最后复测', '复测值 毫米', '解除条件'],
    """
SELECT n.road_name,n.permit_no,z.zone_code,n.ends_at,n.status,r.record_code,r.settlement_after_mm,
       CASE WHEN z.id IS NULL THEN '外部封道，向施工方核对'
            WHEN n.status='completed' AND z.status='closed' AND r.status='verified' AND r.pass_fail='pass'
                 AND r.verified_by IS NOT NULL THEN '可提交解封确认'
            WHEN n.ends_at<CURRENT_TIMESTAMP THEN '许可已到期，施工状态待核查'
            WHEN r.status='rejected' THEN '复测不通过，继续封闭'
            ELSE '等待完工及主管复测' END
FROM work_notices n LEFT JOIN repair_zones z ON z.id=n.zone_id
LEFT JOIN LATERAL (SELECT record_code,settlement_after_mm,status,pass_fail,verified_by FROM resurveys
                   WHERE zone_id=z.id ORDER BY measured_at DESC,id DESC LIMIT 1) r ON TRUE
WHERE n.lane_closure_required ORDER BY n.ends_at,n.id
""",
)
