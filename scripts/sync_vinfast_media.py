"""Download reviewed public VinFast media into the frontend asset cache.

The source list is intentionally explicit instead of being a broad scraper: every
asset has a semantic role, alt text and an official product page. This keeps the
result reproducible and prevents unrelated campaign or navigation images from
entering product pages.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from curl_cffi import requests
from PIL import Image

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
OUTPUT_ROOT: Final = REPOSITORY_ROOT / "frontend" / "public" / "media" / "vinfast"


@dataclass(frozen=True)
class AssetSource:
    """A reviewed public media asset and its presentation metadata."""

    file: str
    source_url: str
    role: str
    alt: str


@dataclass(frozen=True)
class ModelSource:
    """The official source page and assets selected for one model."""

    model: str
    source_page: str
    assets: tuple[AssetSource, ...]


CATALOG_ROOT = "https://static-cms-prod.vinfastauto.com"
VF9_ROOT = "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default"

MODELS: Final[dict[str, ModelSource]] = {
    "vf2": ModelSource(
        "VF 2",
        "https://vinfastauto.com/vn_vi/vf-2",
        (AssetSource("hero.webp", f"{CATALOG_ROOT}/vf2_home_page.png", "hero", "VinFast VF 2"),),
    ),
    "vf3": ModelSource(
        "VF 3",
        "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf3.html",
        (AssetSource("hero.webp", f"{CATALOG_ROOT}/statics/img/homepage-v2/car/VF3.webp", "hero", "VinFast VF 3"),),
    ),
    "vf5": ModelSource(
        "VF 5",
        "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf5.html",
        (AssetSource("hero.webp", f"{CATALOG_ROOT}/statics/img/homepage-v2/car/VF5.webp", "hero", "VinFast VF 5"),),
    ),
    "vf6": ModelSource(
        "VF 6",
        "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf6.html",
        (AssetSource("hero.webp", f"{CATALOG_ROOT}/statics/img/homepage-v2/car/VF6.webp", "hero", "VinFast VF 6"),),
    ),
    "vf7": ModelSource(
        "VF 7",
        "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf7.html",
        (AssetSource("hero.webp", f"{CATALOG_ROOT}/statics/img/homepage-v2/car/VF7.webp", "hero", "VinFast VF 7"),),
    ),
    "vf8": ModelSource(
        "VF 8",
        "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf8.html",
        (AssetSource("hero.webp", f"{CATALOG_ROOT}/statics/img/homepage-v2/car/VF8.webp", "hero", "VinFast VF 8"),),
    ),
    "vf9": ModelSource(
        "VF 9",
        "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html",
        (
            AssetSource(
                "hero.webp",
                f"{VF9_ROOT}/dw174b57d5/images/PDP/vf9/202406/hero.webp",
                "hero",
                "VinFast VF 9 trên cung đường ven biển",
            ),
            AssetSource(
                "exterior-01.webp",
                f"{VF9_ROOT}/dw0c37f2bd/images/PDP/vf9/202406/img-vf9-top-side.webp",
                "exterior",
                "Thiết kế ngoại thất VinFast VF 9",
            ),
            AssetSource(
                "exterior-grey.webp",
                f"{VF9_ROOT}/dwf3c2decf/images/PDP/vf9/202406/exterior/CE1V.webp",
                "color",
                "VinFast VF 9 màu Zenith Grey",
            ),
            AssetSource(
                "exterior-white.webp",
                f"{VF9_ROOT}/dw37cb98dd/images/PDP/vf9/202406/exterior/CE1W.webp",
                "color",
                "VinFast VF 9 màu Infinity Blanc",
            ),
            AssetSource(
                "exterior-red.webp",
                f"{VF9_ROOT}/dwf7565bce/images/PDP/vf9/202406/exterior/CE1M.webp",
                "color",
                "VinFast VF 9 màu Crimson Red",
            ),
            AssetSource(
                "interior-01.webp",
                f"{VF9_ROOT}/dw82690e20/images/PDP/vf9/202406/interior/int-slide-1.webp",
                "interior",
                "Khoang nội thất VinFast VF 9",
            ),
            AssetSource(
                "interior-02.webp",
                f"{VF9_ROOT}/dwb13b43b4/images/PDP/vf9/202406/interior/int-slide-2.webp",
                "detail",
                "Hàng ghế trên VinFast VF 9",
            ),
            AssetSource(
                "technology-01.webp",
                f"{VF9_ROOT}/dwe554db5e/images/PDP/vf9/202406/interior/int-slide-4.webp",
                "technology",
                "Tiện nghi công nghệ trên VinFast VF 9",
            ),
        ),
    ),
    "kyo": ModelSource(
        "Kyo",
        "https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-kyo",
        (
            AssetSource("hero.webp", f"{CATALOG_ROOT}/vinfast-kyo-mau-nau.webp", "hero", "VinFast Kyo màu Nâu Ánh Kim"),
            AssetSource(
                "color-white.webp",
                f"{CATALOG_ROOT}/vinfast-kyo-mau-trang.webp",
                "color",
                "VinFast Kyo màu Trắng Ngọc Trai",
            ),
            AssetSource("color-red.webp", f"{CATALOG_ROOT}/vinfast-kyo-mau-do.webp", "color", "VinFast Kyo màu Đỏ"),
            AssetSource(
                "color-black.webp", f"{CATALOG_ROOT}/vinfast-kyo-mau-den.webp", "color", "VinFast Kyo màu Đen Bóng"
            ),
            AssetSource(
                "color-green.webp", f"{CATALOG_ROOT}/vinfast-kyo-mau-xanh.webp", "color", "VinFast Kyo màu Xanh Oliu"
            ),
            AssetSource(
                "technology-01.webp",
                f"{CATALOG_ROOT}/vinfast-kyo-mau-nau-sau.webp",
                "technology",
                "Màn hình và tay lái VinFast Kyo",
            ),
            AssetSource(
                "storage-01.webp", f"{CATALOG_ROOT}/vinfast-kyo-mau-nau-cop.webp", "detail", "Cốp xe VinFast Kyo"
            ),
            AssetSource(
                "comfort-01.webp", f"{CATALOG_ROOT}/vinfast-kyo-mau-nau-san.webp", "detail", "Sàn để chân VinFast Kyo"
            ),
            AssetSource(
                "safety-01.webp",
                f"{CATALOG_ROOT}/vinfast-kyo-mau-nau-banh.webp",
                "safety",
                "Bánh và hệ thống phanh VinFast Kyo",
            ),
            AssetSource(
                "battery-01.webp",
                f"{CATALOG_ROOT}/vinfast-kyo-mau-nau-nghieng-phai.webp",
                "battery",
                "VinFast Kyo nhìn nghiêng",
            ),
        ),
    ),
}


def download_image(asset: AssetSource, destination: Path) -> tuple[int, int, str]:
    """Download, normalize and optimize one asset as WebP."""

    response = requests.get(asset.source_url, impersonate="chrome", timeout=45)
    response.raise_for_status()
    digest = hashlib.sha256(response.content).hexdigest()
    with Image.open(io.BytesIO(response.content)) as source:
        image = source.convert("RGBA" if "A" in source.getbands() else "RGB")
        image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        width, height = image.size
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "WEBP", quality=86, method=6)
    return width, height, digest


def sync_model(slug: str, source: ModelSource) -> None:
    """Synchronize one model directory and write its manifest."""

    model_dir = OUTPUT_ROOT / slug
    manifest_assets: list[dict[str, object]] = []
    for asset in source.assets:
        width, height, digest = download_image(asset, model_dir / asset.file)
        manifest_assets.append(
            {
                **asdict(asset),
                "width": width,
                "height": height,
                "sha256": digest,
            }
        )
        print(f"{slug}: {asset.file} ({width}x{height})")
    manifest = {
        "model": source.model,
        "source_page": source.source_page,
        "assets": manifest_assets,
    }
    (model_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line model selection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "models",
        nargs="*",
        default=None,
        help="Model slugs to synchronize. Defaults to all reviewed models.",
    )
    return parser.parse_args()


def main() -> None:
    """Synchronize the selected reviewed public assets."""

    args = parse_args()
    for slug in args.models or sorted(MODELS):
        if slug not in MODELS:
            raise SystemExit(f"Unknown model {slug!r}; choose from {', '.join(sorted(MODELS))}")
        sync_model(slug, MODELS[slug])


if __name__ == "__main__":
    main()
