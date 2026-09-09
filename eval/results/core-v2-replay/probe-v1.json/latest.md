# Live probe benchmark — 2026-08-29T14:32:09+00:00

Server: `http://127.0.0.1:18000/api/v1`

| Chỉ số | Giá trị |
|---|---|
| Kịch bản đạt | **35/35** |
| Lượt đạt | **120/120** |
| Lỗi HTTP (500/429…) | 0 |
| Lượt chết (OUT_OF_SCOPE / UNAVAILABLE / CONTENT_BLOCKED / NO_CANDIDATE / EXPIRED) | 4 |
| Độ trễ p50 / p95 | 4.03s / 9.95s |

| Nguồn | Kịch bản đạt |
|---|---|
| sep | 18/18 |
| prod | 9/9 |
| khung-viec | 5/5 |
| feature-fit | 3/3 |

## Từng kịch bản

| ID | Tên | Lượt đạt | Lượt đỏ (tiêu chí) |
|---|---|---|---|
| LP01 | ✅ Ngân sách mơ hồ | 5/5 | — |
| LP02 | ✅ Trả lời lệch slot | 4/4 | — |
| LP03 | ✅ Đổi ý giữa chừng | 5/5 | — |
| LP04 | ✅ Phủ định tính năng | 5/5 | — |
| LP05 | ✅ Hai câu hỏi một lượt | 3/3 | — |
| LP06 | ✅ Lạc đề rồi quay lại | 5/5 | — |
| LP07 | ✅ Bắt đầu lại | 7/7 | — |
| LP08 | ✅ Không dấu, viết tắt | 3/3 | — |
| LP09 | ✅ So sánh xe lạ | 2/2 | — |
| LP10 | ✅ Trả lời bằng số | 5/5 | — |
| LP11 | ✅ Lái thử từ đầu | 4/4 | — |
| LP12 | ✅ Tên xe trùng | 3/3 | — |
| LP13 | ✅ Injection | 2/2 | — |
| LP14 | ✅ Chi phí trước pitch | 3/3 | — |
| LP15 | ✅ Mâu thuẫn ngân sách | 5/5 | — |
| LP16 | ✅ Hỏi lại điều đã nói | 6/6 | — |
| LP17 | ✅ Prod: gia đình 800tr một câu | 1/1 | — |
| LP18 | ✅ Prod: 300tr 5 người | 5/5 | — |
| LP19 | ✅ Prod: 2 tỉ | 4/4 | — |
| LP20 | ✅ Prod: chọn xe sau đề xuất | 2/2 | — |
| LP21 | ✅ Prod: token khung giờ lọt | 1/1 | — |
| LP22 | ✅ Prod: blocklist false positive | 1/1 | — |
| LP23 | ✅ Prod: Ô tô điện rồi nhỏ gọn | 3/3 | — |
| LP24 | ✅ Prod: VF9 rồi giá rồi lăn bánh | 3/3 | — |
| LP25 | ✅ Prod: gặp tư vấn viên | 1/1 | — |
| LP26 | ✅ Chen ngang câu hỏi tỉnh bằng câu giá — quay lại hỏi tỉnh | 3/3 | — |
| LP27 | ✅ Chen ngang câu 'mẫu nào' của giá lăn bánh bằng câu chính sách | 3/3 | — |
| LP28 | ✅ Đang xem VF 5 rồi xin tính giá lăn bánh — không hỏi lại mẫu | 3/3 | — |
| LP29 | ✅ So sánh thiếu xe, khách hỏi chen thông số — quay lại hỏi so sánh | 3/3 | — |
| LP30 | ✅ Câu hỏi lại của việc công cụ không lộ tên slot kỹ thuật | 3/3 | — |
| LP31 | ✅ Đi làm trong phố → đề xuất liên hệ tính năng với nhu cầu phố | 5/5 | — |
| LP32 | ✅ Chở gia đình → đề xuất nêu tính năng cho gia đình | 2/2 | — |
| LP33 | ✅ Chi tiết xe in đủ trang bị theo nhóm + liên hệ nhu cầu đã kể | 2/2 | — |
| LP34 | ✅ 'anh đang quan tâm vf8' → trả thông tin VF 8, không hỏi ngân sách | 3/3 | — |
| LP35 | ✅ Chọn mẫu xong xin tính giá lăn bánh — phải tính, không hỏi lại mẫu | 5/5 | — |

## Lượt đỏ — chi tiết

