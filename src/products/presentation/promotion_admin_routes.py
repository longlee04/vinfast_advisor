"""HTTP `/admin/promotions` — quản trị ưu đãi cho Admin (plan Customer 360 Phase 5C).

Chỉ ADMIN (`routes._is_admin`, cùng cơ chế các route `/admin/vehicles`). Hiệu quả ưu đãi
(đề xuất → gửi → chốt) nằm ở `/admin/promotion-stats` của module agents, nơi có vòng đời.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.products.application.promotion_admin_service import PromotionAdminError, PromotionAdminService
from src.products.domain.eligibility_rules import FIELD_QUESTION_HINTS, FIELD_TYPES, validate_rules
from src.products.presentation.routes import _current_user, _is_admin

router = APIRouter(prefix="/admin/promotions", tags=["admin-promotions"])

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


async def _admin(request: Request) -> str:
    if not await _is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ Admin được quản trị ưu đãi")
    user = await _current_user(request)
    return str(getattr(user, "id", "admin"))


def _error(error: PromotionAdminError) -> HTTPException:
    codes = {"NOT_FOUND": status.HTTP_404_NOT_FOUND, "DUPLICATE_CODE": status.HTTP_409_CONFLICT}
    return HTTPException(
        status_code=codes.get(error.code, status.HTTP_422_UNPROCESSABLE_CONTENT),
        detail={"code": error.code, "errors": list(error.errors)},
    )


@router.get("")
async def list_promotions(request: Request, status_filter: str | None = None) -> list[dict[str, Any]]:
    await _admin(request)
    return await _service(request).list(status_filter)


@router.get("/rule-schema")
async def rule_schema(request: Request) -> dict[str, Any]:
    """Field + toán tử hợp lệ cho bộ dựng luật — một nguồn với bộ đánh giá."""
    await _admin(request)
    return {
        "fields": FIELD_TYPES,
        "operators": ["eq", "in", "gte", "lte", "exists"],
        "question_hints": FIELD_QUESTION_HINTS,
    }


@router.post("/validate-rules")
async def validate(payload: RulesIn, request: Request) -> dict[str, Any]:
    await _admin(request)
    errors = validate_rules(payload.rules)
    return {"ok": not errors, "errors": errors}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_promotion(payload: PromotionIn, request: Request) -> dict[str, Any]:
    """Ưu đãi mới luôn ở trạng thái UNVERIFIED cho tới khi Admin kích hoạt."""
    actor = await _admin(request)
    try:
        return await _service(request).create(payload.model_dump(exclude_none=True), actor)
    except PromotionAdminError as error:
        raise _error(error) from error


@router.patch("/{promotion_id}")
async def update_promotion(promotion_id: str, payload: PromotionIn, request: Request) -> dict[str, Any]:
    actor = await _admin(request)
    try:
        return await _service(request).update(promotion_id, payload.model_dump(exclude_unset=True), actor)
    except PromotionAdminError as error:
        raise _error(error) from error


@router.post("/{promotion_id}/activate")
async def activate_promotion(promotion_id: str, request: Request) -> dict[str, Any]:
    """UNVERIFIED/DRAFT → ACTIVE — chỉ khi luật hợp lệ và còn hạn."""
    actor = await _admin(request)
    try:
        return await _service(request).activate(promotion_id, actor)
    except PromotionAdminError as error:
        raise _error(error) from error


@router.delete("/{promotion_id}")
async def cancel_promotion(promotion_id: str, request: Request) -> dict[str, Any]:
    actor = await _admin(request)
    try:
        return await _service(request).cancel(promotion_id, actor)
    except PromotionAdminError as error:
        raise _error(error) from error


__all__ = ["router"]
