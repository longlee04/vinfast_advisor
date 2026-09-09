"""Tests for downloading high-resolution motorbike imagery from official pages."""

from __future__ import annotations

from crawl.crawl_motorbike_showcase import MODEL_SOURCES, discover_official_asset


def test_every_motorbike_menu_entry_has_an_official_product_source() -> None:
    """The crawler must cover every motorbike exposed by the customer menu."""

    assert set(MODEL_SOURCES) == {
        "vero-x",
        "viper",
        "kinet",
        "feliz-2025",
        "feliz-ii",
        "kyo",
        "evo",
        "evo-lite",
        "evo-grand",
        "evo-grand-lite",
        "evo-lite-neo",
        "flazz",
        "flazz-max",
        "zgoo",
        "amio",
        "amio-s",
        "amio-s2",
        "vf-drgnfly-ebike",
    }


def test_discovers_large_product_asset_instead_of_mega_menu_thumbnail() -> None:
    html = """
    <img src="/on/demandware.static/menu/Evo-Grand-Lite.png">
    <source srcset="https://shop.vinfastauto.com/on/demandware.static/product/evo-grand-lite/hero.webp">
    """

    selected = discover_official_asset(
        html,
        page_url="https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-grand-lite.html",
        asset_suffix="product/evo-grand-lite/hero.webp",
    )

    assert selected.endswith("product/evo-grand-lite/hero.webp")
    assert "menu" not in selected
