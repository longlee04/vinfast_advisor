"""Composition root cho module Locations."""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.locations.application.location_service import LocationService
from src.locations.infrastructure.repositories import SqlAlchemyLocationStore
from src.locations.infrastructure.settings import LocationsSettings

LOG_FILE = Path("logs/app.log")


def get_locations_logger() -> logging.Logger:
    """Get or configure a logger for Locations that writes to logs/app.log."""
    logger = logging.getLogger("src.locations")
    logger.setLevel(logging.INFO)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    has_file_handler = any(
        isinstance(h, logging.FileHandler) and h.baseFilename.endswith("app.log") for h in logger.handlers
    )

    if not has_file_handler:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(file_handler)

    return logger


logger = get_locations_logger()


@dataclass(frozen=True, slots=True)
class LocationsResources:
    """Tài nguyên module Locations sở hữu trong suốt vòng đời ứng dụng."""

    engine: AsyncEngine
    service: LocationService


class LocationsComposition:
    """Tạo và dọn tài nguyên đúng một lần mỗi vòng đời."""

    def __init__(self, settings: LocationsSettings) -> None:
        self._settings = settings
        self._resources: LocationsResources | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @property
    def resources(self) -> LocationsResources | None:
        return self._resources

    async def start(self) -> None:
        if not self._settings.enabled:
            logger.info("Locations is disabled; skipping resource creation")
            return
        if not self._settings.database_url:
            logger.warning("Locations is enabled but has no database URL; staying disabled")
            return
        engine = create_async_engine(self._settings.database_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        self._resources = LocationsResources(
            engine=engine,
            service=LocationService(SqlAlchemyLocationStore(session_factory)),
        )
        logger.info("Locations started successfully")

    async def shutdown(self) -> None:
        """Dọn tài nguyên. An toàn khi gọi dù chưa từng start."""
        resources, self._resources = self._resources, None
        if resources is None:
            return
        await resources.engine.dispose()
        logger.info("Locations resources disposed")
