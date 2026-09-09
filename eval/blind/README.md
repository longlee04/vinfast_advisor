# Blind set — đề thi bot CHƯA TỪNG THẤY

Mục đích: đo năng lực thật trên câu hỏi lạ, khác bộ 86 case (bộ đó là lưới
chống tái phát — viết từ lỗi đã sửa nên pass cao là đương nhiên).

## Luật niêm phong (quan trọng hơn mọi dòng code ở đây)

1. Case do người KHÔNG build hệ thống viết (Sếp, Ngọc, bạn bè). AI/dev
   KHÔNG được đọc nội dung case trước lần chạy đầu.
2. File đề thật đặt tại `eval/blind/blind_cases.json` — file này nằm trong
   `.gitignore` nếu muốn giữ kín, hoặc chỉ thêm vào repo SAU lần chạy đầu.
3. Con số báo cáo là pass/điểm của **LẦN CHẠY ĐẦU TIÊN, trước mọi lần sửa
   code theo đề**. Sửa xong chạy lại thì ghi thành cột thứ hai, không đè.
4. Đề đã lộ (đã dùng để sửa code) thì chuyển sang bộ regression, viết đề mới.

## Cách viết case

Chép `blind_cases.template.json` thành `blind_cases.json` rồi điền. Mỗi case:

- `id`: mã ngắn (BL-01…).
- `persona`: một dòng bối cảnh người hỏi (để người chấm hiểu ý đồ).
- `turns`: danh sách CÂU KHÁCH GÕ, đúng văn phong thật (typo, tiếng lóng,
  đổi ý giữa chừng đều quý).
- `muc_tieu`: khách coi là XONG VIỆC khi nào — người/LLM chấm dựa vào đây.

KHÔNG cần viết "expect" máy móc — blind set chấm bằng rubric, không chấm
bằng khớp chuỗi.

## Chạy

```bash
# 1. Bắn đề vào prod (trong container backend trên VPS, hoặc qua tunnel):
python scripts/blind_run.py --base http://127.0.0.1:8000/api/v1 \
  --cases eval/blind/blind_cases.json --out eval/blind/runs

# 2. Chấm rubric (cần OPENAI_API_KEY trong env):
python scripts/rubric_judge.py --transcripts eval/blind/runs/<ts>/transcripts.json

# Chấm luôn hội thoại THẬT của khách (chạy trong container backend, có DATABASE_URL):
python scripts/rubric_judge.py --from-db --days 7 --limit 50
```

Rubric 4 tiêu chí mỗi lượt bot: **đúng ý / đúng bước / đúng giọng** (LLM chấm)
và **đúng số** (LLM chỉ LIỆT KÊ các con số để NGƯỜI đối chiếu catalog — LLM
không có catalog nên không được phán đúng/sai số). Kết quả kèm file chi tiết,
người soát tối thiểu 20% trước khi tin con số.
