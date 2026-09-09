"""Crawler module for VinFast vehicle product data (P-150 project).

Fetches vehicle detail pages, cleans raw content, strips comparison sections,
and structures unstructured descriptions into Markdown for RAG consumption.
"""

import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests  # type: ignore[no-redef]
    USE_CURL_CFFI = False

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "app.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Output directory
OUTPUT_DIR = Path("data-p150/car_pdf")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 9 target vehicles mapping with updated URLs
VEHICLES: dict[str, dict[str, str]] = {
    "VF2": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-2/",
        "title": "Xe điện VinFast VF2",
    },
    "VF3": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-3/",
        "title": "Xe điện VinFast VF3",
    },
    "VF5": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-5/",
        "title": "Xe điện VinFast VF5",
    },
    "VF6": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-6/",
        "title": "Xe điện VinFast VF6",
    },
    "MPV7": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-mpv-7/",
        "title": "Xe điện VinFast MPV7",
    },
    "VF7": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-7/",
        "title": "Xe điện VinFast VF7",
    },
    "VF8": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-8/",
        "title": "Xe điện VinFast VF8",
    },
    "VF8_2026": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-8-all-new/",
        "title": "Xe điện VinFast VF8 The All-New 2026",
    },
    "VF9": {
        "url": "https://vinfastvietnam.com.vn/vinfast-vf-9/",
        "title": "Xe điện VinFast VF9",
    },
}

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

COMPARISON_PATTERN: re.Pattern[str] = re.compile(
    r"so\s*sánh.*động\s*cơ\s*đốt\s*trong", re.IGNORECASE
)

SECTION_KEYWORDS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "Tổng quan",
        [
            "tổng quan", "giới thiệu", "biểu tượng", "định vị", "bước tiến",
            "ô tô đầu đời", "sự lựa chọn", "series mới", "all new",
            "tùy chọn cho ngân sách", "giá bán", "ước mơ trong tầm với",
            "khuyến mãi", "ưu đãi", "bảng giá"
        ],
    ),
    (
        2,
        "Thiết kế ngoại thất",
        [
            "ngoại thất", "thân xe", "thiết kế đèn", "la-zăng", "mâm", "màu",
            "cửa", "kính", "gương", "cốp", "phong cách", "vũ trụ phi đối xứng",
            "khí động học", "dấu ấn", "ánh nhìn"
        ],
    ),
    (
        3,
        "Nội thất",
        [
            "nội thất", "cabin", "không gian", "ghế", "bật", "da", "điều hòa",
            "vật liệu", "bố trí", "trải nghiệm thị giác", "khoáng đạt"
        ],
    ),
    (
        4,
        "Công nghệ và tiện nghi",
        [
            "công nghệ", "màn hình", "tiện nghi", "giải trí", "âm thanh", "kết nối",
            "apple carplay", "android auto", "trợ lý", "điều khiển", "thông minh",
            "ứng dụng", "ota", "sạc", "pin", "tiện lợi", "vận hành"
        ],
    ),
    (
        5,
        "An toàn",
        [
            "an toàn", "túi khí", "camera", "cảm biến", "hỗ trợ an toàn", "bảo vệ"
        ],
    ),
    (
        6,
        "ADAS",
        [
            "adas", "trợ lái", "hỗ trợ lái", "tự động", "cruise control",
            "làn đường", "cảnh báo", "phanh khẩn cấp", "điểm mù"
        ],
    ),
    (
        7,
        "Các tính năng nổi bật",
        [
            "nổi bật", "điểm nổi bật", "tính năng nổi bật", "đặc trưng", "ưu điểm",
            "tính năng"
        ],
    ),
]


def clean_text(text: str | None) -> str:
    """Normalize string using NFC unicode normalization and whitespace collapsing."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", normalized).strip()


def is_form_or_ui_noise(text: str) -> bool:
    """Filter out navigation, cookie, login dialog, and registration form noise."""
    if len(text) < 2:
        return True
    t_lower = text.lower()

    exact_noise = {
        "giá bán", "giới thiệu", "ngoại thất", "nội thất", "tính năng", "thông số",
        "dark", "light", "dark light", "nhận ưu đãi", "đóng", "tiện ích", "mua sắm",
        "tin tức", "hỗ trợ", "thảo luận", "đặt cọc", "tải brochure",
        "dự toán chi phí lăn bánh", "đăng nhập / đăng ký", "so sánh", "quay lại",
        "xem thêm", "gửi thông tin", "chọn màu chi tiết tại đây"
    }
    if t_lower in exact_noise:
        return True

    noise_keywords = [
        "họ và tên", "nhập số điện thoại", "quên mật khẩu",
        "đăng nhập", "đăng ký", "tôi đồng ý", "cảm ơn quý khách",
        "thời gian dự kiến", "phương thức thanh toán", "về đầu trang",
        "thay đổi thành công", "kích hoạt tài khoản", "quý khách vui lòng",
        "vui lòng để lại thông tin", "dự toán chi phí",
        "bảo vệ dữ liệu cá nhân", "gửi thông tin",
        "chuyên viên tư vấn", "dữ liệu cá nhân", "quý khách cần hỗ trợ", "bảo mật thông tin",
        "nhập thông tin xe động cơ", "tính phí lăn bánh", "dự toán trả góp"
    ]
    return any(k in t_lower for k in noise_keywords)


def categorize_text(text: str) -> int:
    """Categorize text line into one of the standard section numbers (1-7)."""
    t_lower = text.lower()
    for sec_num, _, keywords in SECTION_KEYWORDS:
        if any(kw in t_lower for kw in keywords):
            return sec_num
    return 1


def fetch_html(url: str) -> str:
    """Fetch HTML from given URL using curl_cffi (or fallback requests)."""
    if USE_CURL_CFFI:
        resp = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=30)
    else:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def crawl_vehicle(doc_id: str, data: dict[str, str]) -> bool:
    """Crawl a single vehicle URL, extract text, format to Markdown, and save file."""
    url = data["url"]
    title = data["title"]
    log.info(f"Crawling {doc_id} from {url}")
    print(f"[INFO] Crawling {doc_id} from {url}")

    try:
        html_content = fetch_html(url)
        soup = BeautifulSoup(html_content, "html.parser")
    except Exception as e:
        log.error(f"Failed to fetch {url}: {e}")
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return False

    # Remove script, style, header, footer, etc.
    for tag in soup(
        [
            "script", "style", "header", "footer", "nav", "noscript",
            "svg", "iframe", "button", "input", "select", "textarea",
            "form", "label"
        ]
    ):
        tag.decompose()

    for tag in soup.find_all(
        id=re.compile(r"modal|login|register|lead|auth|footer", re.I)
    ):
        tag.decompose()

    # Locate comparison section, remove it and all subsequent elements
    for el in soup.find_all(True):
        txt = clean_text(el.get_text(separator=" ", strip=True))
        if COMPARISON_PATTERN.search(txt) and len(txt) < 150:
            log.info(f"Removed section: So sánh với động cơ đốt trong in {doc_id}")
            parent = el.parent
            while parent and parent.name not in ["section", "div", "body"]:
                parent = parent.parent
            if parent and parent.name != "body":
                for next_node in list(parent.find_next_siblings()):
                    next_node.decompose()
                parent.decompose()
            break

    block_tags = [
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "dd", "tr", "figcaption"
    ]
    raw_blocks: list[tuple[str, str]] = []
    seen: set[str] = set()

    for el in soup.find_all(True):
        if el.name in block_tags or (el.name == "div" and not el.find_all(block_tags)):
            txt = clean_text(el.get_text(separator=" ", strip=True))
            if not txt or is_form_or_ui_noise(txt):
                continue
            if COMPARISON_PATTERN.search(txt):
                break

            if txt in seen:
                continue

            if any(txt in s and len(s) > len(txt) for s in seen):
                continue

            seen.add(txt)
            raw_blocks.append((el.name, txt))

    log.info(f"Raw text blocks extracted: {len(raw_blocks)}")

    # Categorize into sections
    sections: dict[int, list[tuple[str, str]]] = {
        num: [] for num, _, _ in SECTION_KEYWORDS
    }
    current_sec = 1

    for tag_name, text in raw_blocks:
        detected_sec = categorize_text(text)
        if tag_name.startswith("h"):
            current_sec = detected_sec

        sections[current_sec].append((tag_name, text))

    today = date.today().isoformat()
    doc_md: list[str] = [
        "---",
        f"doc_id: {doc_id}",
        f"title: {title}",
        f"source_url: {url}",
        "category: car",
        "language: vi",
        f"date_crawled: {today}",
        f"converted_at: {today}",
        "---",
        "",
        f"# {title}",
        "",
    ]

    for num, sec_title, _ in SECTION_KEYWORDS:
        sec_items = sections[num]
        if not sec_items:
            continue

        doc_md.append(f"## {num}. {sec_title}")
        doc_md.append("")

        for tag_name, text in sec_items:
            if tag_name.startswith("h"):
                doc_md.append(f"### {text}")
            elif tag_name == "li":
                doc_md.append(f"- {text}")
            elif tag_name == "dt":
                doc_md.append(f"**{text}**")
            elif tag_name == "dd":
                doc_md.append(f"{text}")
            else:
                doc_md.append(text)
            doc_md.append("")

    markdown_content = "\n".join(doc_md)
    file_path = OUTPUT_DIR / f"{doc_id}.md"

    # Idempotent write / overwrite
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    log.info(f"Saved: {file_path}")
    print(f"[INFO] Saved: {file_path}")
    return True


def main() -> None:
    """Main execution entry point."""
    success_count = 0
    fail_count = 0

    for doc_id, data in VEHICLES.items():
        if crawl_vehicle(doc_id, data):
            success_count += 1
        else:
            fail_count += 1

    print(f"Finished crawling. Success: {success_count}, Fail: {fail_count}")


if __name__ == "__main__":
    main()
