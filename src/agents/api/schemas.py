"""[Khối 4] Hình dạng HTTP ổn định cho nhóm endpoint vận hành."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.agents.domain.comparison import ComparisonSource


class PublishNoticeRequest(BaseModel):
    """[A8-4] Admin đăng một thông báo nội bộ."""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    priority: Literal["NORMAL", "URGENT"] = "NORMAL"


class PublishNoticeResponse(BaseModel):
    notice_id: UUID


class NoticeResponse(BaseModel):
    """[A8-4] Một thông báo kèm trạng thái đã đọc của riêng người đang hỏi."""

    notice_id: UUID
    title: str
    content: str
    priority: str
    created_at: datetime
    read: bool


class PendingReviewResponse(BaseModel):
    """Một dòng hàng đợi duyệt gửi cho tư vấn viên."""

    review_id: UUID
    session_id: UUID
    run_id: UUID
    status: str
    content: str
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime


class QueueEntryResponse(BaseModel):
    """[C3] Một dòng hàng đợi cho màn tư vấn viên — kèm hồ sơ khách và cờ vận hành."""

    review_id: UUID
    session_id: UUID
    run_id: UUID
    status: str
    content: str
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    profile_snapshot: dict | None = None
    offer_state: str | None = None
    age_minutes: int | None = None
    handoff_requested: bool = False
    offer_suggestion_ignored: bool = False
    #: [T7b] "spam ×N" — số lần đẩy vượt trần đã gộp vào mục này. Mặc định 0 nên
    #: client cũ không vỡ.
    merged_count: int = 0


class ReviewDetailResponse(BaseModel):
    """Bản nháp đầy đủ kèm ảnh so sánh, dành cho tư vấn viên.

    Hồ sơ khách (`profile_snapshot`) là bằng chứng NỘI BỘ — chỉ ra ở đường staff,
    không bao giờ đi qua cửa gửi khách.
    """

    review_id: UUID
    session_id: UUID
    run_id: UUID
    status: str
    content: str
    edited_content: str | None = None
    comparison_image_base64: str | None = None
    profile_snapshot: dict | None = None
    offer_state: str | None = None
    matched_promotions: list[dict] = Field(default_factory=list)
    adjustment_policies: list[dict] = Field(default_factory=list)


class ClaimReviewResponse(BaseModel):
    """[A7-2] Kết quả nhận một mục trong hàng đợi."""

    granted: bool
    rejection: str | None = None


class ApproveReviewRequest(BaseModel):
    """[A7-3] Duyệt nguyên trạng khi bỏ trống, hoặc sửa văn bản rồi duyệt."""

    edited_content: str | None = None


class OfferAdjustmentRequest(BaseModel):
    """[C3] Một lần cấp/điều chỉnh ưu đãi — biên độ do ADMIN cấu hình kiểm."""

    promotion_code: str | None = None
    promotion_type: str | None = None
    adjustment_type: str | None = None
    amount_vnd: int | None = None
    percent: float | None = None
    months: int | None = None
    gift_code: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None


class ResolveReviewRequest(BaseModel):
    """[C3/C6] Duyệt/từ chối kèm tuỳ chọn cấp ưu đãi và cờ chuyển người thật.

    `offer_adjustment` để trống là hợp lệ (D12): đề xuất ưu đãi là bằng chứng,
    không phải nghĩa vụ.
    """

    status: Literal["APPROVED", "REJECTED"]
    edited_content: str | None = None
    offer_adjustment: OfferAdjustmentRequest | None = None
    handoff_requested: bool = False


class ResolveReviewResponse(BaseModel):
    review_id: UUID


class DeliverContentResponse(BaseModel):
    """[A7-3 / comparison-image] Nội dung được phép gửi khách, kèm ảnh so sánh nếu có."""

    review_id: UUID
    content: str
    comparison_image_base64: str | None = None


class BookTestDriveRequest(BaseModel):
    """[A8-2] Đặt lịch lái thử từ portal hoặc đề xuất đã duyệt."""

    run_id: UUID | None = None
    vehicle_id: UUID
    showroom: str = Field(min_length=1, max_length=255)
    scheduled_at: datetime
    customer_name: str | None = None
    phone: str | None = None
    customer_id: str | None = None


class BookingListItemResponse(BaseModel):
    booking_id: UUID
    customer_id: str
    customer_name: str | None = None
    phone: str | None = None
    vehicle_id: UUID
    vehicle_name: str
    advisor_id: str | None = None
    showroom: str
    scheduled_at: datetime
    status: str
    created_at: datetime


class BookTestDriveResponse(BaseModel):
    booking_id: UUID


class SessionHistoryResponse(BaseModel):
    """[A8-3] Một phiên tư vấn trong lịch sử của khách."""

    session_id: str
    started_at: datetime
    run_count: int
    last_review_status: str | None


class FunnelRowResponse(BaseModel):
    """[A9-1] Một ngày trong phễu tư vấn."""

    day: date
    sessions_started: int
    sessions_with_profile: int
    sessions_with_recommendation: int
    sessions_approved: int
    sessions_booked: int


class CompareRequest(BaseModel):
    """Yêu cầu so sánh hai hoặc ba mẫu từ snapshot của run."""

    run_id: UUID
    vehicle_ids: list[UUID] = Field(min_length=2, max_length=3)


class TcoEstimateRequest(BaseModel):
    """Khách tự chỉnh giả định ngay trên thẻ chi phí, không cần gõ vào khung chat.

    Sếp 2026-08-27: *"phải có ô hay điền gì đó hoặc kéo số km còn tỉnh thành để
    cho người ta chọn chứ không cần phải chat rồi cập nhật lại"*.

    Hai trường vì đúng hai thứ có thể sai trong một ước tính: quãng đường mỗi
    ngày, và khu vực đăng ký. Khu vực là chỗ sai đắt nhất — lệ phí biển ô tô là
    140.000đ ở Khu vực II và 14.000.000đ ở Hà Nội/TP.HCM, chênh 100 lần.
    """

    vehicle_id: UUID
    #: Trần 1000 km/ngày là mốc VÔ LÝ, không phải mốc sản phẩm: nó chặn giá trị
    #: hỏng từ client chứ không phán xét thói quen đi lại của khách.
    daily_distance_km: float = Field(ge=0, le=1000)
    #: Mã tỉnh (`domain/pricing_intent.PROVINCES`). `None` = chưa biết, và phép
    #: tính rơi về Khu vực II — đúng hành vi đang chạy khi khách chưa nói tỉnh.
    province_code: str | None = None
    #: Phiên hội thoại, để ghi lại lựa chọn của khách. Thiếu thì vẫn tính được,
    #: chỉ là lượt chat sau không biết khách vừa chỉnh gì.
    session_id: str | None = None


class TcoComponentResponse(BaseModel):
    """Một khoản trong bảng chi phí, kèm nhãn tiếng Việt sẵn để client khỏi tự dịch."""

    code: str
    label: str
    amount_vnd: str
    #: "rolling" (lăn bánh ban đầu) / "operating" (vận hành 5 năm) / "" (chỗ dựng
    #: cũ chưa gán nhóm) — client chia hai nhóm trên thẻ, rỗng thì bảng phẳng như cũ.
    group: str = ""


class TcoEstimateResponse(BaseModel):
    """Bảng chi phí 5 năm đã tính lại theo giả định khách vừa chỉnh.

    Số gửi dạng CHUỖI, không phải float: đây là tiền, và `Decimal` đi qua JSON
    float là chỗ mất chính xác âm thầm.
    """

    vehicle_id: UUID
    total_vnd: str | None
    components: list[TcoComponentResponse]
    daily_distance_km: float
    province_code: str | None
    region_code: str
    #: Câu nói ra phép tính này đứng trên giả định nào — bắt buộc, cùng lý do với
    #: `chain._assumption_note`: một ước tính không nói mình ước tính theo gì thì
    #: khách không có cách nào biết nó sai ở đâu để sửa.
    assumption_note: str
    unavailable_reason: str | None = None


class ProvinceOptionResponse(BaseModel):
    """Một tỉnh thành khách chọn được trên thẻ chi phí."""

    code: str
    name: str
    region_code: str


class ComparisonCellResponse(BaseModel):
    """Một ô trong hàng so sánh snapshot."""

    vehicle_id: UUID
    value_text: str | None
    source: ComparisonSource | None
    evidence_ref: str | None
    label: str | None
    is_better: bool


class ComparisonRowResponse(BaseModel):
    """Một tiêu chí so sánh và các giá trị theo xe."""

    criterion_code: str
    cells: list[ComparisonCellResponse]


class ComparisonTableResponse(BaseModel):
    """Bảng so sánh dựng từ snapshot bất biến của một run."""

    captured_at: datetime | None
    vehicle_ids: list[UUID]
    rows: list[ComparisonRowResponse]
