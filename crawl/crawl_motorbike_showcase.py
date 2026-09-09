"""Download full-size imagery for motorbikes exposed by the customer menu.

All assets are discovered on official VinFast product pages and copied into the
frontend public directory.  The application therefore never enlarges the small
mega-menu thumbnails and does not depend on hotlinked CDN URLs at runtime.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "frontend" / "public" / "vehicles" / "motorbikes"
URL_ATTRIBUTE_NAMES = ("content", "src", "data-src", "data-original", "srcset", "data-srcset")
IMAGE_SUFFIX_RE = re.compile(r"\.(?:avif|jpe?g|png|webp)(?:\?.*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class MotorbikeSource:
    """Official page and preferred full-size asset for one menu model."""

    page_url: str
    asset_suffix: str


MODEL_SOURCES: dict[str, MotorbikeSource] = {
    "vero-x": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-may-dien-verox.html", "images/PDP-XMD/verox/img-top-verox-green.webp"),
    "viper": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-viper", "themes/porto/img/pdp-page/viper/viper-gray.webp"),
    "kinet": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-kinet", "vinfast-kinet-mau-xam-den.webp"),
    "feliz-2025": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-may-dien-feliz.html", "images/PDP-XMD/feliz/2025/img-top-feliz-green.webp"),
    "feliz-ii": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-feliz-II", "themes/porto/img/pdp-page/feliz-ii/feliz-ii-red.webp"),
    "kyo": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-kyo", "vinfast-kyo-mau-nau.webp"),
    "evo": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-evo", "themes/porto/img/pdp-page/evo/img-banner-info.webp"),
    "evo-lite": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-evo", "themes/porto/img/pdp-page/evo/duo-choice-section.png"),
    "evo-grand": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-grand.html", "landingpage/lp-xmd/evo-grand/hero.webp"),
    "evo-grand-lite": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-grand-lite.html", "landingpage/lp-xmd/evo-grand-lite/hero.webp"),
    "evo-lite-neo": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-may-dien-evo-lite-neo.html", "images/PDP-XMD/evoliteneo/img-top-evoliteneo-green.webp"),
    "flazz": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-may-dien-flazz.html", "images/PDP-XMD/flazz/img-flazz-red.webp"),
    "flazz-max": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-flazz-max", "themes/porto/img/pdp-page/flazz-max/flazz-max-white.webp"),
    "zgoo": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-may-dien-zgoo.html", "images/PDP-XMD/zgoo/img-zgoo-green.webp"),
    "amio": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-amio", "pdp/amio/amio-black.webp"),
    "amio-s": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-amio-s", "themes/porto/img/pdp-page/amio-s/amio-s-gray.webp"),
    "amio-s2": MotorbikeSource("https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-amio-s2", "amio-s2-herobanner-den.png"),
    "vf-drgnfly-ebike": MotorbikeSource("https://shop.vinfastauto.com/vn_vi/xe-dap-dien-drgnfly.html", "reserves/DrgnFly/overview-01.png"),
}


def _candidate_urls(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for tag in soup.find_all(("img", "source", "meta")):
        for name in URL_ATTRIBUTE_NAMES:
            raw = tag.get(name)
            if not isinstance(raw, str):
                continue
            for item in raw.split(","):
                value = item.strip().split(" ", 1)[0]
                candidate = urljoin(page_url, value)
                if IMAGE_SUFFIX_RE.search(candidate) and candidate not in urls:
                    urls.append(candidate)
    return urls


def discover_official_asset(html: str, *, page_url: str, asset_suffix: str) -> str:
    """Return the explicitly selected asset after verifying it exists in HTML."""

    normalized_suffix = asset_suffix.casefold().lstrip("/")
    matches = [
        url
        for url in _candidate_urls(html, page_url)
        if url.casefold().split("?", 1)[0].endswith(normalized_suffix)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one official asset ending in {asset_suffix}, found {len(matches)}")
    if "mega-menu" in matches[0].casefold():
        raise ValueError("mega-menu thumbnails cannot be used as detail-page imagery")
    return matches[0]


def _fetch(url: str) -> bytes:
    response = requests.get(url, impersonate="chrome", timeout=60)
    response.raise_for_status()
    return response.content


def crawl(output_dir: Path = DEFAULT_OUTPUT) -> list[Path]:
    """Discover, validate, and download every official product image."""

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for slug, source in MODEL_SOURCES.items():
        html = _fetch(source.page_url).decode("utf-8")
        asset_url = discover_official_asset(
            html, page_url=source.page_url, asset_suffix=source.asset_suffix
        )
        suffix = Path(asset_url.split("?", 1)[0]).suffix.lower() or ".webp"
        output = output_dir / f"{slug}{suffix}"
        output.write_bytes(_fetch(asset_url))
        with Image.open(output) as image:
            width, height = image.size
        if max(width, height) < 900 or min(width, height) < 500:
            output.unlink(missing_ok=True)
            raise ValueError(f"official asset for {slug} is too small: {width}x{height}")
        downloaded.append(output)
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    paths = crawl(args.output)
    print(f"Downloaded {len(paths)} official full-size motorbike images")


if __name__ == "__main__":
    main()
