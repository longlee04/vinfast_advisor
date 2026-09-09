"""Seed policy chunks into policy_chunks table for hybrid search."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.agents.adapters.embedding import OpenAIEmbeddingAdapter
from src.agents.models import PolicyChunkRow

POLICIES = [
    {
        "source_file": "Chinh_sach_bao_hanh_VinFast_2026.pdf",
        "effective_month": "2026-08",
        "policy_category": "WARRANTY",
        "chunk_text": (
            "Chính sách bảo hành xe ô tô điện VinFast chính hãng: "
            "Các dòng xe ô tô điện VinFast (VF e34, VF 5, VF 6, VF 7, VF 8, VF 9) được bảo hành chính hãng từ 7 năm đến 10 năm hoặc 160.000 km đến 200.000 km (tùy điều kiện nào đến trước). "
            "Pin cao áp của ô tô điện VinFast được bảo hành từ 8 năm đến 10 năm không giới hạn số km đối với khách hàng mua pin. "
            "Dịch vụ cứu hộ 24/7 hoàn toàn miễn phí trong suốt thời gian xe còn hạn bảo hành trên toàn quốc. "
            "Dịch vụ sửa chữa lưu động Mobile Service và Sạc pin lưu động Mobile Charging sẵn sàng phục vụ khách hàng mọi lúc, mọi nơi."
        ),
    },
    {
        "source_file": "Chinh_sach_bao_hanh_xe_may_dien_VinFast.pdf",
        "effective_month": "2026-08",
        "policy_category": "WARRANTY",
        "chunk_text": (
            "Chính sách bảo hành xe máy điện VinFast: "
            "Tất cả các dòng xe máy điện VinFast (Evo 200, Feliz S, Klara S, Vento S, Theon S, Vero X, Viper) được bảo hành tiêu chuẩn từ 3 năm đến 5 năm hoặc 30.000 km đến 50.000 km (tùy điều kiện nào đến trước). "
            "Pin LFP trên xe máy điện được bảo hành chính hãng đổi mới nếu dung lượng tối đa giảm dưới 70%. "
            "Hỗ trợ cứu hộ xe máy điện miễn phí 24/7 trong thời gian bảo hành qua tổng đài chăm sóc khách hàng VinFast 1900 23 23 89."
        ),
    },
    {
        "source_file": "Quy_dinh_Voucher_Song_Xanh_Vingroup.pdf",
        "effective_month": "2026-08",
        "policy_category": "VOUCHER",
        "chunk_text": (
            "Voucher Sống Xanh là chương trình ưu đãi đặc quyền do Tập đoàn Vingroup và VinFast phát hành nhằm khuyến khích cộng đồng chuyển đổi sang phương tiện di chuyển thuần điện. "
            "Mệnh giá Voucher Sống Xanh thông thường gồm các mức: 30 triệu đồng, 50 triệu đồng, 80 triệu đồng, và voucher đặc biệt 100 triệu đến 250 triệu đồng dành cho các dòng xe cao cấp như VF 8, VF 9. "
            "Voucher Sống Xanh được sử dụng để trừ trực tiếp vào giá trị thanh toán khi ký hợp đồng mua xe ô tô điện VinFast mới tại các showroom và đại lý ủy quyền chính thức. "
            "Lưu ý: Mỗi hợp đồng mua xe chỉ được áp dụng số lượng voucher theo đúng quy định của từng chương trình bán hàng cụ thể và voucher phải còn thời hạn hiệu lực, chưa từng được kích hoạt sử dụng trước đó."
        ),
    },
    {
        "source_file": "Chinh_sach_thu_cu_doi_moi_VinFast_2026.pdf",
        "effective_month": "2026-08",
        "policy_category": "TRADE_IN",
        "chunk_text": (
            "Chương trình Thu cũ đổi mới - Chuyển đổi Xanh cùng VinFast: "
            "VinFast hỗ trợ thu mua xe ô tô chạy xăng cũ của tất cả các thương hiệu trên thị trường theo giá thị trường minh bạch và định giá nhanh chóng để đổi sang ô tô điện VinFast mới. "
            "Đặc biệt đối với khách hàng đang sở hữu xe xăng VinFast (Fadil, Lux A2.0, Lux SA2.0, President), khi chuyển đổi sang ô tô điện VinFast sẽ được tặng thêm Voucher tri ấn chuyển đổi xanh trị giá từ 30 triệu đến 80 triệu đồng tùy dòng xe cũ. "
            "Khách hàng được hỗ trợ thủ tục sang tên, bù trừ trực tiếp tiền bán xe cũ vào chi phí mua xe mới một cách tiện lợi và nhanh chóng."
        ),
    },
    {
        "source_file": "Chinh_sach_mua_xe_0_dong_va_tra_gop.pdf",
        "effective_month": "2026-08",
        "policy_category": "FINANCING",
        "chunk_text": (
            "Chính sách Mua xe 0 đồng và Gói vay trả góp ưu đãi VinFast: "
            "Khách hàng có thể sở hữu ô tô điện VinFast với gói hỗ trợ tài chính vay vốn lên đến 80% - 100% giá trị xe (Mua xe không cần trả trước với điều kiện thế chấp bổ sung hoặc hồ sơ tín dụng đạt chuẩn). "
            "Thời hạn vay linh hoạt kéo dài đến 8 năm (96 tháng). "
            "Lãi suất được VinFast và các ngân hàng đối tác liên kết hỗ trợ cố định ở mức rất hấp dẫn trong 2 - 3 năm đầu, phần chênh lệch lãi suất thị trường được VinFast chi trả thay cho khách hàng."
        ),
    },
    {
        "source_file": "Chinh_sach_sac_pin_va_tram_sac_VGreen.pdf",
        "effective_month": "2026-08",
        "policy_category": "CHARGING",
        "chunk_text": (
            "Chính sách sạc pin và mạng lưới trạm sạc V-GREEN: "
            "VinFast cùng công ty trạm sạc toàn cầu V-GREEN triển khai mạng lưới trạm sạc phủ khắp 63 tỉnh thành Việt Nam, trên mọi tuyến quốc lộ, cao tốc và đô thị. "
            "Khách hàng sở hữu ô tô điện VinFast được hưởng chính sách miễn phí sạc pin tại hệ thống trạm sạc công cộng V-GREEN theo các chương trình khuyến mại tri ân của từng thời kỳ. "
            "Chi phí sạc pin tiêu chuẩn khi không áp dụng miễn phí là 3.858 VNĐ/kWh (đã bao gồm VAT), rẻ hơn đáng kể so với chi phí đổ xăng cùng quãng đường."
        ),
    },
    {
        "source_file": "Uu_dai_Cong_an_Quan_doi_CBNV.pdf",
        "effective_month": "2026-08",
        "policy_category": "PROMOTION",
        "chunk_text": (
            "Chương trình ưu đãi dành riêng cho lực lượng vũ trang và cán bộ nhân viên: "
            "Cán bộ chiến sĩ Công an, Quân đội nhân dân Việt Nam và thân nhân theo quy định được giảm 5% giá niêm yết MSRP khi mua ô tô điện VinFast. "
            "Cán bộ nhân viên tập đoàn VNPost, giáo viên, y bác sĩ và cán bộ nhân viên thuộc hệ sinh thái Vingroup được hưởng mức chiết khấu ưu đãi từ 3% đến 5% tùy cấp bậc và dòng xe lựa chọn."
        ),
    },
]


async def seed_policies():
    url = (
        os.environ.get("AGENT_DATABASE_URL") or "postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
    )
    engine = create_async_engine(url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    embedding_adapter = OpenAIEmbeddingAdapter(model_name="text-embedding-3-small", dimensions=1536)

    async with session_factory() as session:
        await session.execute(text("DELETE FROM policy_chunks"))

        texts = [p["chunk_text"] for p in POLICIES]
        embeddings = await embedding_adapter.embed(texts)

        for p, emb in zip(POLICIES, embeddings):
            row = PolicyChunkRow(
                chunk_id=uuid4(),
                source_file=p["source_file"],
                source_url="https://vinfastauto.com/vn_vi/chinh-sach-ban-hang",
                effective_month=p["effective_month"],
                policy_category=p["policy_category"],
                chunk_text=p["chunk_text"],
                embedding=emb,
                created_at=datetime.now(UTC),
            )
            session.add(row)

        await session.commit()
        print(f"Successfully seeded {len(POLICIES)} policy chunks into policy_chunks table!")


if __name__ == "__main__":
    asyncio.run(seed_policies())
