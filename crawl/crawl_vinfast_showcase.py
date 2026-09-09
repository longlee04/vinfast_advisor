"""Crawl official VinFast media into additive showcase CSV records.

The crawler intentionally does not touch the existing vehicle, price, or spec CSVs.
It discovers media URLs from the official HTML and emits stable IDs so importing the
result with ``ON CONFLICT DO NOTHING`` is safe and idempotent.
"""

from __future__ import annotations

import argparse
import csv
import html as html_module
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

SOURCE_URL = "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf8.html"
VF8_VEHICLE_ID = "7b751a66-fd67-54a6-ac13-04a65f712033"
DEFAULT_OUTPUT = Path(__file__).parents[1] / "data-p150" / "catalog" / "vehicle_showcase_items.csv"

FIELDS = (
    "showcase_item_id",
    "vehicle_id",
    "section_key",
    "item_key",
    "title",
    "description",
    "media_url",
    "media_alt",
    "display_order",
    "source_url",
    "source_retrieved_at",
    "status",
    "created_at",
    "updated_at",
)

_ITEMS = (
    ("overview", "hero-wide", "VF 8", "Mẫu SUV điện kết hợp thiết kế hiện đại, không gian tiện nghi và công nghệ hỗ trợ người lái.", "img-top.webp", 0),
    ("exterior", "aerodynamics", "Thiết kế khí động học", "Giảm lực cản không khí, hỗ trợ hiệu quả vận hành và tạo dáng vẻ mạnh mẽ.", "thietkekdh.webp", 0),
    ("exterior", "mirrors", "Gương chiếu hậu hiện đại", "Chi tiết ngoại thất gọn gàng, đồng bộ với ngôn ngữ thiết kế của VF 8.", "guong.webp", 1),
    ("exterior", "panoramic-roof", "Trần kính toàn cảnh", "Mở rộng tầm nhìn và tăng cảm giác thoáng đãng cho khoang hành khách.", "panorama.webp", 2),
    ("exterior", "camera-360", "Camera 360°", "Hỗ trợ quan sát khu vực quanh xe khi di chuyển trong không gian hẹp.", "360.webp", 3),
    ("interior", "driver-monitor", "Giám sát người lái", "Hỗ trợ theo dõi sự tập trung của người lái trên hành trình.", "giamsatht.webp", 0),
    ("interior", "vegan-seats", "Ghế da vegan", "Không gian ngồi cao cấp với tiện nghi sưởi và thông gió tùy phiên bản.", "gheda-vegan.webp", 1),
    ("interior", "steering-wheel", "Vô lăng tiện dụng", "Các điều khiển quan trọng được bố trí trong tầm tay người lái.", "volang.webp", 2),
    ("interior", "hud", "Màn hình hiển thị kính lái", "Thông tin vận hành được đặt trong vùng quan sát phía trước.", "hud.webp", 3),
    ("technology", "vivi", "Trợ lý ảo ViVi 2.0", "Tương tác giọng nói tiếng Việt và hỗ trợ điều khiển nhiều tính năng trên xe.", "ai.webp", 0),
    ("technology", "ota", "Cập nhật phần mềm từ xa", "Nhận các bản cập nhật phần mềm và tính năng mới thuận tiện hơn.", "sota.webp", 1),
    ("technology", "mobile-app", "Ứng dụng VinFast", "Theo dõi và sử dụng một số tiện ích xe từ điện thoại.", "vapp.webp", 2),
    ("performance", "journey", "Sẵn sàng cho mọi hành trình", "Khả năng vận hành được trình bày cùng thông số đã lưu trong Catalog của nhóm.", "journey.webp", 0),
    ("safety", "sos", "Hỗ trợ khẩn cấp", "Các tính năng kết nối hỗ trợ trong tình huống cần trợ giúp.", "sos.webp", 0),
    ("safety", "airbags", "Hệ thống túi khí", "Bảo vệ hành khách bằng hệ thống an toàn thụ động trên xe.", "11-boombag.webp", 1),
    ("safety", "adas-warning", "Cảnh báo và hỗ trợ lái", "Các tính năng ADAS hỗ trợ quan sát và phản ứng trong nhiều tình huống giao thông.", "canhbaovc.webp", 2),
    ("versions", "eco", "VF 8 Eco", "Phiên bản Eco trong Catalog của nhóm.", "vf8eco.webp", 0),
    ("versions", "plus", "VF 8 Plus", "Phiên bản Plus trong Catalog của nhóm.", "vf8plus.webp", 1),
)

_URL_RE = re.compile(
    r"(?:https://shop\.vinfastauto\.com)?/on/demandware\.static/[^\"'<>\s]+",
    re.IGNORECASE,
)
_COLOR_RE = re.compile(
    r'<a[^>]+id="colorExterior(?P<code>[A-Za-z0-9]+)-tab"[^>]+data-color="(?P<name>[^"]+)"',
    re.IGNORECASE,
)


def _asset_urls(html: str) -> dict[str, str]:
    assets: dict[str, str] = {}
    for raw_url in _URL_RE.findall(html_module.unescape(html)):
        url = urljoin(SOURCE_URL, raw_url.rstrip("),"))
        filename = url.rsplit("/", 1)[-1].split("?", 1)[0]
        assets.setdefault(filename.lower(), url)
    return assets


def _stable_id(item_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{SOURCE_URL}#{VF8_VEHICLE_ID}:{item_key}"))


def build_vf8_showcase_rows(html: str, *, retrieved_at: str) -> list[dict[str, str]]:
    """Build normalized rows using only official asset URLs found in ``html``."""

    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    assets = _asset_urls(html)
    rows: list[dict[str, str]] = []
    for section, key, title, description, filename, order in _ITEMS:
        media_url = assets.get(filename.lower())
        if media_url is None:
            continue
        item_key = f"{section}.{key}"
        rows.append(
            {
                "showcase_item_id": _stable_id(item_key),
                "vehicle_id": VF8_VEHICLE_ID,
                "section_key": section,
                "item_key": item_key,
                "title": title,
                "description": description,
                "media_url": media_url,
                "media_alt": f"VinFast VF 8 - {title}",
                "display_order": str(order),
                "source_url": SOURCE_URL,
                "source_retrieved_at": retrieved_at,
                "status": "ACTIVE",
                "created_at": retrieved_at,
                "updated_at": retrieved_at,
            }
        )

    color_order = 0
    for match in _COLOR_RE.finditer(html):
        code = match.group("code")
        name = html_module.unescape(match.group("name")).strip()
        media_url = assets.get(f"product-{code}.webp".lower())
        if media_url is None:
            continue
        item_key = f"colors.{code.lower()}"
        rows.append(
            {
                "showcase_item_id": _stable_id(item_key),
                "vehicle_id": VF8_VEHICLE_ID,
                "section_key": "colors",
                "item_key": item_key,
                "title": name,
                "description": "Tùy chọn màu ngoại thất được giới thiệu trên trang VinFast VF 8.",
                "media_url": media_url,
                "media_alt": f"VinFast VF 8 màu {name}",
                "display_order": str(color_order),
                "source_url": SOURCE_URL,
                "source_retrieved_at": retrieved_at,
                "status": "ACTIVE",
                "created_at": retrieved_at,
                "updated_at": retrieved_at,
            }
        )
        color_order += 1

    section_order = {
        "overview": 0,
        "colors": 1,
        "exterior": 2,
        "interior": 3,
        "technology": 4,
        "performance": 5,
        "safety": 6,
        "versions": 7,
    }
    return sorted(
        rows,
        key=lambda row: (
            section_order[row["section_key"]],
            int(row["display_order"]),
            row["item_key"],
        ),
    )


def fetch_html(url: str = SOURCE_URL) -> str:
    """Fetch the official product page with a transparent crawler user agent."""

    request = Request(url, headers={"User-Agent": "P150CatalogCrawler/1.0 (+educational-project)"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed official HTTPS URL
        return response.read().decode("utf-8")


def write_rows(rows: list[dict[str, str]], output: Path = DEFAULT_OUTPUT) -> None:
    """Write the additive showcase dataset without changing any existing catalog CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    retrieved_at = datetime.now(UTC).isoformat()
    rows = build_vf8_showcase_rows(fetch_html(), retrieved_at=retrieved_at)
    if not rows:
        raise RuntimeError("No official VF8 showcase assets were discovered")
    write_rows(rows, args.output)
    print(f"Wrote {len(rows)} official VF8 showcase items to {args.output}")


if __name__ == "__main__":
    main()
