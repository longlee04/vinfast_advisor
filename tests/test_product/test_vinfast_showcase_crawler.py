"""Tests for the deterministic official VinFast showcase crawler."""

from __future__ import annotations

from crawl.crawl_vinfast_showcase import build_vf8_showcase_rows


def test_vf8_crawler_only_accepts_assets_present_in_official_html() -> None:
    html = """
    <html><body>
      <img src="/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwhero/images/PDP/vf8/img-top.webp">
      <img src="/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dweco/reserves/VF8/vf8eco.webp">
      <img src="/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwplus/reserves/VF8/vf8plus.webp">
      <img src="/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwa/reserves/VF8/thietkekdh.webp">
      <!--
        <a id="colorExteriorCE1W-tab" data-color="Urban Mint"></a>
        <img src="/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwmint/reserves/VF8/exterior/product-CE1W.webp">
      -->
    </body></html>
    """

    rows = build_vf8_showcase_rows(html, retrieved_at="2026-08-11T10:00:00+07:00")

    assert rows[0]["section_key"] == "overview"
    assert all(row["source_url"].endswith("dat-coc-xe-vf8.html") for row in rows)
    media = {row["media_url"] for row in rows if row["media_url"]}
    assert any(url.endswith("img-top.webp") for url in media)
    assert any(url.endswith("vf8eco.webp") for url in media)
    assert not any(url.endswith("panorama.webp") for url in media)
    assert not any(row["title"] == "Urban Mint" for row in rows)


def test_vf8_crawler_uses_stable_ids_for_idempotent_import() -> None:
    html = '<img src="/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwhero/images/PDP/vf8/img-top.webp">'

    first = build_vf8_showcase_rows(html, retrieved_at="2026-08-11T10:00:00+07:00")
    second = build_vf8_showcase_rows(html, retrieved_at="2026-08-12T10:00:00+07:00")

    assert [row["showcase_item_id"] for row in first] == [row["showcase_item_id"] for row in second]
