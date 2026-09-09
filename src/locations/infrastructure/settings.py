"""Cấu hình module Locations, đọc từ biến môi trường `LOCATIONS_*`."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocationsSettings:
    """Cấu hình đủ để quyết định có bật module hay không."""

    enabled: bool
    database_url: str

    @classmethod
    def from_environment(cls) -> "LocationsSettings":
        enabled = os.environ.get("LOCATIONS_ENABLED", "false").strip().lower() == "true"
        url = os.environ.get("LOCATIONS_DATABASE_URL", "").strip()
        if not url:
            url = os.environ.get("AUTH_DATABASE_URL", "").strip()
        return cls(enabled=enabled, database_url=url)
