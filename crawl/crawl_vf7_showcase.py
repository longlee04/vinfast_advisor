"""Download the selected VF 7 product-story assets from VinFast's official page."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PAGE_URL = "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf7.html"
DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "vehicles" / "vf7"


@dataclass(frozen=True)
class Asset:
    """One curated official image used by the VF 7 product story."""

    suffix: str
    section: str
    filename: str


ASSETS: dict[str, Asset] = {
    "hero": Asset("reserves/VF7/vf7-hero-car.webp", "overview", "hero.webp"),
    "solar-ruby": Asset("reserves/VF7/exterior/product-CE1M.webp", "colors", "solar-ruby.webp"),
    "zenith-grey": Asset("reserves/VF7/exterior/product-CE1V.webp", "colors", "zenith-grey.webp"),
    "urban-mint": Asset("reserves/VF7/exterior/product-CE1W.webp", "colors", "urban-mint.webp"),
    "infinity-blanc": Asset("reserves/VF7/exterior/product-CE18.webp", "colors", "infinity-blanc.webp"),
    "jet-black": Asset("reserves/VF7/exterior/product-CE11.webp", "colors", "jet-black.webp"),
    "exterior": Asset("reserves/VF7/vf7-slide-in-croped.webp", "exterior", "exterior.webp"),
    "technology": Asset("reserves/VF7/vf7-img-tech.webp", "technology", "technology.webp"),
    "design": Asset("reserves/VF7/vf7-masterpiece-1.webp", "exterior", "design.webp"),
    "interior": Asset("reserves/VF7/interior/vf7-noi-that-overview.webp", "interior", "interior.webp"),
    "performance": Asset("reserves/VF7/vf7-passion.webp", "performance", "performance.webp"),
}


def discover_assets(html: str, *, page_url: str, suffixes: list[str]) -> list[str]:
    """Resolve an explicit ordered list of assets present in official page HTML."""

    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for tag in soup.find_all(("img", "source")):
        for attribute in ("src", "data-src", "srcset", "data-srcset", "data-original"):
            raw = tag.get(attribute)
            if not isinstance(raw, str):
                continue
            for part in raw.split(","):
                candidate = urljoin(page_url, part.strip().split(" ", 1)[0])
                if candidate not in urls:
                    urls.append(candidate)
    selected: list[str] = []
    for suffix in suffixes:
        matches = [url for url in urls if url.split("?", 1)[0].endswith(suffix)]
        if len(matches) != 1:
            raise ValueError(f"expected one VF 7 asset ending in {suffix}, found {len(matches)}")
        if "mega-menu" in matches[0].casefold():
            raise ValueError("mega-menu thumbnails are not product-story media")
        selected.append(matches[0])
    return selected


def _fetch(url: str) -> bytes:
    response = requests.get(url, impersonate="chrome", timeout=60)
    response.raise_for_status()
    return response.content


def crawl(output_dir: Path = DEFAULT_OUTPUT) -> list[Path]:
    """Download and dimension-check all curated VF 7 assets."""

    html = _fetch(PAGE_URL).decode("utf-8")
    definitions = list(ASSETS.values())
    urls = discover_assets(html, page_url=PAGE_URL, suffixes=[asset.suffix for asset in definitions])
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for asset, url in zip(definitions, urls, strict=True):
        output = output_dir / asset.filename
        output.write_bytes(_fetch(url))
        with Image.open(output) as image:
            width, height = image.size
        if max(width, height) < 1000 or min(width, height) < 500:
            output.unlink(missing_ok=True)
            raise ValueError(f"VF 7 asset {asset.filename} is too small: {width}x{height}")
        outputs.append(output)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(f"Downloaded {len(crawl(args.output))} official VF 7 assets")


if __name__ == "__main__":
    main()
