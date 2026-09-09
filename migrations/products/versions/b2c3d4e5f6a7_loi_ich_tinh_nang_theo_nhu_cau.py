"""Câu lợi ích tính năng theo nhu cầu — dữ liệu cho `agents/domain/feature_fit`.

Revision ID: b2c3d4e5f6a7
Revises: e6f7a8b9c0d1
Create Date: 2026-08-29

Sếp 2026-08-29: bot phải liên hệ tính năng xe với nhu cầu khách, và lời liên hệ
phải là DỮ LIỆU đã duyệt chứ không phải LLM tự nghĩ. Bảng `feature_need_tags`
có sẵn cột `note` nhưng mới phủ 34 cặp, lời còn kỹ thuật. Migration này ghi
64 cặp (tính năng × nhu cầu) với câu lợi ích viết cho khách; cặp đã có thì
cập nhật `note`/`relevance`, cặp mới thì thêm. Cùng nội dung với
`data-p150/catalog/feature_need_tags.csv` để môi trường seed mới không lệch.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS: tuple[tuple[str, str, str, str], ...] = (
    (
        "COMPACT_SIZE",
        "URBAN_TRAFFIC",
        "1.00",
        "thân xe gọn và bán kính quay đầu nhỏ nên len phố đông và đỗ ở chỗ hẹp dễ hơn",
    ),
    (
        "CAMERA_360",
        "URBAN_TRAFFIC",
        "0.90",
        "camera toàn cảnh cho thấy hết vật cản quanh xe khi ra vào bãi đỗ hay đi ngõ hẹp",
    ),
    (
        "BLIND_SPOT_MONITOR",
        "URBAN_TRAFFIC",
        "0.80",
        "chuyển làn giữa dòng xe máy đông có cảnh báo điểm mù nên đỡ giật mình",
    ),
    ("ECO_MODE", "URBAN_TRAFFIC", "0.70", "đi phố tốc độ thấp bật chế độ Eco tiết kiệm điện mà vẫn đủ lực"),
    (
        "SMARTPHONE_MIRRORING",
        "URBAN_TRAFFIC",
        "0.60",
        "bản đồ điện thoại hiện lên màn hình xe nên tìm đường trong phố không phải cầm máy",
    ),
    ("FAST_CHARGING", "URBAN_TRAFFIC", "0.60", "ghé trụ sạc nhanh lúc đi làm là đủ pin cho vài ngày trong phố"),
    ("MULTI_ZONE_AC", "URBAN_TRAFFIC", "0.50", "kẹt xe lâu vẫn mát đều từng vị trí mà không tốn nhiều điện"),
    (
        "ADAS_SUITE",
        "URBAN_TRAFFIC",
        "0.60",
        "phanh khẩn cấp và cảnh báo va chạm hỗ trợ khi xe phía trước dừng đột ngột trong phố",
    ),
    (
        "ANTI_THEFT",
        "URBAN_TRAFFIC",
        "0.50",
        "đỗ xe ngoài đường hay bãi công cộng có chống trộm báo động nên yên tâm hơn",
    ),
    ("MOBILE_APP", "URBAN_TRAFFIC", "0.50", "xem pin còn bao nhiêu và tìm xe trong bãi ngay trên điện thoại"),
    ("GPS", "URBAN_TRAFFIC", "0.40", "định vị xe giúp tìm lại chỗ đỗ khi gửi xe ở bãi lớn"),
    ("7_SEATER", "FAMILY_TRIP", "1.00", "ba hàng ghế đủ chỗ cho cả nhà và ông bà đi cùng"),
    (
        "ISOFIX_ANCHORS",
        "FAMILY_TRIP",
        "1.00",
        "ghế trẻ em gắn chắc vào móc ISOFIX nên các bé ngồi an toàn suốt chuyến đi",
    ),
    ("MULTI_ZONE_AC", "FAMILY_TRIP", "0.80", "người lớn và trẻ nhỏ mỗi hàng ghế chọn được nhiệt độ riêng"),
    ("POWER_TAILGATE", "FAMILY_TRIP", "0.70", "tay bế con hay xách đồ vẫn mở cốp được bằng một nút bấm"),
    (
        "PANORAMIC_ROOF",
        "FAMILY_TRIP",
        "0.60",
        "nóc kính toàn cảnh cho các bé ngắm trời và khoang xe thoáng hơn khi đi chơi xa",
    ),
    ("ADAS_SUITE", "FAMILY_TRIP", "0.80", "giữ làn và phanh khẩn cấp hỗ trợ người lái khi chở cả gia đình"),
    ("CAMERA_360", "FAMILY_TRIP", "0.60", "lùi xe ở khu vui chơi hay bãi đỗ đông trẻ nhỏ có camera toàn cảnh quan sát"),
    ("BLIND_SPOT_MONITOR", "FAMILY_TRIP", "0.60", "xe dài chở nhiều người có cảnh báo điểm mù khi chuyển làn"),
    ("LEATHER_SEATS", "FAMILY_TRIP", "0.50", "trẻ làm đổ đồ ăn lau ghế da là sạch"),
    (
        "HIGH_RANGE_BATTERY",
        "FAMILY_TRIP",
        "0.70",
        "pin dung lượng lớn đủ cho chuyến đi chơi cả ngày mà không phải dừng sạc",
    ),
    ("HIGH_RANGE_BATTERY", "LONG_RANGE", "1.00", "pin quãng đường lớn đi tỉnh một mạch đỡ phải tìm trạm dọc đường"),
    ("FAST_CHARGING", "LONG_RANGE", "0.90", "ghé trạm sạc nhanh khoảng nửa tiếng là đủ pin chạy tiếp chặng dài"),
    ("ADAS_SUITE", "LONG_RANGE", "0.90", "kiểm soát hành trình thích ứng và giữ làn đỡ mỏi khi chạy cao tốc lâu"),
    ("BLIND_SPOT_MONITOR", "LONG_RANGE", "0.70", "chuyển làn trên cao tốc có cảnh báo điểm mù an tâm hơn"),
    ("HEAD_UP_DISPLAY", "LONG_RANGE", "0.60", "tốc độ và chỉ dẫn hiện ngay trên kính lái nên mắt không rời mặt đường"),
    (
        "POWER_DRIVER_SEAT",
        "LONG_RANGE",
        "0.60",
        "chỉnh ghế điện nhiều hướng tìm được tư thế thoải mái cho chặng đường dài",
    ),
    ("VENTILATED_SEATS", "LONG_RANGE", "0.60", "ghế thông gió đỡ nóng lưng khi ngồi lái nhiều giờ liền"),
    ("MOBILE_APP", "LONG_RANGE", "0.50", "theo dõi pin và lên kế hoạch điểm sạc cho cả hành trình trên điện thoại"),
    ("ESIM", "LONG_RANGE", "0.40", "xe có kết nối dữ liệu riêng nên dẫn đường và cập nhật vẫn chạy khi đi xa"),
    ("TOWING", "LONG_RANGE", "0.40", "kéo được rơ-moóc nhỏ mang thêm đồ cho chuyến đi xa"),
    ("HIGH_PAYLOAD", "DELIVERY_LOAD", "1.00", "tải trọng lớn chở được nhiều hàng mỗi chuyến"),
    ("TOWING", "DELIVERY_LOAD", "0.60", "kéo thêm rơ-moóc khi hàng cồng kềnh"),
    ("BATTERY_SWAPPABLE", "DELIVERY_LOAD", "0.70", "đổi pin vài phút là chạy tiếp không đứt ca chở hàng"),
    (
        "BATTERY_SWAPPABLE",
        "DELIVERY_USE",
        "1.00",
        "đổi pin tại trạm trong vài phút nên chạy giao hàng liên tục cả ngày",
    ),
    ("BATTERY_REMOVABLE", "DELIVERY_USE", "0.80", "tháo pin mang theo pin dự phòng đổi giữa ca giao hàng"),
    ("ANTI_THEFT", "DELIVERY_USE", "0.70", "dừng đỗ nhiều điểm trong ngày có chống trộm báo động"),
    ("GPS", "DELIVERY_USE", "0.70", "định vị xe theo dõi lộ trình giao hàng và tìm xe khi cần"),
    ("MOBILE_APP", "DELIVERY_USE", "0.60", "xem pin và trạng thái xe trên điện thoại để sắp xếp ca chạy"),
    ("ECO_MODE", "DELIVERY_USE", "0.60", "chạy Eco kéo dài quãng đường mỗi lần sạc khi giao hàng cả ngày"),
    ("HIGH_PAYLOAD", "DELIVERY_USE", "0.70", "chở được nhiều hàng hơn mỗi chuyến"),
    ("ECO_MODE", "ECO_SAVING", "1.00", "chế độ Eco giảm điện tiêu thụ nên chi phí mỗi km thấp hơn"),
    ("AUTO_SHUTOFF_CHARGER", "ECO_SAVING", "0.80", "sạc tự ngắt khi đầy giúp bảo vệ pin và không tốn điện thừa"),
    ("BATTERY_REMOVABLE", "ECO_SAVING", "0.60", "tháo pin sạc bằng điện nhà rẻ hơn sạc ngoài trạm"),
    ("MOBILE_APP", "ECO_SAVING", "0.50", "theo dõi mức tiêu thụ điện trên ứng dụng để chạy tiết kiệm hơn"),
    ("COMPACT_SIZE", "ECO_SAVING", "0.50", "xe nhỏ nhẹ nên tốn ít điện hơn mỗi km"),
    ("BATTERY_REMOVABLE", "NO_HOME_CHARGING", "1.00", "tháo pin mang lên nhà sạc khi chỗ để xe không có ổ cắm"),
    ("BATTERY_SWAPPABLE", "NO_HOME_CHARGING", "0.90", "đổi pin tại trạm thay cho việc sạc ở nhà"),
    (
        "FAST_CHARGING",
        "NO_HOME_CHARGING",
        "0.90",
        "không sạc được ở nhà thì ghé trụ sạc nhanh khoảng nửa tiếng là đầy phần lớn pin",
    ),
    ("MOBILE_APP", "NO_HOME_CHARGING", "0.60", "tìm trạm sạc gần và xem trạng thái sạc trên điện thoại"),
    ("VENTILATED_SEATS", "PREMIUM_COMFORT", "0.90", "ghế thông gió và sưởi mát mùa hè ấm mùa đông"),
    ("PANORAMIC_ROOF", "PREMIUM_COMFORT", "1.00", "nóc kính toàn cảnh cho khoang xe sáng và sang hơn"),
    ("ADAS_SUITE", "PREMIUM_COMFORT", "0.90", "gói hỗ trợ lái nâng cao ADAS là trang bị của phân khúc cao cấp"),
    ("MULTI_ZONE_AC", "PREMIUM_COMFORT", "0.80", "điều hòa chia vùng cho mỗi vị trí ngồi tự chọn nhiệt độ"),
    ("LEATHER_SEATS", "PREMIUM_COMFORT", "0.70", "nội thất bọc da cho cảm giác sang trọng và dễ vệ sinh"),
    ("POWER_DRIVER_SEAT", "PREMIUM_COMFORT", "0.70", "ghế lái chỉnh điện nhớ vị trí ngồi"),
    ("HEAD_UP_DISPLAY", "PREMIUM_COMFORT", "0.70", "màn hình hiển thị trên kính lái là công nghệ của xe hạng sang"),
    ("WIRELESS_CHARGING", "PREMIUM_COMFORT", "0.70", "sạc điện thoại không dây khoang lái gọn không vướng cáp"),
    ("POWER_TAILGATE", "PREMIUM_COMFORT", "0.70", "cốp sau đóng mở bằng điện"),
    ("CAMERA_360", "PREMIUM_COMFORT", "0.60", "camera toàn cảnh 360 độ thuộc nhóm trang bị cao cấp"),
    (
        "SMARTPHONE_MIRRORING",
        "PREMIUM_COMFORT",
        "0.50",
        "Apple CarPlay và Android Auto đưa ứng dụng quen thuộc lên màn hình xe",
    ),
    ("ESIM", "PREMIUM_COMFORT", "0.40", "xe có eSIM kết nối dữ liệu sẵn cho các dịch vụ trực tuyến"),
    ("BLUETOOTH", "URBAN_TRAFFIC", "0.30", "nghe gọi rảnh tay qua Bluetooth khi đi trong phố"),
    ("BLUETOOTH", "LONG_RANGE", "0.30", "nghe nhạc và gọi điện rảnh tay suốt chặng đường dài"),
)


def upgrade() -> None:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    bind = op.get_bind()
    known = {row[0] for row in bind.execute(sa.text("SELECT feature_code FROM feature_definitions")).all()}
    for feature_code, need_tag, relevance, note in ROWS:
        if feature_code not in known:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO feature_need_tags
                    (feature_code, need_tag, relevance, note, created_by, created_at, updated_at)
                VALUES (:feature_code, :need_tag, :relevance, :note, 'feature_fit', :now, :now)
                ON CONFLICT (feature_code, need_tag) DO UPDATE
                    SET note = EXCLUDED.note,
                        relevance = EXCLUDED.relevance,
                        updated_at = EXCLUDED.updated_at
                """
            ),
            {"feature_code": feature_code, "need_tag": need_tag, "relevance": relevance, "note": note, "now": now},
        )


def downgrade() -> None:
    """Chỉ gỡ cặp do migration này thêm; cặp cũ giữ note mới (không khôi phục lời cũ)."""

    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM feature_need_tags WHERE created_by = 'feature_fit'"))
