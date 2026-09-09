-- T21 (D10): đếm review có nhu cầu chưa đáp ứng (nút thắt phát hiện nhưng
-- không có ưu đãi khớp), nhóm theo nút thắt. NULL-safe: hàng cũ pre-migration
-- có profile_snapshot = NULL bị loại tự nhiên vì NULL->>'x' = NULL <> 'true'.
--
-- KHÔNG dashboard, KHÔNG endpoint metrics (D10) — chạy tay khi cần.
SELECT count(*), profile_snapshot->>'unmet_bottleneck' AS unmet_bottleneck
FROM review_queue
WHERE profile_snapshot->>'unmet_demand_flag' = 'true'
GROUP BY unmet_bottleneck;
