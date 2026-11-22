"""Additional operational reconciliation rules for this project."""

RECONCILIATION_VIEWS = {
    'survey-coordinate-preflight': (
        '测量坐标系入簇预检',
        '逐点比对来源坐标系与测量批声明，并列明质检或未入簇原因，避免异坐标点进入维修片区。',
        ['测量批', '点位', '批坐标系', '点坐标系', '质检状态', '簇标记', '复核结论'],
        """
SELECT b.batch_code,p.point_code,b.coordinate_reference,p.coordinate_reference,p.quality_status,p.cluster_label,
       CASE WHEN p.coordinate_reference<>b.coordinate_reference THEN '坐标系不一致，待转换'
            WHEN p.quality_status NOT IN ('clustered','datum_corrected','unchecked') THEN '复核点位质检状态'
            WHEN p.quality_status='clustered' AND p.cluster_label IS NULL THEN '有效离群点，现场复核'
            WHEN p.cluster_label IS NULL THEN '待入簇'
            ELSE '已记录入簇结果' END
FROM survey_points p JOIN survey_batches b ON b.id=p.batch_id
ORDER BY b.measured_at DESC,p.point_code
""",
    ),
}
