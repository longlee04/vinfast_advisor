"""
crawl_motobike_vin.py
=====================
3-Stage VinFast Electric Motorcycle Crawler

Stage 1 : Discovery            – discover all VinFast electric motorcycle detail page URLs
                                 using Selenium to click #cate_loadmore_pc ("Tải thêm sản phẩm")
Stage 2 : Detail Extraction    – visit each URL, scrape raw specs, text, pricing, images
Stage 3 : Data Normalization   – transform raw records -> unified electric motorcycle schema

Target  : https://xedienvietthanh.com/vinfast/
Output  : crawl/data/stage1_motobike_vin.json
          crawl/data/raw_motobike_vin.json
          crawl/data/raw_motobike_vin.jsonl
          crawl/data/motobike_vin.json
          crawl/data/motobike_vin.jsonl
          crawl/data/motobike_vin.csv
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# Try logger import from src if available (reference from crawl.py), else standard logging
try:
    from src.telemetry.logger import logger
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

# Selenium imports (reference from crawl.py format)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://xedienvietthanh.com/vinfast/"
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 1.0


def create_webdriver() -> webdriver.Chrome:
    """Khởi tạo Selenium Webdriver ở chế độ Headless."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


# ──────────────────────────────────────────────────────────────────────────────
# CRAWLER CLASS
# ──────────────────────────────────────────────────────────────────────────────

class CrawlMotobikeVin:
    """
    Class dùng để crawl dữ liệu tất cả xe máy điện VinFast từ https://xedienvietthanh.com/vinfast/
    Lưu dữ liệu vào thư mục crawl/data theo quy trình 3 stage.
    """

    def __init__(self, output_path: str | Path = OUTPUT_DIR, url: str = BASE_URL) -> None:
        self.url = url
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_soup(self, target_url: str) -> BeautifulSoup:
        """Fetch URL and return BeautifulSoup object."""
        logger.info(f"GET {target_url}")
        resp = self.session.get(target_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        time.sleep(DELAY_BETWEEN_REQUESTS)
        return BeautifulSoup(resp.text, "html.parser")

    # ──────────────────────────────────────────────────────────────────────────
    # STAGE 1 — Discovery (using Selenium to click #cate_loadmore_pc)
    # ──────────────────────────────────────────────────────────────────────────
    def stage1_discover(self) -> list[dict[str, str]]:
        """
        Stage 1: Electric Motorcycle Discovery
        Sử dụng Selenium mở trang landing page và liên tục click nút 'Tải thêm sản phẩm'
        (#cate_loadmore_pc) cho đến khi tải hết toàn bộ tất cả sản phẩm xe máy điện VinFast trên trang.
        """
        logger.info("=== STAGE 1: Electric Motorcycle Discovery (Selenium) ===")
        discovered: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        driver = create_webdriver()
        try:
            logger.info(f"Mở trang web: {self.url}")
            driver.get(self.url)
            time.sleep(3)

            wait = WebDriverWait(driver, 10)
            click_count = 0

            # Vòng lặp cuộn và click nút "Tải thêm sản phẩm" (#cate_loadmore_pc)
            while True:
                try:
                    # Scroll xuống cuối trang
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                    # Đợi nút "Tải thêm sản phẩm"
                    load_more = wait.until(
                        EC.presence_of_element_located((By.ID, "cate_loadmore_pc"))
                    )

                    # Nếu nút không còn hiển thị thì dừng
                    if not load_more.is_displayed():
                        logger.info("Nút 'Tải thêm sản phẩm' không còn hiển thị. Đã tải hết.")
                        break

                    # Scroll tới nút
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        load_more
                    )

                    # Đợi click được
                    wait.until(
                        EC.element_to_be_clickable((By.ID, "cate_loadmore_pc"))
                    )

                    # Đếm số lượng sản phẩm hiện tại
                    old_count = len(driver.find_elements(By.CSS_SELECTOR, "h5.item-title, div.product-wrapper, li.product"))

                    # Click bằng JavaScript (ổn định hơn click thường)
                    driver.execute_script("arguments[0].click();", load_more)
                    click_count += 1
                    time.sleep(2)

                    # Chờ cho tới khi có thêm sản phẩm
                    try:
                        wait.until(
                            lambda d: len(d.find_elements(By.CSS_SELECTOR, "h5.item-title, div.product-wrapper, li.product")) > old_count
                        )
                    except TimeoutException:
                        logger.info("Không có sản phẩm mới nào được tải thêm sau khi click. Kết thúc cuộn.")
                        break

                    new_count = len(driver.find_elements(By.CSS_SELECTOR, "h5.item-title, div.product-wrapper, li.product"))
                    logger.info(f"Click #{click_count}: Đã tải {new_count} sản phẩm (trước đó: {old_count})")

                except TimeoutException:
                    logger.info("Không còn sản phẩm để tải (TimeoutException).")
                    break

                except (ElementClickInterceptedException, StaleElementReferenceException):
                    continue

            # Phân tích toàn bộ DOM đã tải đầy đủ bằng BeautifulSoup
            soup = BeautifulSoup(driver.page_source, "html.parser")
            cards = soup.select("div.product-wrapper, li.product, div.col")
            if not cards:
                cards = soup.select("h5.item-title")

            for card in cards:
                a = card.find("a", href=True)
                if not a:
                    continue

                href = a.get("href", "").strip()
                if not href:
                    continue

                abs_url = urllib.parse.urljoin(self.url, href)
                if abs_url in seen_urls:
                    continue

                # Extract title from h5.item-title specifically to avoid status text ("Hết Hàng")
                h5 = card.find("h5", class_="item-title") or card.find("h5") or card.find("h3") or card.find("h4")
                if h5 and h5.get_text(strip=True):
                    name = h5.get_text(strip=True)
                else:
                    name = a.get_text(strip=True)

                if not name or name in ["Hết Hàng", "Đặt hàng", "Mặc định", "Mới"]:
                    name = self._extract_card_name(card)

                # Validation & Filtering Rules
                if not self._is_vinfast_motorcycle(name, abs_url):
                    continue

                seen_urls.add(abs_url)
                discovered.append({"name": name, "url": abs_url})
                logger.info(f"  Discovered ({len(discovered)}): {name} -> {abs_url}")

        finally:
            driver.quit()

        logger.info(f"Stage 1 complete. Discovered {len(discovered)} VinFast electric motorcycles.")
        return discovered

    def _is_vinfast_motorcycle(self, name: str, url: str) -> bool:
        """Check if a URL / name corresponds strictly to a VinFast electric motorcycle."""
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()
        name_lower = name.lower()

        # Must be on xedienvietthanh.com
        if "xedienvietthanh.com" not in parsed.netloc:
            return False

        # Exclude landing page itself and category pages
        if path.rstrip("/") in ["/vinfast", "/xe-may-dien"]:
            return False
        if any(c in path for c in ["/category/", "/danh-muc", "/tin-tuc", "/lien-he", "/cart", "/checkout"]):
            return False

        # Exclude standalone batteries, chargers, spare parts, helmets, accessories
        noise_keywords = [
            "ắc quy", "ac-quy", "sạc", "sac-", "bộ khóa", "bo-khoa",
            "dầu", "mũ", "tay ga", "dieu-toc", "điều tốc", "bánh", "lốp",
            "khuyen-mai", "tin-tuc", "chinh-sach"
        ]
        if any(kw in path for kw in ["ac-quy", "sac-", "bo-khoa", "dieu-toc", "tin-tuc"]) or \
           (path.startswith("/pin-") and "xe-may-dien" not in path):
            return False

        if any(kw in name_lower for kw in ["ắc quy", "bộ khóa", "tay ga", "điều tốc", "sạc xe", "sạc 48v"]) or \
           (name_lower.startswith("pin ") and "xe máy điện" not in name_lower):
            return False

        # Exclude other brands (Yadea, Espero, Nijia, Aima, Zoomer, Anbico, Dibao, Vespa)
        other_brands = ["yadea", "espero", "nijia", "aima", "zoomer", "anbico", "dibao", "roma"]
        if any(b in path or b in name_lower for b in other_brands):
            return False

        # Must contain vinfast or xe-may-dien in path/name
        if "vinfast" not in path and "vinfast" not in name_lower and "xe-may-dien" not in path:
            return False

        return True

    def _extract_card_name(self, card: Any) -> str:
        img = card.find("img")
        if img and img.get("alt", "").strip():
            return img["alt"].strip()
        h5 = card.find("h5") or card.find("h4") or card.find("h3")
        if h5 and h5.get_text(strip=True):
            return h5.get_text(strip=True)
        return card.get("href", "").strip("/").split("/")[-1].replace("-", " ").title()

    # ──────────────────────────────────────────────────────────────────────────
    # STAGE 2 — Detail Extraction
    # ──────────────────────────────────────────────────────────────────────────
    def stage2_extract(self, discovered_vehicles: list[dict[str, str]]) -> list[dict[str, Any]]:
        """
        Stage 2: Electric Motorcycle Detail Extraction
        Duyệt từng URL chi tiết, lấy toàn bộ nội dung thô:
        - product name, detail_link
        - hero_image
        - raw_specs (bảng/danh sách thông số kỹ thuật thô)
        - raw_text (toàn bộ nội dung văn bản)
        - pricing info
        """
        logger.info("=== STAGE 2: Electric Motorcycle Detail Extraction ===")
        raw_records: list[dict[str, Any]] = []

        for item in discovered_vehicles:
            name = item["name"]
            url = item["url"]

            try:
                soup = self.get_soup(url)
            except Exception as e:
                logger.error(f"  Failed to fetch {url}: {e}")
                raw_records.append({
                    "vehicle_name": name,
                    "detail_link": url,
                    "hero_image": None,
                    "raw_specs": {},
                    "raw_text": "",
                    "pricing": None,
                    "error": str(e),
                })
                continue

            # Update product name from H1 tag on detail page if H1 is valid
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                h1_text = h1.get_text(strip=True)
                if any(k in h1_text.lower() for k in ["vinfast", "xe", "klara", "evo", "feliz", "vento", "theon"]):
                    name = h1_text

            logger.info(f"Extracting detail: {name} ({url})")

            hero_image = self._extract_hero_image(soup, url)
            raw_specs = self._extract_raw_specs(soup)
            raw_text = soup.get_text("\n", strip=True)
            pricing = self._extract_pricing(soup)

            record = {
                "vehicle_name": name,
                "detail_link": url,
                "hero_image": hero_image,
                "raw_specs": raw_specs,
                "raw_text": raw_text,
                "pricing": pricing,
            }
            raw_records.append(record)
            logger.info(
                f"  Extracted OK – specs={len(raw_specs)}, "
                f"hero_image={'✓' if hero_image else '✗'}, "
                f"price={'✓' if pricing else '✗'}"
            )

        logger.info(f"Stage 2 complete. Extracted {len(raw_records)} records.")
        return raw_records

    def _extract_hero_image(self, soup: BeautifulSoup, base_url: str) -> str | None:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            return urllib.parse.urljoin(base_url, og_img["content"])

        selectors = [
            ".details-product img",
            ".product-image img",
            "img[class*='hero']",
            "img[class*='featured']",
            "article img",
        ]
        for sel in selectors:
            img = soup.select_one(sel)
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    return urllib.parse.urljoin(base_url, src)

        return None

    def _extract_raw_specs(self, soup: BeautifulSoup) -> dict[str, str]:
        specs: dict[str, str] = {}

        # 1. Standard spec list items: ul.parametdesc li, div.content-special li
        for li in soup.select("ul.parametdesc li, div.content-special li, .details-product li"):
            text = li.get_text(" ", strip=True)
            if ":" in text:
                parts = text.split(":", 1)
                k = parts[0].strip()
                v = parts[1].strip()
                if k and v and len(k) < 80:
                    specs[k] = v

        # 2. Table rows <tr> <td>
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) == 2:
                    k = cells[0].get_text(strip=True)
                    v = cells[1].get_text(strip=True)
                    if k and v and not any(w in k.lower() for w in ["thành tiền", "chuyển khoản", "hủy", "hình ảnh"]):
                        specs[k] = v

        return specs

    def _extract_pricing(self, soup: BeautifulSoup) -> dict[str, Any] | None:
        details_pro = soup.select_one(".details-pro, .price-box, .product-detail")
        if not details_pro:
            details_pro = soup

        old_price_val = None
        promo_price_val = None

        # Look for price elements in product header container
        old_elem = details_pro.select_one(".old-price, .product-price-old, del")
        sp_elem = details_pro.select_one(".special-price, .product-price, ins, .bk-product-price")

        if old_elem:
            old_price_val = self._parse_price_number(old_elem.get_text(strip=True))
        if sp_elem:
            promo_price_val = self._parse_price_number(sp_elem.get_text(strip=True))

        if old_price_val is None and promo_price_val is None:
            # Fallback: scan any price-like text in details area
            for p in details_pro.select(".price, .amount"):
                num = self._parse_price_number(p.get_text(strip=True))
                if num and num > 1_000_000:
                    promo_price_val = num
                    break

        if old_price_val is None and promo_price_val is not None:
            base_price = promo_price_val
            promotion_price = promo_price_val
        elif old_price_val is not None and promo_price_val is None:
            base_price = old_price_val
            promotion_price = old_price_val
        elif old_price_val is not None and promo_price_val is not None:
            base_price = old_price_val
            promotion_price = promo_price_val
        else:
            return None

        # Battery option heuristic from title / text
        full_text = soup.get_text().lower()
        h1_tag = soup.find("h1")
        title_text = h1_tag.get_text().lower() if h1_tag else ""

        if "thuê pin" in title_text or "thuê pin" in full_text[:500]:
            battery_option = "Subscription"
        elif any(k in title_text for k in ["kèm 1 pin", "kèm 2 pin", "kèm pin", "mua pin", "đứt pin"]):
            battery_option = "Included"
        elif "kèm pin" in full_text[:500]:
            battery_option = "Included"
        else:
            battery_option = "Subscription"

        return {
            "base_price": base_price,
            "promotion_price": promotion_price,
            "battery_option": battery_option,
            "currency": "VND",
        }

    def _parse_price_number(self, s: str) -> int | None:
        digits = re.sub(r"[^\d]", "", s)
        if digits:
            try:
                val = int(digits)
                return val if val > 100_000 else None
            except ValueError:
                return None
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # STAGE 3 — Normalization
    # ──────────────────────────────────────────────────────────────────────────
    def stage3_normalize(self, raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Stage 3: Electric Motorcycle Data Normalization
        Chuyển đổi dữ liệu thô Stage 2 thành schema chuẩn.
        """
        logger.info("=== STAGE 3: Data Normalization ===")
        normalized_list: list[dict[str, Any]] = []

        for raw in raw_records:
            norm = self._normalize_record(raw)
            normalized_list.append(norm)
            logger.info(
                f"  Normalized: {norm['brand']} {norm['model']} "
                f"(Variant: {norm['variant']}, Speed: {norm['max_speed']}, Range: {norm['range']})"
            )

        logger.info(f"Stage 3 complete. Normalized {len(normalized_list)} records.")
        return normalized_list

    def _normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        name = raw.get("vehicle_name", "")
        specs = raw.get("raw_specs", {})
        text = raw.get("raw_text", "")

        # ── 1. brand ──────────────────────────────────────────────────────────
        brand = "VinFast"

        # ── 2. model & variant ────────────────────────────────────────────────
        model, variant = self._parse_model_and_variant(name, raw.get("detail_link", ""))

        # ── 3. vehicle_type ───────────────────────────────────────────────────
        vehicle_type = "Electric Scooter"

        # ── 4. status ─────────────────────────────────────────────────────────
        status = "Available"

        # ── 5. year ───────────────────────────────────────────────────────────
        year = None
        m_year = re.search(r"\b(202[0-9])\b", name + " " + text[:300])
        if m_year:
            year = int(m_year.group(1))

        # ── 6. motor_power & max_power ────────────────────────────────────────
        motor_power, max_power = self._parse_power(specs)

        # ── 7. torque ─────────────────────────────────────────────────────────
        torque = self._parse_torque(text, specs)

        # ── 8. max_speed ──────────────────────────────────────────────────────
        max_speed = self._parse_max_speed(specs)

        # ── 9. battery fields ─────────────────────────────────────────────────
        b_type, b_cap, b_qty, b_rem = self._parse_battery(specs, text)

        # ── 10. range ─────────────────────────────────────────────────────────
        rng = self._parse_range(specs)

        # ── 11. charging_time ─────────────────────────────────────────────────
        charging_time = self._parse_charging_time(specs)

        # ── 12. charging_method ───────────────────────────────────────────────
        charging_method = "Home Charger"

        # ── 13. dimensions & weights ──────────────────────────────────────────
        weight = self._parse_weight(specs)
        max_load = self._parse_max_load(specs)
        seat_height = self._parse_seat_height(specs)
        wheel_size = self._parse_wheel_size(specs)

        # ── 14. brakes & suspensions ──────────────────────────────────────────
        front_brake, rear_brake = self._parse_brakes(specs)
        front_susp, rear_susp = self._parse_suspension(specs)

        # ── 15. smart_features ────────────────────────────────────────────────
        smart_features = self._parse_smart_features(text)

        return {
            "brand": brand,
            "model": model,
            "variant": variant,
            "vehicle_type": vehicle_type,
            "status": status,
            "year": year,
            "motor_power": motor_power,
            "max_power": max_power,
            "torque": torque,
            "max_speed": max_speed,
            "battery_type": b_type,
            "battery_capacity": b_cap,
            "battery_quantity": b_qty,
            "battery_removable": b_rem,
            "range": rng,
            "charging_time": charging_time,
            "charging_method": charging_method,
            "weight": weight,
            "max_load": max_load,
            "seat_height": seat_height,
            "wheel_size": wheel_size,
            "front_brake": front_brake,
            "rear_brake": rear_brake,
            "front_suspension": front_susp,
            "rear_suspension": rear_susp,
            "smart_features": smart_features,
            "pricing": raw.get("pricing"),
            "image": raw.get("hero_image"),
            "detail_link": raw.get("detail_link"),
        }

    def _parse_model_and_variant(self, name: str, url: str = "") -> tuple[str | None, str | None]:
        clean = re.sub(r"^(Xe\s+Máy\s+Điện|XE\s+MÁY\s+ĐIỆN|XE\s+ĐẠP\s+ĐIỆN)\s+", "", name, flags=re.I).strip()
        clean = re.sub(r"^VinFast\s+", "", clean, flags=re.I).strip()
        clean_no_bracket = re.sub(r"\(.*?\)", "", clean).strip()

        # If name is generic, derive from URL slug
        if clean_no_bracket in ["Hết Hàng", "Đặt hàng", "Mặc định", "Mới", ""] and url:
            slug = url.strip("/").split("/")[-1].replace("xe-may-dien-vinfast-", "").replace("xe-may-dien-", "")
            clean_no_bracket = slug.replace("-", " ").title()

        # Known models order from most specific to general
        known_models = [
            "Evo Grand Lite",
            "Evo Grand",
            "Evo 200 Lite",
            "Evo 200",
            "Evo Lite Neo",
            "Evo Lite",
            "Evo Neo",
            "Evo Max",
            "Evo",
            "Flazz Max",
            "Flazz",
            "Feliz Lite",
            "Feliz Neo",
            "Feliz II",
            "Feliz S",
            "Feliz",
            "Klara Neo",
            "Klara S",
            "Klara Lithium",
            "Klara",
            "Vento Neo",
            "Vento S",
            "Vento",
            "Theon S",
            "Theon",
            "Kinet",
            "Kyo",
            "Amio S2",
            "Amio S",
            "Amio",
            "Vero X",
            "Viper",
            "Motio",
            "ZGoo",
            "DrgnFly",
            "Tempest",
            "Impes",
            "Ludo",
        ]

        model = None
        for m in known_models:
            if re.search(r"\b" + re.escape(m) + r"\b", clean_no_bracket, re.I):
                model = m
                break

        if not model:
            model = clean_no_bracket or None

        # Variant extraction
        variant = None
        if "Thuê Pin" in name or "thue-pin" in url:
            variant = "Thuê Pin"
        elif "Kèm 1 Pin" in name or "Kèm pin" in name or "Mua 1 Pin" in name or "Kèm 2 Pin" in name or "kem-pin" in url:
            if "Kèm 2 Pin" in name or "2-pin" in url:
                variant = "Kèm 2 Pin"
            else:
                variant = "Kèm Pin"
        elif model == "Evo Grand Lite":
            variant = "Lite"
        elif model == "Evo Grand":
            variant = "Grand"
        elif model and "Lite" in model and model not in ["Evo Lite", "Evo Grand Lite", "Feliz Lite"]:
            variant = "Lite"
        elif model and "Neo" in model:
            variant = "Neo"
        elif model and "S" in model:
            variant = "S"

        return model, variant

    def _parse_power(self, specs: dict) -> tuple[dict | None, dict | None]:
        dc_text = specs.get("Động cơ xe") or specs.get("Động cơ") or ""
        if not dc_text:
            return None, None

        motor_power = None
        max_power = None

        m_nom = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:W|kW)", dc_text, re.I)
        if m_nom:
            raw_v = m_nom.group(1).replace(",", ".")
            if "." in raw_v and len(raw_v.split(".")[-1]) == 3:
                val = float(raw_v.replace(".", ""))
            else:
                val = float(raw_v)
            if val > 50:
                val = round(val / 1000.0, 2)
            motor_power = {"value": val, "unit": "kW"}

        m_max = re.search(r"(?:tối đa|max)\s*(\d+(?:[\.,]\d+)?)\s*(?:W|kW)", dc_text, re.I)
        if m_max:
            raw_v = m_max.group(1).replace(",", ".")
            if "." in raw_v and len(raw_v.split(".")[-1]) == 3:
                val_max = float(raw_v.replace(".", ""))
            else:
                val_max = float(raw_v)
            if val_max > 50:
                val_max = round(val_max / 1000.0, 2)
            max_power = {"value": val_max, "unit": "kW"}

        return motor_power, max_power

    def _parse_torque(self, text: str, specs: dict) -> dict | None:
        combined = text + " " + " ".join(specs.values())
        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*Nm", combined, re.I)
        if m:
            return {"value": float(m.group(1).replace(",", ".")), "unit": "Nm"}
        return None

    def _parse_max_speed(self, specs: dict) -> dict | None:
        spd_text = specs.get("Vận tốc tối đa") or specs.get("Tốc độ tối đa") or ""
        if spd_text:
            m = re.search(r"(\d+)\s*km/h", spd_text, re.I)
            if m:
                return {"value": int(m.group(1)), "unit": "km/h"}
        return None

    def _parse_battery(self, specs: dict, text: str) -> tuple[str | None, dict | None, int | None, bool | None]:
        bat_text = specs.get("Loại acquy") or specs.get("Pin") or specs.get("Loại acquy / Pin") or ""

        # Battery Type
        b_type = None
        if "LFP" in bat_text.upper():
            b_type = "LFP"
        elif "LITHIUM" in bat_text.upper() or "PIN" in bat_text.upper():
            b_type = "Lithium-ion"
        elif "ACQUY" in bat_text.upper() or "ẮC QUY" in bat_text.upper():
            b_type = "Lead Acid"

        # Battery Capacity
        b_cap = None
        m_cap = re.search(r"(\d+(?:[\.,]\d+)?)\s*kWh", bat_text, re.I)
        if m_cap:
            b_cap = {"value": float(m_cap.group(1).replace(",", ".")), "unit": "kWh"}

        # Battery Quantity
        b_qty = None
        m_qty = re.search(r"(01|02|1|2)\s*Pin", bat_text, re.I)
        if m_qty:
            b_qty = int(m_qty.group(1))

        # Battery Removable
        b_rem = None
        combined = bat_text.lower() + " " + text.lower()
        if "tháo rời" in combined or "tháo pin" in combined:
            b_rem = True
        elif "cố định" in combined:
            b_rem = False

        return b_type, b_cap, b_qty, b_rem

    def _parse_range(self, specs: dict) -> dict | None:
        rng_text = specs.get("Quãng đường") or specs.get("Tầm xa") or ""
        if rng_text:
            m = re.search(r"(\d+)\s*km", rng_text, re.I)
            if m:
                return {"value": int(m.group(1)), "unit": "km"}
        return None

    def _parse_charging_time(self, specs: dict) -> dict | None:
        chg_text = specs.get("Thời gian sạc") or ""
        if not chg_text:
            return None

        if "4h30" in chg_text or "4 giờ 30" in chg_text or "4.5" in chg_text:
            return {"value": 4.5, "unit": "hour"}
        if "6 tiếng 30" in chg_text or "6h30" in chg_text or "6.5" in chg_text:
            return {"value": 6.5, "unit": "hour"}

        m_range = re.search(r"(\d+)\s*-\s*(\d+)\s*tiếng", chg_text, re.I)
        if m_range:
            avg = (float(m_range.group(1)) + float(m_range.group(2))) / 2.0
            return {"value": avg, "unit": "hour"}

        m_single = re.search(r"(\d+)\s*(?:tiếng|h)", chg_text, re.I)
        if m_single:
            return {"value": float(m_single.group(1)), "unit": "hour"}

        return None

    def _parse_weight(self, specs: dict) -> dict | None:
        wt_text = specs.get("Trọng lượng xe") or specs.get("Trọng lượng") or ""
        if wt_text:
            m = re.search(r"(\d+)\s*kg", wt_text, re.I)
            if m:
                return {"value": int(m.group(1)), "unit": "kg"}
        return None

    def _parse_max_load(self, specs: dict) -> dict | None:
        load_text = specs.get("Chở vật nặng") or specs.get("Tải trọng") or ""
        if load_text:
            m = re.search(r"(\d+)\s*kg", load_text, re.I)
            if m:
                return {"value": int(m.group(1)), "unit": "kg"}
        return None

    def _parse_seat_height(self, specs: dict) -> dict | None:
        st_text = specs.get("Chiều cao yên xe") or specs.get("Chiều cao yên") or ""
        if st_text:
            m = re.search(r"(\d+)\s*mm", st_text, re.I)
            if m:
                return {"value": int(m.group(1)), "unit": "mm"}
        return None

    def _parse_wheel_size(self, specs: dict) -> int | None:
        wh_text = specs.get("Đường kính bánh xe") or specs.get("Bánh xe") or ""
        if wh_text:
            m_inch = re.search(r"(\d+)(?:[\"”\']|\s*inch)", wh_text, re.I)
            if m_inch:
                return int(m_inch.group(1))
            m_tire = re.search(r"-\s*(\d{2})\b", wh_text)
            if m_tire:
                return int(m_tire.group(1))
        return None

    def _parse_brakes(self, specs: dict) -> tuple[str | None, str | None]:
        brk_text = specs.get("Phanh") or ""
        front_brake = None
        rear_brake = None

        if brk_text:
            lower = brk_text.lower()
            if "phanh đĩa trước" in lower or "đĩa trước" in lower:
                front_brake = "Disc"
            elif "phanh cơ trước" in lower or "cơ trước" in lower:
                front_brake = "Drum"

            if "phanh cơ sau" in lower or "cơ sau" in lower:
                rear_brake = "Drum"
            elif "phanh đĩa sau" in lower or "đĩa sau" in lower:
                rear_brake = "Disc"

            if "ABS" in brk_text.upper():
                front_brake = "ABS"
            elif "CBS" in brk_text.upper():
                front_brake = "CBS"

        return front_brake, rear_brake

    def _parse_suspension(self, specs: dict) -> tuple[str | None, str | None]:
        gx_text = specs.get("Giảm xóc") or ""
        front_susp = None
        rear_susp = None

        if gx_text:
            if ";" in gx_text:
                parts = gx_text.split(";", 1)
                front_susp = parts[0].strip()
                rear_susp = parts[1].strip()
            else:
                front_susp = gx_text.strip()

        return front_susp, rear_susp

    def _parse_smart_features(self, text: str) -> list[str] | None:
        features = []
        lower = text.lower()

        if "gps" in lower or "định vị" in lower:
            features.append("GPS")
        if "bluetooth" in lower:
            features.append("Bluetooth")
        if "esim" in lower:
            features.append("eSIM")
        if "app" in lower or "ứng dụng" in lower:
            features.append("Mobile App")
        if "chống trộm" in lower or "báo động" in lower:
            features.append("Anti Theft")
        if "tự ngắt" in lower:
            features.append("Auto Shutoff Charger")

        return features if features else None

    # ──────────────────────────────────────────────────────────────────────────
    # PIPELINE RUNNER
    # ──────────────────────────────────────────────────────────────────────────
    def run(self) -> None:
        """Run full 3-stage crawling pipeline."""
        logger.info("Starting VinFast Electric Motorcycle Crawler Pipeline")
        logger.info(f"Target URL: {self.url}")

        # ── Stage 1: Discovery (Selenium + cate_loadmore_pc) ──────────────────
        discovered = self.stage1_discover()
        stage1_path = self.output_path / "stage1_motobike_vin.json"
        stage1_path.write_text(json.dumps(discovered, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Stage 1 output saved -> {stage1_path}")

        if not discovered:
            logger.error("No motorcycles discovered in Stage 1. Aborting.")
            return

        # ── Stage 2: Detail Extraction ────────────────────────────────────────
        raw_records = self.stage2_extract(discovered)
        raw_json_path = self.output_path / "raw_motobike_vin.json"
        raw_jsonl_path = self.output_path / "raw_motobike_vin.jsonl"

        raw_json_path.write_text(json.dumps(raw_records, ensure_ascii=False, indent=2), encoding="utf-8")
        with raw_jsonl_path.open("w", encoding="utf-8") as f:
            for r in raw_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        logger.info(f"Stage 2 output saved -> {raw_json_path} & {raw_jsonl_path}")

        # ── Stage 3: Data Normalization ───────────────────────────────────────
        normalized = self.stage3_normalize(raw_records)
        norm_json_path = self.output_path / "motobike_vin.json"
        norm_jsonl_path = self.output_path / "motobike_vin.jsonl"
        norm_csv_path = self.output_path / "motobike_vin.csv"

        norm_json_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        with norm_jsonl_path.open("w", encoding="utf-8") as f:
            for record in normalized:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Stage 3 output saved -> {norm_json_path} & {norm_jsonl_path}")

        # Optional CSV saving (similar to crawl.py)
        try:
            import pandas as pd
            df = pd.DataFrame(normalized)
            df.to_csv(norm_csv_path, index=False)
            logger.info(f"Stage 3 CSV saved -> {norm_csv_path}")
        except Exception as e:
            logger.warning(f"Could not save CSV via pandas: {e}")

        logger.info(f"Pipeline finished! Successfully processed {len(normalized)} VinFast electric motorcycles.")

        # Summary Table Print
        print("\n" + "=" * 70)
        print(f" VinFast Electric Motorcycle Crawler — {len(normalized)} motorcycles")
        print("=" * 70)
        for item in normalized:
            price_info = item.get("pricing") or {}
            promo = price_info.get("promotion_price")
            p_str = f"{promo:,} VND" if promo else "Contact"
            sp = item.get("max_speed") or {}
            spd = f"{sp.get('value')} km/h" if sp.get("value") else "N/A"
            rg = item.get("range") or {}
            range_str = f"{rg.get('value')} km" if rg.get("value") else "N/A"
            print(
                f"  {item['brand']} {str(item['model']):<18} "
                f"[{str(item['variant']) or 'Standard':<10}] "
                f"Price: {p_str:>16} | Speed: {spd:>8} | Range: {range_str:>8}"
            )
        print("=" * 70)
        print(f"  Output directory: {self.output_path.resolve()}")
        print("=" * 70 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    crawler = CrawlMotobikeVin()
    crawler.run()
