"""FastAPI routes cho module Locations. Toàn bộ công khai."""

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse

from src.locations.application.contracts import LocationPage, LocationSummary
from src.locations.domain.errors import InvalidBoundsError, InvalidRadiusError
from src.locations.presentation.schemas import (
    CategoryOut,
    LocationListOut,
    LocationOut,
    LocationsError,
    RegionOut,
)

router = APIRouter(prefix="/locations", tags=["locations"])


def _error(code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=LocationsError(error=code).model_dump(),
        headers={"Cache-Control": "no-store"},
    )


def _service(request: Request):
    composition = getattr(request.app.state, "locations", None)
    if composition is None or composition.resources is None:
        return None
    return composition.resources.service


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=LocationsError(error="locations_unavailable").model_dump(),
        headers={"Cache-Control": "no-store"},
    )


def _to_out(item: LocationSummary) -> LocationOut:
    return LocationOut(
        id=item.location_id,
        external_id=item.external_id,
        type=item.location_type,
        category_label=item.category_name,
        name=item.name,
        address=item.address,
        city=item.city,
        district=item.district,
        latitude=item.latitude,
        longitude=item.longitude,
        hotline=item.hotline,
        directions_url=item.directions_url,
        open_time=item.open_time,
        close_time=item.close_time,
        status=item.status,
        distance_km=item.distance_km,
    )


def _to_list(page: LocationPage) -> LocationListOut:
    return LocationListOut(
        items=[_to_out(item) for item in page.items],
        total=page.total,
        truncated=page.truncated,
    )


@router.get("", response_model=LocationListOut)
async def list_locations(
    request: Request,
    response: Response,
    south: float | None = Query(default=None),
    north: float | None = Query(default=None),
    west: float | None = Query(default=None),
    east: float | None = Query(default=None),
    types: list[str] = Query(default=[]),
    city: str | None = Query(default=None),
    district: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> LocationListOut | JSONResponse:
    service = _service(request)
    if service is None:
        return _unavailable()
    try:
        page = await service.list_locations(
            south=south,
            north=north,
            west=west,
            east=east,
            types=tuple(types),
            city=city,
            district=district,
            query=q,
            limit=limit,
        )
    except InvalidBoundsError:
        return _error("invalid_bounds")
    response.headers["Cache-Control"] = "no-store"
    return _to_list(page)


@router.get("/nearby", response_model=LocationListOut)
async def list_nearby(
    request: Request,
    response: Response,
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(default=10.0),
    types: list[str] = Query(default=[]),
    limit: int = Query(default=50, ge=1, le=200),
) -> LocationListOut | JSONResponse:
    service = _service(request)
    if service is None:
        return _unavailable()
    try:
        page = await service.list_nearby(
            latitude=lat, longitude=lon, radius_km=radius_km, types=tuple(types), limit=limit
        )
    except InvalidRadiusError:
        return _error("invalid_radius")
    except InvalidBoundsError:
        return _error("invalid_bounds")
    response.headers["Cache-Control"] = "no-store"
    return _to_list(page)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(request: Request, response: Response) -> list[CategoryOut] | JSONResponse:
    service = _service(request)
    if service is None:
        return _unavailable()
    entries = await service.list_categories()
    response.headers["Cache-Control"] = "no-store"
    return [CategoryOut(id=entry.location_type, label=entry.category_name, count=entry.count) for entry in entries]


@router.get("/regions", response_model=list[RegionOut])
async def list_regions(request: Request, response: Response) -> list[RegionOut] | JSONResponse:
    service = _service(request)
    if service is None:
        return _unavailable()
    entries = await service.list_regions()
    response.headers["Cache-Control"] = "no-store"
    return [RegionOut(city=entry.city, districts=list(entry.districts)) for entry in entries]


__all__ = ["router"]
