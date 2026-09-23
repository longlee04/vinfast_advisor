# Runbook — canary cờ `agent_fallback`

Cờ này bật/tắt HAI móc agent của lõi v2 (plan `docs/PLAN_AGENT_MIGRATION.md`
Bước 10). Mặc định **TẮT**. Bật cờ là hành động vận hành, không phải deploy.

## Bật / tắt

```sql
-- Bật cho danh sách khách nội bộ (allowlist thắng phần trăm)
UPDATE agent_feature_flags
   SET enabled = TRUE, rollout_percent = 0, customer_allowlist = 'cus-1,cus-2,cus-3', updated_at = now()
 WHERE name = 'agent_fallback';

-- Mở theo phần trăm (băm sha256 theo customer_id — cùng khách luôn cùng nhánh)
UPDATE agent_feature_flags SET enabled = TRUE, rollout_percent = 5, updated_at = now() WHERE name = 'agent_fallback';

-- TẮT (rollback thường dùng) — hiệu lực <= 60s, KHÔNG cần deploy
UPDATE agent_feature_flags SET enabled = FALSE, updated_at = now() WHERE name = 'agent_fallback';
```

Adapter cache 60s (`FLAG_TTL_SECONDS`), nên mọi thay đổi có hiệu lực trong vòng
một phút. Hàng chưa có / đọc hỏng / DB chết → coi như **TẮT**.

## Kill-switch (sự cố)

```
AGENT_FALLBACK_KILL_SWITCH=true   # trong .env, rồi restart process
```

Thắng mọi thứ trong DB, hiệu lực ngay khi process lên. Dùng khi không vào được
DB hoặc cần chắc chắn tuyệt đối.

## Trình tự canary

| Nấc | Cấu hình | Thời gian | Điều kiện lên nấc sau |
|---|---|---|---|
| 0 | allowlist 3-5 `customer_id` nội bộ | 3 ngày | toàn bộ ngưỡng §5.4 đạt |
| 1 | `rollout_percent = 5` | 3 ngày | như trên |
| 2 | `rollout_percent = 25` | 3 ngày | như trên |
| 3 | `rollout_percent = 50` | 3 ngày | như trên |
| 4 | `rollout_percent = 100` | — | — |

**Mỗi nấc phải đạt lại toàn bộ ngưỡng mới được lên nấc sau.** Ghi lại mỗi lần
đổi nấc vào mục "Nhật ký" bên dưới: ngày, `rollout_percent`, số đo.

## Số phải xem ở mỗi nấc

```
uv run python -m scripts.core_v2_metrics --days 1 --core v2     # bảng "Chi so agent" + lý do fallback
uv run python -m scripts.agent_eval --base <api> --email <e> --password <p> --dsn "$AGENT_DATABASE_URL"
```

| # | Ngưỡng | Giá trị |
|---|---|---|
| A1 | 9 câu regression (§5.1) giống cờ OFF | 100% — cứng |
| A5 | p95 latency lượt agent | ≤ 14s |
| A6 | p95 latency lượt KHÔNG agent | không tăng quá 5% |
| A7 | `agent_error = verify_rejected` | < 15% lượt agent |
| A8 | `quote_gate` chặn | < 5% lượt agent |
| A9 | `agent_llm_calls` p99 | ≤ 4 |
| A10 | Sự cố P1/P2 | 0 |
| A11 | Lượt vừa `agent_used=true` vừa `terminal_reason=PENDING_HANDOFF` | 0 — cứng |

Truy vấn nhanh cho A11:

```sql
SELECT count(*) FROM turn_traces
 WHERE payload->>'agent_used' = 'true' AND terminal_reason = 'PENDING_HANDOFF';
```

## Rollback

1. Tắt cờ (SQL ở trên) — **luôn làm trước**, hiệu lực ≤ 60s.
2. Không vào được DB → `AGENT_FALLBACK_KILL_SWITCH=true` + restart.
3. Chỉ khi hai cách trên không đủ mới revert code: `git revert` commit của Bước
   6/7 (móc 1 / móc 2). Bước 1-5, 8, 9 không cần revert — chúng không bật gì.

## Nhật ký canary

| Ngày | Nấc | `rollout_percent` | Người đổi | Số đo / ghi chú |
|---|---|---|---|---|
| — | — | — | — | *(chưa bắt đầu — cờ đang TẮT)* |
