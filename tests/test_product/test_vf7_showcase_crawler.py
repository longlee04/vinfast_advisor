"""Tests for the official VF 7 showcase asset crawler."""

from crawl.crawl_vf7_showcase import ASSETS, PAGE_URL, discover_assets


def test_vf7_crawler_covers_product_story_sections_and_colors() -> None:
    assert PAGE_URL == "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf7.html"
    assert {asset.section for asset in ASSETS.values()} >= {
        "overview",
        "colors",
        "exterior",
        "interior",
        "performance",
        "technology",
    }
    assert len([asset for asset in ASSETS.values() if asset.section == "colors"]) == 5


def test_discovers_only_explicit_official_vf7_assets() -> None:
    html = """
    <img src="/images/mega-menu/car/VF7.png">
    <img src="/reserves/VF7/vf7-hero-car.webp">
    <img src="/reserves/VF7/interior/vf7-noi-that-overview.webp">
    """
    found = discover_assets(
        html,
        page_url=PAGE_URL,
        suffixes=[
            "reserves/VF7/vf7-hero-car.webp",
            "reserves/VF7/interior/vf7-noi-that-overview.webp",
        ],
    )
    assert found[0].endswith("reserves/VF7/vf7-hero-car.webp")
    assert found[1].endswith("reserves/VF7/interior/vf7-noi-that-overview.webp")
    assert all("mega-menu" not in url for url in found)
