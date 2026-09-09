# Sổ LUẬT TẠM — các cửa tất định chờ model gánh

Nguyên tắc (chốt với Sếp 2026-08-31 khuya): **lỗi HIỂU thì dạy model bằng ví
dụ trong prompt `understand`; regex/cửa tất định chỉ có hai vai** —
(a) bất biến an toàn (tiền, số liệu, lộ prompt, handoff): vĩnh viễn;
(b) hotfix tạm: PHẢI có điều kiện gỡ, ghi ở đây. Luật không có ngày chết là
đường quay lại core v1.

Cách gỡ một luật: chạy bộ eval liên quan (blind set / probe) với luật TẮT —
model tự đúng ≥ 9/10 biến thể của nhóm câu đó qua 2 lần chạy cách nhau ≥ 1
tuần thì xoá luật + giữ test như tài liệu hành vi.

## Đang treo (hotfix tạm — ứng viên gỡ)

| Luật | Ở đâu | Vì bug nào | Ví dụ đã vào prompt? |
|---|---|---|---|
| Ép intent `TEST_DRIVE` cụm "đặt/đăng ký lái thử" | `understand._test_drive_request` | "cho anh đặt lịch lái thử" bị gán VEHICLE_QA | ✅ understand-v2 |
| Ép intent `ON_ROAD_PRICE` cụm lăn-bánh | `understand._forced_intent` + `pricing_intent.mentions_on_road_price` | "vf3 lan banh bn" → bảng thông số | ✅ understand-v2 |
| Địa danh khi treo chọn-mẫu (C4) | `policy.decide` C4 | "Hà Nội" sau câu lái thử → Nearby/TVV | ✅ understand-v2 |
| Đính chính tỉnh giữa việc (nhánh `_province_slot`/SLOT_ANSWER) | `understand.to_understanding` cuối | "hn" bị chào lại | ✅ understand-v2 |

## Giữ vĩnh viễn (bất biến an toàn / trả lời tất định)

- `moderation_blocklist` + `is_system_probe` — két sắt.
- `_concern_topic` + `render._CONCERN_REPLIES` — đây KHÔNG chỉ là nhận diện:
  nó chọn CÂU TRẢ LỜI tất định không-số-liệu. Muốn chuyển cho model phải kèm
  nguồn fact được duyệt, là dự án riêng.
- `BUDGET_HOPELESS_RATIO`, `LONG_TRIP_MIN_RANGE_KM`, claim/plan_claims,
  `assert_clean` — luật số liệu và giọng, không phải chuyện hiểu ý.
- C4b (kể nhu cầu khi treo chọn-mẫu → vào tư vấn) — luật ĐIỀU PHỐI trạng
  thái, không phải hiểu ý; model không thay được vì quyết định nằm ở policy.

## Nhật ký gỡ

(chưa có — luật đầu tiên được gỡ thì ghi vào đây: ngày, luật, bằng chứng eval)
