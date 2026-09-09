"""FastAPI routes cho Vehicle Catalog (Refactored schema)."""

from __future__ import annotations

import math
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request, status

from src.auth.domain.accounts import User
from src.auth.domain.authorization import Role
from src.products.application import PageParams
from src.products.application.feature_flag_service import FeatureFlagService
from src.products.application.offer_policy_service import OfferPolicyService
from src.products.application.tco_service import TcoUnavailableError
from src.products.application.vehicle_service import VehicleCatalogService
from src.products.domain.errors import ProductNotFoundError, ProductPermissionError
from src.products.domain.offer_policy import (
    AdjustmentOutOfBoundsError,
    OfferAdjustmentPolicy,
)
from src.products.domain.tco import resolve_region_code
from src.products.domain.values import PromotionType, VehicleType
from src.products.presentation import (
    BatteryPolicyOut,
    FeatureFlagOut,
    FeatureFlagReview,
    FeatureFlagUpdate,
    MetaOut,
    OfferAdjustmentPolicyIn,
    OfferAdjustmentPolicyOut,
    PaginationOut,
    PromotionLinkOut,
    StandardListResponse,
    StandardSuccessResponse,
    TcoAssumptionsOut,
    TcoBreakdownOut,
    TcoConsumptionOut,
    TcoOut,
    VehicleCreate,
    VehicleDetailOut,
    VehicleFeatureFlagOut,
    VehiclePriceIn,
    VehiclePriceOut,
    VehiclePriceUpdate,
    VehicleSpecsUpdate,
    VehicleSummaryOut,
    VehicleUpdate,
)

router = APIRouter(prefix="", tags=["vehicles"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _current_user(request: Request) -> User | None:
    """Resolve the authenticated user from the access-token cookie.

    Role is not embedded in the JWT — only `sub` (user id), `sid` (session id),
    `exp`, `iss`, and `aud` are signed (`src/auth/infrastructure/security.py:34`).
    To know whether the caller is an admin we have to look the account up
    through `customer.me`, which also re-validates the session is live.
    """
    access_token = request.cookies.get("__Host-p150_access")
    if not access_token:
        return None
    auth = getattr(request.app.state, "auth", None)
    if auth is None or getattr(auth, "resources", None) is None:
        return None
    services = auth.resources.services
    try:
        return await services.customer.me(access_token)
    except Exception:
        return None


async def _is_admin(request: Request) -> bool:
    """Return True only when the caller is an active ADMIN.

    Compares against the `Role` enum (not the raw string) so a future rename of
    the enum value cannot silently demote every admin to a 403.
    """
    user = await _current_user(request)
    return user is not None and user.role is Role.ADMIN


def _service(request: Request) -> VehicleCatalogService:
    resources = getattr(request.app.state, "product", None)
    if resources is None or getattr(resources, "vehicle_service", None) is None:
        raise HTTPException(status_code=503, detail="Vehicle catalog service unavailable")
    return resources.vehicle_service


def _summary(detail) -> VehicleSummaryOut:
    v = detail.vehicle
    return VehicleSummaryOut(
        vehicle_id=v.vehicle_id,
        vehicle_type=v.vehicle_type.value,
        brand=v.brand,
        model_name=v.model_name,
        variant_name=v.variant_name,
        model_year=v.model_year,
        status=v.status.value,
        slug=v.slug,
        image_url=v.image_url,
        detail_url=v.detail_url,
    )


def _detail_out(detail) -> VehicleDetailOut:
    specs = {}
    if detail.specs is not None:
        import dataclasses
        from datetime import date
        from datetime import datetime as _dt

        from src.products.domain.entities import Car, Motorbike

        if isinstance(detail.specs, (Car, Motorbike)):
            for field_name, value in dataclasses.asdict(detail.specs).items():
                if isinstance(value, (_dt, date)):
                    specs[field_name] = value.isoformat()
                elif value is not None:
                    specs[field_name] = str(value)
    return VehicleDetailOut(
        vehicle=_summary(detail),
        specs=specs,
        prices=[VehiclePriceOut.model_validate(_point_dict(p)) for p in detail.prices],
        battery_policies=[BatteryPolicyOut.model_validate(_policy_dict(bp)) for bp in detail.battery_policies],
        feature_flags=[VehicleFeatureFlagOut.model_validate(_flag_dict(f)) for f in detail.feature_flags],
        promotions=[PromotionLinkOut(promotion_id=p.promotion_id, vehicle_id=p.vehicle_id) for p in detail.promotions],
        showcase_items=[
            {
                "showcase_item_id": item.showcase_item_id,
                "section_key": item.section_key,
                "item_key": item.item_key,
                "title": item.title,
                "description": item.description,
                "media_url": item.media_url,
                "media_alt": item.media_alt,
                "display_order": item.display_order,
                "source_url": item.source_url,
                "source_retrieved_at": item.source_retrieved_at,
            }
            for item in detail.showcase_items
        ],
    )


def _point_dict(point) -> dict:
    from datetime import datetime as _dt

    # Ensure valid_from and valid_to are datetime objects
    valid_from = (
        point.valid_from.isoformat()
        if hasattr(point, "valid_from") and isinstance(point.valid_from, _dt)
        else point.valid_from
    )
    valid_to = (
        point.valid_to.isoformat() if hasattr(point, "valid_to") and isinstance(point.valid_to, _dt) else point.valid_to
    )

    return {
        "price_id": point.price_id,
        "price_type": point.price_type,
        "amount_vnd": point.amount_vnd,
        "currency": point.currency,
        "region_code": point.region_code,
        "status": point.status.value,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


def _policy_dict(policy) -> dict:
    from datetime import datetime as _dt

    # Ensure valid_from and valid_to are datetime objects
    valid_from = (
        policy.valid_from.isoformat()
        if hasattr(policy, "valid_from") and isinstance(policy.valid_from, _dt)
        else policy.valid_from
    )
    valid_to = (
        policy.valid_to.isoformat()
        if hasattr(policy, "valid_to") and isinstance(policy.valid_to, _dt)
        else policy.valid_to
    )

    return {
        "battery_policy_id": policy.battery_policy_id,
        "ownership_model": policy.ownership_model.value,
        "status": policy.status.value,
        "version": policy.version,
        "monthly_fee_vnd": policy.monthly_fee_vnd,
        "purchase_price_vnd": policy.purchase_price_vnd,
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


def _flag_dict(flag) -> dict:
    return {
        "feature_code": flag.feature_code,
        "name": flag.name,
        "status": flag.status,
        "verification_status": flag.verification_status,
        "value_text": flag.value_text,
        "value_number": float(flag.value_number)
        if hasattr(flag, "value_number") and flag.value_number is not None
        else None,
        "value_boolean": flag.value_boolean,
    }


# ---------------------------------------------------------------------------
# Customer endpoints
# ---------------------------------------------------------------------------


@router.get("/vehicles", response_model=StandardListResponse)
async def list_vehicles(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    vehicle_type: str | None = Query(default=None),
) -> StandardListResponse:
    svc = _service(request)
    params = PageParams(skip=(page - 1) * page_size, limit=page_size)
    items = await svc.list_active_vehicles(params, vehicle_type=vehicle_type)
    total = await svc.count_active_vehicles(vehicle_type=vehicle_type)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return StandardListResponse(
        data=[_detail_out(v) for v in items],
        pagination=PaginationOut(page=page, page_size=page_size, total_items=total, total_pages=total_pages),
        meta=MetaOut(),
    )


@router.get("/vehicles/search", response_model=StandardListResponse)
async def search_vehicles(
    request: Request,
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> StandardListResponse:
    svc = _service(request)
    params = PageParams(skip=(page - 1) * page_size, limit=page_size)
    items = await svc.search_vehicles(q, params)
    total = len(items)
    return StandardListResponse(
        data=[_detail_out(v) for v in items],
        pagination=PaginationOut(page=page, page_size=page_size, total_items=total, total_pages=1),
        meta=MetaOut(),
    )


# ---------------------------------------------------------------------------
# Lightweight diagnostic endpoint — verifies wiring.
#
# IMPORTANT: this route MUST be registered BEFORE ``/vehicles/{identifier}``
# because FastAPI matches routes in declaration order, and ``_schema-types``
# would otherwise be captured by the ``{identifier}`` path parameter
# (underscores are valid path characters). The route does not touch the
# database or auth — it only enumerates the ``VehicleType`` enum — but the
# path-param shadowing would route the request through ``get_vehicle_detail``
# and ultimately raise 503 from the product service. See regression test
# ``test_schema_types_not_captured_by_identifier_param``.
# ---------------------------------------------------------------------------


@router.get("/vehicles/_schema-types", response_model=StandardSuccessResponse)
async def list_vehicle_types(_: Request) -> StandardSuccessResponse:
    """Expose VehicleType enum để kiểm thử wiring."""
    return StandardSuccessResponse(data={"vehicle_types": [t.value for t in VehicleType]}, meta=MetaOut())


@router.get("/vehicles/{identifier}/tco", response_model=StandardSuccessResponse)
async def get_vehicle_tco(
    identifier: str,
    request: Request,
    province: str = Query(..., min_length=1),
    monthly_distance_km: int = Query(..., ge=1, le=20000),
    ownership_years: int = Query(default=5, ge=1, le=15),
) -> StandardSuccessResponse:
    """GET /vehicles/{identifier}/tco — ước tính tổng chi phí sở hữu.

    NOTE: đăng ký TRƯỚC ``/vehicles/{identifier}`` để tránh nhầm lẫn thứ tự
    khớp route (theo ghi chú của route ``_schema-types`` phía trên), dù xét kỹ
    ``/tco`` có thêm một segment nên không thực sự bị ``{identifier}`` nuốt.
    """
    resources = getattr(request.app.state, "product", None)
    service = None if resources is None else getattr(resources, "tco_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vehicle catalog service unavailable",
        )
    try:
        estimate = await service.estimate(
            identifier,
            monthly_km=Decimal(monthly_distance_km),
            years=ownership_years,
            # `province` bắt buộc: lệ phí biển số ô tô chênh 100 lần giữa hai
            # khu vực, nên không có giá trị mặc định nào đúng cho cả nước.
            region_code=resolve_region_code(province),
        )
    except ProductNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vehicle_not_found") from None
    except TcoUnavailableError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tco_unavailable") from None

    breakdown = estimate.breakdown
    return StandardSuccessResponse(
        data=TcoOut(
            breakdown=TcoBreakdownOut(
                vehicle_price_vnd=int(breakdown.vehicle_price_vnd),
                price_type=estimate.price_type,
                registration_fee_vnd=int(breakdown.registration_fee_vnd),
                plate_fee_vnd=int(breakdown.plate_fee_vnd),
                inspection_fee_vnd=int(breakdown.inspection_vnd),
                inspection_count=breakdown.inspection_count,
                insurance_vnd=int(breakdown.insurance_vnd),
                road_fee_vnd=int(breakdown.road_fee_vnd),
                electricity_vnd=int(breakdown.electricity_vnd),
                maintenance_vnd=int(breakdown.maintenance_vnd),
                maintenance_count=breakdown.maintenance_count,
                total_km=int(breakdown.total_km),
                total_upfront_vnd=int(breakdown.total_upfront_vnd),
                total_ownership_vnd=int(breakdown.total_ownership_vnd),
            ),
            assumptions=TcoAssumptionsOut(
                region_code=estimate.assumptions["region_code"],
                assumption_version=estimate.assumptions["assumption_version"],
                electricity_vnd_per_kwh=int(estimate.assumptions["electricity_vnd_per_kwh"]),
                registration_fee_percent=str(estimate.assumptions["registration_fee_percent"]),
                horizon_months=estimate.assumptions["horizon_months"],
                source_note=estimate.assumptions["source_note"],
            ),
            consumption=TcoConsumptionOut(
                kwh_per_100km=str(estimate.kwh_per_100km),
                source=estimate.consumption_source,
                derivation=estimate.derivation,
            ),
        )
    )


@router.get("/vehicles/{identifier}", response_model=StandardSuccessResponse)
async def get_vehicle_detail(identifier: str, request: Request) -> StandardSuccessResponse:
    """GET /vehicles/{identifier} — lookup by vehicle_id, slug, or SKU.

    NOTE: this route is intentionally registered AFTER
    ``/vehicles/_schema-types``. FastAPI matches routes in declaration order,
    and ``_schema-types`` would otherwise be captured by ``{identifier}`` here
    (underscores are valid path characters). Reordering must preserve that.
    """
    svc = _service(request)
    try:
        detail = await svc.get_vehicle_detail(identifier)
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "VEHICLE_NOT_FOUND", "message": str(exc), "details": {}}},
        ) from exc
    return StandardSuccessResponse(data=_detail_out(detail), meta=MetaOut())


@router.get("/vehicles/{identifier}/rag-context", response_model=StandardSuccessResponse)
async def get_vehicle_rag_context(identifier: str, request: Request) -> StandardSuccessResponse:
    svc = _service(request)
    try:
        ctx = await svc.get_vehicle_rag_context(identifier)
        return StandardSuccessResponse(data={"context": ctx}, meta=MetaOut())
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "VEHICLE_NOT_FOUND", "message": str(exc), "details": {}}},
        ) from exc


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/vehicles", response_model=StandardListResponse)
async def list_admin_vehicles(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> StandardListResponse:
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    params = PageParams(skip=(page - 1) * page_size, limit=page_size)
    items = await svc.list_admin_vehicles(params, status=status_filter, is_admin=True)
    total = await svc.count_admin_vehicles(status=status_filter, is_admin=True)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return StandardListResponse(
        data=[_detail_out(v) for v in items],
        pagination=PaginationOut(page=page, page_size=page_size, total_items=total, total_pages=total_pages),
        meta=MetaOut(),
    )


@router.post(
    "/admin/vehicles",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_vehicle(payload: VehicleCreate, request: Request) -> StandardSuccessResponse:
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        detail = await svc.create_vehicle(payload.model_dump(), is_admin=True)
        return StandardSuccessResponse(data=_detail_out(detail), meta=MetaOut())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/admin/vehicles/{vehicle_id}", response_model=StandardSuccessResponse)
async def update_admin_vehicle(vehicle_id: str, payload: VehicleUpdate, request: Request) -> StandardSuccessResponse:
    """Cap nhat mot phan thong tin xe (§6.4)."""
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        detail = await svc.update_vehicle(vehicle_id, payload.model_dump(exclude_unset=True), is_admin=True)
        return StandardSuccessResponse(data=_detail_out(detail), meta=MetaOut())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/admin/vehicles/{vehicle_id}/prices/{price_id}", response_model=StandardSuccessResponse)
async def update_admin_vehicle_price(
    vehicle_id: str, price_id: str, payload: VehiclePriceUpdate, request: Request
) -> StandardSuccessResponse:
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        detail = await svc.update_vehicle_price(
            vehicle_id, price_id, payload.model_dump(exclude_unset=True), is_admin=True
        )
        return StandardSuccessResponse(data=_detail_out(detail), meta=MetaOut())
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/admin/vehicles/{vehicle_id}/specs", response_model=StandardSuccessResponse)
async def update_admin_vehicle_specs(
    vehicle_id: str, payload: VehicleSpecsUpdate, request: Request
) -> StandardSuccessResponse:
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        detail = await svc.update_vehicle_specs(vehicle_id, payload.model_dump(exclude_unset=True), is_admin=True)
        return StandardSuccessResponse(data=_detail_out(detail), meta=MetaOut())
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put(
    "/admin/vehicles/{vehicle_id}/feature-flags/{feature_code}",
    response_model=StandardSuccessResponse,
)
async def review_admin_feature_flag(
    vehicle_id: str, feature_code: str, payload: FeatureFlagUpdate, request: Request
) -> StandardSuccessResponse:
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        flag = await svc.review_feature_flag(
            vehicle_id, feature_code, payload.model_dump(exclude_unset=True), is_admin=True
        )
        return StandardSuccessResponse(data=VehicleFeatureFlagOut.model_validate(_flag_dict(flag)), meta=MetaOut())
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/admin/vehicles/{vehicle_id}/prices", response_model=StandardSuccessResponse)
async def replace_admin_vehicle_prices(
    vehicle_id: str, payload: list[VehiclePriceIn], request: Request
) -> StandardSuccessResponse:
    """Thay bo gia hien hanh: gia cu chuyen EXPIRED, gia moi vao ACTIVE (§6.3)."""
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        detail = await svc.replace_vehicle_prices(vehicle_id, [p.model_dump() for p in payload], is_admin=True)
        return StandardSuccessResponse(data=_detail_out(detail), meta=MetaOut())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/admin/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_admin_vehicle(vehicle_id: str, request: Request) -> None:
    """Archive mềm — giữ nguyên hàng, chỉ đổi status sang ARCHIVED (§6.5).

    Giữ động từ DELETE để frontend không phải sửa lời gọi, nhưng ngữ nghĩa là
    archive: dữ liệu con (specs, giá, feature flags) không bị cascade xóa.
    """
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        await svc.archive_vehicle(vehicle_id, is_admin=True)
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/admin/vehicles/{vehicle_id}/restore", response_model=StandardSuccessResponse)
async def restore_admin_vehicle(vehicle_id: str, request: Request) -> StandardSuccessResponse:
    """Gỡ archive, đưa xe về ACTIVE."""
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _service(request)
    try:
        detail = await svc.restore_vehicle(vehicle_id, is_admin=True)
        return StandardSuccessResponse(data=_detail_out(detail), meta=MetaOut())
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Feature Flags Admin
# ---------------------------------------------------------------------------


def _flag_service(request: Request) -> FeatureFlagService:
    resources = getattr(request.app.state, "product", None)
    if resources is None or getattr(resources, "feature_flag_service", None) is None:
        raise HTTPException(status_code=503, detail="Product module chua khoi tao")
    return resources.feature_flag_service


def _flag_out(detail) -> FeatureFlagOut:  # noqa: ANN001
    return FeatureFlagOut(
        vehicle_id=detail.vehicle_id,
        feature_code=detail.feature_code,
        status=detail.status,
        verification_status=detail.verification_status,
        vehicle_name=detail.vehicle_name,
        feature_name=detail.feature_name,
        confidence=float(detail.confidence) if detail.confidence is not None else None,
        updated_by=detail.updated_by,
    )


@router.get("/admin/feature-flags", response_model=StandardListResponse)
async def list_pending_feature_flags(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    vehicle_id: str | None = Query(default=None),
) -> StandardListResponse:
    """Liet ke feature flags dang cho duyet."""
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _flag_service(request)
    params = PageParams(skip=(page - 1) * page_size, limit=page_size)
    items = await svc.list_pending(params, is_admin=True, vehicle_id=vehicle_id)
    total = await svc.count_pending(is_admin=True, vehicle_id=vehicle_id)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return StandardListResponse(
        data=[_flag_out(f) for f in items],
        pagination=PaginationOut(page=page, page_size=page_size, total_items=total, total_pages=total_pages),
        meta=MetaOut(),
    )


@router.post(
    "/admin/feature-flags/{vehicle_id}/{feature_code}/review",
    response_model=StandardSuccessResponse,
)
async def review_feature_flag(
    vehicle_id: str, feature_code: str, payload: FeatureFlagReview, request: Request
) -> StandardSuccessResponse:
    """Duyet hoac tu choi mot feature flag. Chi ADMIN."""
    user = await _current_user(request)
    if user is None or user.role is not Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _flag_service(request)
    try:
        detail = await svc.review(vehicle_id, feature_code, payload.decision, actor_id=str(user.id), is_admin=True)
        return StandardSuccessResponse(data=_flag_out(detail), meta=MetaOut())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _offer_policy_service(request: Request) -> OfferPolicyService:
    resources = getattr(request.app.state, "product", None)
    if resources is None or getattr(resources, "offer_policy_service", None) is None:
        raise HTTPException(status_code=503, detail="Offer policy service unavailable")
    return resources.offer_policy_service


def _offer_policy_out(policy) -> OfferAdjustmentPolicyOut:  # noqa: ANN001
    return OfferAdjustmentPolicyOut(
        promotion_type=policy.promotion_type.value,
        adjust_min_vnd=policy.adjust_min_vnd,
        adjust_max_vnd=policy.adjust_max_vnd,
        adjust_min_percent=policy.adjust_min_percent,
        adjust_max_percent=policy.adjust_max_percent,
        financing_months_min=policy.financing_months_min,
        financing_months_max=policy.financing_months_max,
        financing_support_max_vnd=policy.financing_support_max_vnd,
        gift_value_max_vnd=policy.gift_value_max_vnd,
        allowed_gift_codes=policy.allowed_gift_codes,
        registration_support_max_vnd=policy.registration_support_max_vnd,
        other_max_vnd=policy.other_max_vnd,
    )


@router.get("/admin/offer-policies", response_model=StandardListResponse)
async def list_offer_policies(request: Request) -> StandardListResponse:
    """Liet ke toan bo offer_adjustment_policies. Chi ADMIN."""
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _offer_policy_service(request)
    policies = await svc.list(is_admin=True)
    return StandardListResponse(
        data=[_offer_policy_out(p) for p in policies],
        pagination=PaginationOut(page=1, page_size=len(policies), total_items=len(policies), total_pages=1),
        meta=MetaOut(),
    )


@router.post(
    "/admin/offer-policies",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_offer_policy(payload: OfferAdjustmentPolicyIn, request: Request) -> StandardSuccessResponse:
    """Tao mot offer_adjustment_policy. Chi ADMIN."""
    user = await _current_user(request)
    if user is None or user.role is not Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _offer_policy_service(request)
    try:
        policy = await svc.create(_to_policy_domain(payload), created_by=str(user.id), is_admin=True)
        return StandardSuccessResponse(data=_offer_policy_out(policy), meta=MetaOut())
    except AdjustmentOutOfBoundsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/admin/offer-policies/{promotion_type}", response_model=StandardSuccessResponse)
async def update_offer_policy(
    promotion_type: str, payload: OfferAdjustmentPolicyIn, request: Request
) -> StandardSuccessResponse:
    """Cap nhat mot phan cau hinh. Chi ADMIN."""
    user = await _current_user(request)
    if user is None or user.role is not Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _offer_policy_service(request)
    try:
        policy = await svc.update(
            promotion_type,
            payload.model_dump(exclude_unset=True, exclude_none=True),
            updated_by=str(user.id),
            is_admin=True,
        )
        return StandardSuccessResponse(data=_offer_policy_out(policy), meta=MetaOut())
    except AdjustmentOutOfBoundsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete(
    "/admin/offer-policies/{promotion_type}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_offer_policy(promotion_type: str, request: Request) -> None:
    """Xoa mot offer_adjustment_policy. Chi ADMIN."""
    if not await _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin role required")
    svc = _offer_policy_service(request)
    try:
        await svc.delete(promotion_type, is_admin=True)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _to_policy_domain(payload: OfferAdjustmentPolicyIn) -> OfferAdjustmentPolicy:
    return OfferAdjustmentPolicy(
        promotion_type=PromotionType(payload.promotion_type),
        adjust_min_vnd=payload.adjust_min_vnd,
        adjust_max_vnd=payload.adjust_max_vnd,
        adjust_min_percent=payload.adjust_min_percent,
        adjust_max_percent=payload.adjust_max_percent,
        financing_months_min=payload.financing_months_min,
        financing_months_max=payload.financing_months_max,
        financing_support_max_vnd=payload.financing_support_max_vnd,
        gift_value_max_vnd=payload.gift_value_max_vnd,
        allowed_gift_codes=payload.allowed_gift_codes,
        registration_support_max_vnd=payload.registration_support_max_vnd,
        other_max_vnd=payload.other_max_vnd,
    )


__all__ = ["router"]
