"""HTTP `/advisor/promotions` — tư vấn viên quản lý chương trình ưu đãi (plan Customer 360 §16).

Admin chỉ lo kỹ thuật; tư vấn viên chịu trách nhiệm với khách nên toàn quyền tạo/sửa/bật tắt
chương trình, dựng luật đối tượng, đặt hạn mức tự cấp. Ưu đãi vượt hạn mức do một tư vấn viên
KHÁC duyệt (`/advisor/opportunity-offers/{id}/approve` của module agents). Hiệu quả ưu đãi
(đề xuất → gửi → chốt) nằm ở `/advisor/promotion-stats`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.auth.domain.authorization import Role
from src.products.application.promotion_admin_service import PromotionAdminError, PromotionAdminService
from src.products.domain.eligibility_rules import FIELD_QUESTION_HINTS, FIELD_TYPES, validate_rules
from src.products.presentation.routes import _current_user

router = APIRouter(prefix="/advisor/promotions", tags=["advisor-promotions"])

PromotionTypeLiteral = Literal[
    "FIXED_DISCOUNT", "PERCENT_DISCOUNT", "GIFT", "FINANCING", "REGISTRATION_SUPPORT", "OTHER"
]


class PromotionIn(BaseModel):
    promotion_code: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    promotion_type: PromotionTypeLiteral | None = None
    discount_amount_vnd: int | None = Field(default=None, ge=0)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    eligibility_rules: dict[str, Any] | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    gift_group: str | None = Field(default=None, max_length=50)
    stackable: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    max_uses: int | None = Field(default=None, gt=0)
    requires_advisor_approval: bool | None = None
    advisor_max_discount_vnd: int | None = Field(default=None, ge=0)
    status: Literal["DRAFT", "UNVERIFIED", "EXPIRED", "CANCELLED"] | None = None


class RulesIn(BaseModel):
    rules: dict[str, Any]


def _service(request: Request) -> PromotionAdminService:
    resources = getattr(request.app.state, "product", None)
    service = getattr(getattr(resources, "resources", resources), "promotion_admin_service", None)
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Promotion admin unavailable")
    return service


async def _advisor(request: Request) -> str:
    """Chỉ tư vấn viên đang hoạt động — Admin (kỹ thuật) không quản lý ưu đãi nữa."""

    user = await _current_user(request)
    if user is None or user.role is not Role.ADVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ tư vấn viên được quản lý ưu đãi")
    return str(getattr(user, "id", "advisor"))


def _error(error: PromotionAdminError) -> HTTPException:
    codes = {"NOT_FOUND": status.HTTP_404_NOT_FOUND, "DUPLICATE_CODE": status.HTTP_409_CONFLICT}
    return HTTPException(
        status_code=codes.get(error.code, status.HTTP_422_UNPROCESSABLE_CONTENT),
        detail={"code": error.code, "errors": list(error.errors)},
    )


@router.get("")
async def list_promotions(request: Request, status_filter: str | None = None) -> list[dict[str, Any]]:
    await _advisor(request)
    return await _service(request).list(status_filter)


@router.get("/rule-schema")
async def rule_schema(request: Request) -> dict[str, Any]:
    """Field + toán tử hợp lệ cho bộ dựng luật — một nguồn với bộ đánh giá."""
    await _advisor(request)
    return {
        "fields": FIELD_TYPES,
        "operators": ["eq", "in", "gte", "lte", "exists"],
        "question_hints": FIELD_QUESTION_HINTS,
    }


@router.post("/validate-rules")
async def validate(payload: RulesIn, request: Request) -> dict[str, Any]:
    await _advisor(request)
    errors = validate_rules(payload.rules)
    return {"ok": not errors, "errors": errors}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_promotion(payload: PromotionIn, request: Request) -> dict[str, Any]:
    """Ưu đãi mới luôn ở trạng thái UNVERIFIED cho tới khi Admin kích hoạt."""
    actor = await _advisor(request)
    try:
        return await _service(request).create(payload.model_dump(exclude_none=True), actor)
    except PromotionAdminError as error:
        raise _error(error) from error


@router.patch("/{promotion_id}")
async def update_promotion(promotion_id: str, payload: PromotionIn, request: Request) -> dict[str, Any]:
    actor = await _advisor(request)
    try:
        return await _service(request).update(promotion_id, payload.model_dump(exclude_unset=True), actor)
    except PromotionAdminError as error:
        raise _error(error) from error


@router.post("/{promotion_id}/activate")
async def activate_promotion(promotion_id: str, request: Request) -> dict[str, Any]:
    """UNVERIFIED/DRAFT → ACTIVE — chỉ khi luật hợp lệ và còn hạn."""
    actor = await _advisor(request)
    try:
        return await _service(request).activate(promotion_id, actor)
    except PromotionAdminError as error:
        raise _error(error) from error


@router.delete("/{promotion_id}")
async def cancel_promotion(promotion_id: str, request: Request) -> dict[str, Any]:
    actor = await _advisor(request)
    try:
        return await _service(request).cancel(promotion_id, actor)
    except PromotionAdminError as error:
        raise _error(error) from error


__all__ = ["router"]
