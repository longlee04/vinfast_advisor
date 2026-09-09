"""Cho phep doi cho luu anh so sanh bang bien moi truong."""

from __future__ import annotations

from pathlib import Path

from src.agents.services.operations.comparison_image import (
    ComparisonImageStore,
    default_comparison_image_dir,
)


def test_default_directory_is_used_when_the_env_var_is_absent() -> None:
    assert default_comparison_image_dir({}) == Path("data/comparison_images")


def test_env_var_overrides_the_default_directory() -> None:
    assert default_comparison_image_dir({"COMPARISON_IMAGE_DIR": "/tmp/p150-anh"}) == Path("/tmp/p150-anh")


def test_blank_env_var_falls_back_to_the_default() -> None:
    """Bien rong trong `.env` la loi cau hinh pho bien; khong duoc thanh Path('')."""
    assert default_comparison_image_dir({"COMPARISON_IMAGE_DIR": "   "}) == Path("data/comparison_images")


def test_store_round_trips_an_image_through_the_configured_directory(tmp_path: Path) -> None:
    from uuid import uuid4

    run_id = uuid4()
    store = ComparisonImageStore(default_comparison_image_dir({"COMPARISON_IMAGE_DIR": str(tmp_path)}))

    store.save(run_id, b"\x89PNG-gia-lap")

    assert store.load(run_id) == b"\x89PNG-gia-lap"
