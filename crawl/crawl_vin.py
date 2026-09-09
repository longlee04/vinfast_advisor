"""
crawl_vin.py
============
3-Stage VinFast Electric Vehicle Crawler

Stage 1 : Vehicle Discovery       – find all EV detail-page URLs
Stage 2 : Vehicle Detail Extraction – visit each URL, scrape raw data
Stage 3 : Data Normalization       – transform raw records → unified schema

Target  : https://vinfastvietnam.com.vn/o-to-dien-vinfast/
Output  : vinfast_vehicles.json  (normalized JSON array)
          vinfast_vehicles.jsonl (one normalized JSON object per line)
          vinfast_raw.json       (raw Stage-2 records, for debugging)
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://vinfastvietnam.com.vn/o-to-dien-vinfast/"
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 30       # seconds
DELAY_BETWEEN_REQUESTS = 1 # seconds – be polite to the server

logging.basicConfig(
    filename="logs/app.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    """Fetch a URL and return a BeautifulSoup object."""
    log.info("GET %s", url)
    resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    time.sleep(DELAY_BETWEEN_REQUESTS)
    return BeautifulSoup(resp.text, "html.parser")


def absolute_url(href: str, base: str) -> str:
    """Ensure href is an absolute URL."""
    return urllib.parse.urljoin(base, href)


def is_vehicle_link(href: str) -> bool:
    """
    Heuristic: a vehicle detail link contains a slug like /vf-3/, /vf-8/,
    /vf-e34/, etc. and is NOT a category, blog, or utility page.
    """
    if not href:
        return False
    parsed = urllib.parse.urlparse(href)
    path = parsed.path.lower().strip("/")

    # Must be on the same domain
    if parsed.netloc and "vinfastvietnam.com.vn" not in parsed.netloc:
        return False

    # Must look like a vehicle page
    vehicle_pattern = re.compile(
        r"(vf[\-_]?\d+|vf[\-_]?e\d+|vf[\-_]?wild|vf[\-_]?lux)", re.IGNORECASE
    )
    if not vehicle_pattern.search(path):
        return False

    # Exclude noise
    noise_words = [
        "tin-tuc", "news", "blog", "phu-kien", "khuyen-mai",
        "promotion", "accessories", "dich-vu", "service",
        "lien-he", "contact", "careers", "tuyen-dung",
    ]
    if any(w in path for w in noise_words):
        return False

    return True


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 1 – Vehicle Discovery
# ──────────────────────────────────────────────────────────────────────────────

def stage1_discover_vehicles(session: requests.Session) -> list[dict]:
    """
    Open the landing page, find every EV vehicle card, and return a list of:
        {"name": "VinFast VF 3", "url": "https://..."}

    Rules (from system_prompt.md Stage 1):
    - Follow only links that lead to an individual vehicle page.
    - Ignore navigation menus, footer, blog, banners, promotions, accessories.
    - No duplicate links.
    - Every URL must correspond to a vehicle detail page.
    """
    log.info("=== STAGE 1: Vehicle Discovery ===")
    soup = get_soup(BASE_URL, session)

    seen_urls: set[str] = set()
    vehicles: list[dict] = []

    # ── Strategy A: look for <a> tags inside article/card/product wrappers ──
    card_selectors = [
        "article a[href]",
        ".product a[href]",
        ".vehicle-card a[href]",
        ".car-item a[href]",
        ".xe-dien a[href]",
        ".item a[href]",
        '[class*="product"] a[href]',
        '[class*="vehicle"] a[href]',
        '[class*="car-"] a[href]',
        '[class*="item"] a[href]',
    ]

    anchors: list[Any] = []
    for selector in card_selectors:
        anchors.extend(soup.select(selector))

    # ── Strategy B: fallback – scan ALL anchors on the page ──
    if not anchors:
        log.warning("No card-level anchors found; falling back to all <a> tags.")
        anchors = soup.find_all("a", href=True)

    for tag in anchors:
        href = tag.get("href", "")
        url = absolute_url(href, BASE_URL)

        if url in seen_urls:
            continue
        if not is_vehicle_link(url):
            continue

        # Extract the visible name from the anchor or nearest heading
        name = _extract_vehicle_name(tag)
        if not name:
            # Derive name from URL slug as last resort
            slug = urllib.parse.urlparse(url).path.strip("/").split("/")[-1]
            name = slug.replace("-", " ").title()

        seen_urls.add(url)
        vehicles.append({"name": name, "url": url})
        log.info("  Found: %s → %s", name, url)

    log.info("Stage 1 complete. %d vehicles discovered.", len(vehicles))
    return vehicles


def _extract_vehicle_name(anchor_tag: Any) -> str:
    """
    Try multiple strategies to get the vehicle name from an <a> tag context.
    """
    # 1. alt text on an <img> inside the anchor
    img = anchor_tag.find("img")
    if img and img.get("alt", "").strip():
        alt = img["alt"].strip()
        if re.search(r"VF|VinFast", alt, re.IGNORECASE):
            return alt

    # 2. Nearest heading sibling / parent
    for heading_tag in ("h1", "h2", "h3", "h4"):
        # inside the anchor itself
        h = anchor_tag.find(heading_tag)
        if h and h.get_text(strip=True):
            return h.get_text(strip=True)

    # 3. Parent card's heading
    parent = anchor_tag.parent
    for _ in range(5):  # traverse up to 5 levels
        if parent is None:
            break
        for heading_tag in ("h1", "h2", "h3", "h4"):
            h = parent.find(heading_tag)
            if h and h.get_text(strip=True):
                text = h.get_text(strip=True)
                if re.search(r"VF|VinFast", text, re.IGNORECASE):
                    return text
        parent = parent.parent

    # 4. Anchor text itself
    text = anchor_tag.get_text(strip=True)
    if re.search(r"VF|VinFast", text, re.IGNORECASE):
        return text

    # 5. title attribute
    if anchor_tag.get("title", "").strip():
        return anchor_tag["title"].strip()

    return ""


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 2 – Vehicle Detail Extraction
# ──────────────────────────────────────────────────────────────────────────────

def stage2_extract_details(
    vehicles: list[dict], session: requests.Session
) -> list[dict]:
    """
    Visit every vehicle URL exactly once and extract:
      - vehicle_name, detail_link
      - hero_image URL
      - raw_specs  (dict of all spec-table key→value pairs)
      - raw_text   (all visible text on the page)
      - raw_pricing (list of price strings found)

    Rules (from system_prompt.md Stage 2):
    - Read the ENTIRE page (headings, paragraphs, features, specs, images, pricing).
    - Visit every URL exactly once.
    - Never skip a vehicle.
    - Missing fields → null.
    - Never hallucinate values.
    """
    log.info("=== STAGE 2: Vehicle Detail Extraction ===")
    raw_records: list[dict] = []

    for vehicle in vehicles:
        name = vehicle["name"]
        url = vehicle["url"]
        log.info("Extracting: %s (%s)", name, url)

        try:
            soup = get_soup(url, session)
        except Exception as exc:
            log.error("  Failed to fetch %s: %s", url, exc)
            raw_records.append({
                "vehicle_name": name,
                "detail_link": url,
                "hero_image": None,
                "raw_specs": {},
                "raw_text": "",
                "raw_pricing": [],
                "error": str(exc),
            })
            continue

        record: dict[str, Any] = {
            "vehicle_name": name,
            "detail_link": url,
            "hero_image": _extract_hero_image(soup, url),
            "raw_specs": _extract_specs(soup),
            "raw_text": _extract_full_text(soup),
            "raw_pricing": _extract_pricing_strings(soup),
        }
        raw_records.append(record)
        log.info(
            "  OK – specs=%d  pricing=%d  image=%s",
            len(record["raw_specs"]),
            len(record["raw_pricing"]),
            "✓" if record["hero_image"] else "✗",
        )

    log.info("Stage 2 complete. %d records extracted.", len(raw_records))
    return raw_records


def _extract_hero_image(soup: BeautifulSoup, base_url: str) -> str | None:
    """Return the hero / main image URL of the vehicle page."""
    # Common hero image patterns
    selectors = [
        'meta[property="og:image"]',
        'img[class*="hero"]',
        'img[class*="banner"]',
        'img[class*="main"]',
        'img[class*="featured"]',
        ".hero img",
        ".banner img",
        "#hero img",
        "header img",
    ]

    # 1. Open Graph image (most reliable)
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return absolute_url(og["content"], base_url)

    # 2. Structured selectors
    for sel in selectors[1:]:
        tag = soup.select_one(sel)
        if tag:
            src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
            if src:
                return absolute_url(src, base_url)

    # 3. First large image on the page (width hint via attributes)
    for img in soup.find_all("img"):
        width = img.get("width", "0")
        try:
            if int(str(width).replace("px", "").strip()) >= 600:
                src = img.get("src") or img.get("data-src")
                if src:
                    return absolute_url(src, base_url)
        except (ValueError, TypeError):
            pass

    return None


def _extract_specs(soup: BeautifulSoup) -> dict[str, str]:
    """
    Extract all specification key-value pairs from tables, dl/dt/dd lists,
    and common spec-block layouts.
    """
    specs: dict[str, str] = {}

    # ── HTML <table> rows ──
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                if key:
                    specs[key] = val
            elif len(cells) >= 3:
                # First column is header, rest are values per variant
                key = cells[0].get_text(strip=True)
                vals = " / ".join(c.get_text(strip=True) for c in cells[1:] if c.get_text(strip=True))
                if key:
                    specs[key] = vals

    # ── <dl><dt><dd> definition lists ──
    for dl in soup.find_all("dl"):
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            key = dt.get_text(strip=True)
            val = dd.get_text(strip=True)
            if key:
                specs[key] = val

    # ── Common class-based spec rows ──
    spec_row_selectors = [
        '[class*="spec-row"]',
        '[class*="spec-item"]',
        '[class*="specification"]',
        '[class*="thong-so"]',
        '[class*="tech-spec"]',
    ]
    for sel in spec_row_selectors:
        for item in soup.select(sel):
            texts = [t.strip() for t in item.stripped_strings]
            if len(texts) >= 2:
                specs[texts[0]] = " ".join(texts[1:])

    return specs


def _extract_full_text(soup: BeautifulSoup) -> str:
    """
    Extract all visible text from the page, excluding nav/footer noise.
    """
    # Remove noisy elements
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()

    lines: list[str] = []
    for elem in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "dd", "dt", "span"]
    ):
        text = elem.get_text(" ", strip=True)
        if text and len(text) > 3:
            lines.append(text)

    return "\n".join(lines)


def _extract_pricing_strings(soup: BeautifulSoup) -> list[str]:
    """
    Extract all price-like strings from the page (VND / đồng / giá).
    """
    price_pattern = re.compile(
        r"(?:[\d\.]+\s*(?:tỷ|triệu|đồng|VNĐ|VND))|(?:giá[:\s]+[\d\.,]+)",
        re.IGNORECASE | re.UNICODE,
    )
    full_text = soup.get_text(" ")
    return price_pattern.findall(full_text)


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 3 – Data Normalization
# ──────────────────────────────────────────────────────────────────────────────

# Unified output schema (all fields default to None)
EMPTY_SCHEMA: dict[str, Any] = {
    "brand": None,
    "model": None,
    "variant": None,
    "body_type": None,
    "year": None,
    "status": None,
    "range": None,
    "efficiency": None,
    "weight": None,
    "acceleration_0_100": None,
    "one_stop_range": None,
    "battery": None,
    "fastcharge": None,
    "towing": None,
    "cargo_volume": None,
    "price_per_range": None,
    "pricing": None,
    "image": None,
    "detail_link": None,
}


def stage3_normalize(raw_records: list[dict]) -> list[dict]:
    """
    Transform raw Stage-2 records into the predefined unified vehicle schema.

    Rules (from system_prompt.md Stage 3):
    - Do NOT access the website.
    - Use ONLY raw_extracted data as source of truth.
    - Missing fields → null.
    - Never hallucinate values.
    - Normalize units.
    - Every object follows the schema exactly.
    """
    log.info("=== STAGE 3: Data Normalization ===")
    normalized: list[dict] = []

    for raw in raw_records:
        record = dict(EMPTY_SCHEMA)  # fresh copy
        specs: dict[str, str] = raw.get("raw_specs", {})
        raw_text: str = raw.get("raw_text", "")
        pricing_strs: list[str] = raw.get("raw_pricing", [])

        # ── brand ──────────────────────────────────────────────────────────────
        record["brand"] = "VinFast"

        # ── detail_link ────────────────────────────────────────────────────────
        record["detail_link"] = raw.get("detail_link")

        # ── image ──────────────────────────────────────────────────────────────
        record["image"] = raw.get("hero_image")

        # ── model & variant ───────────────────────────────────────────────────
        vehicle_name: str = raw.get("vehicle_name", "")
        record["model"], record["variant"] = _parse_model_variant(vehicle_name)

        # ── body_type ──────────────────────────────────────────────────────────
        record["body_type"] = _normalize_body_type(specs, raw_text)

        # ── year ───────────────────────────────────────────────────────────────
        record["year"] = _extract_year(specs, raw_text)

        # ── status ─────────────────────────────────────────────────────────────
        record["status"] = _normalize_status(raw_text)

        # ── range ──────────────────────────────────────────────────────────────
        record["range"] = _normalize_range(specs, raw_text)

        # ── efficiency ─────────────────────────────────────────────────────────
        record["efficiency"] = _normalize_efficiency(specs, raw_text)

        # ── weight ─────────────────────────────────────────────────────────────
        record["weight"] = _normalize_weight(specs, raw_text)

        # ── acceleration_0_100 ─────────────────────────────────────────────────
        record["acceleration_0_100"] = _normalize_acceleration(specs, raw_text)

        # ── battery ────────────────────────────────────────────────────────────
        record["battery"] = _normalize_battery(specs, raw_text)

        # ── fastcharge ─────────────────────────────────────────────────────────
        record["fastcharge"] = _normalize_fastcharge(specs, raw_text)

        # ── towing ─────────────────────────────────────────────────────────────
        record["towing"] = _normalize_towing(specs, raw_text)

        # ── cargo_volume ───────────────────────────────────────────────────────
        record["cargo_volume"] = _normalize_cargo(specs, raw_text)

        # ── pricing ────────────────────────────────────────────────────────────
        record["pricing"] = _normalize_pricing(pricing_strs, raw_text)

        # ── price_per_range ────────────────────────────────────────────────────
        record["price_per_range"] = _calc_price_per_range(
            record["pricing"], record["range"]
        )

        normalized.append(record)
        log.info(
            "  Normalized: %s %s (%s)",
            record["brand"],
            record["model"],
            record["variant"] or "—",
        )

    log.info("Stage 3 complete. %d records normalized.", len(normalized))
    return normalized


# ── Normalization helpers ──────────────────────────────────────────────────────

def _parse_model_variant(name: str) -> tuple[str | None, str | None]:
    """
    'VinFast VF 3'            → ('VF 3', None)
    'VinFast VF 8 All New'    → ('VF 8', 'All New')
    'VinFast VF e34 Eco'      → ('VF e34', 'Eco')
    'vf2' (from slug)         → ('VF 2', None)
    """
    name = name.strip()
    # Remove brand prefix
    name = re.sub(r"^VinFast\s+", "", name, flags=re.IGNORECASE)

    # Normalize compact slug formats: vf2 → VF 2, vfe34 → VF e34
    slug_match = re.match(r"^vf(e?)(\d+)$", name, re.IGNORECASE)
    if slug_match:
        prefix = "e" if slug_match.group(1).lower() == "e" else ""
        num = slug_match.group(2)
        name = f"VF {prefix}{num}"

    # Capitalize VF prefix correctly: vf 3 → VF 3
    name = re.sub(r"^vf\s+", "VF ", name, flags=re.IGNORECASE)

    # Known variant suffixes
    variant_re = re.compile(
        r"\s+(Eco|Plus|Extended\s+Range|All\s+New|Pro|Standard|Base|Luxury|Sport)$",
        re.IGNORECASE,
    )
    m = variant_re.search(name)
    if m:
        variant = m.group(1).strip()
        model = name[: m.start()].strip()
        return model or None, variant or None

    return name or None, None


def _normalize_body_type(specs: dict, text: str) -> str | None:
    keywords = {
        "Mini Hatchback": ["mini hatchback"],
        "Hatchback": ["hatchback"],
        "SUV": ["suv", "crossover"],
        "Pickup": ["pickup", "bán tải"],
        "MPV": ["mpv", "minivan"],
        "City Car": ["city car", "đô thị"],
        "Sedan": ["sedan"],
        "Compact SUV": ["compact suv"],
    }
    combined = (text + " " + " ".join(specs.values())).lower()
    for body, patterns in keywords.items():
        if any(p in combined for p in patterns):
            return body
    return None


def _extract_year(specs: dict, text: str) -> int | None:
    """
    Return launch/model year ONLY if explicitly stated in spec table.
    Do NOT pick up years from copyright notices, dates, or body text.
    """
    year_keys = re.compile(r"năm sản xuất|model year|năm ra mắt|launch year|year", re.IGNORECASE)
    for key, val in specs.items():
        if year_keys.search(key):
            m = re.search(r"(20\d{2})", val)
            if m:
                return int(m.group(1))
    # Only accept explicit year spec patterns like "Năm: 2024" in text
    m = re.search(r"(?:năm sản xuất|model year|năm ra mắt)[^\d]*(20\d{2})", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _normalize_status(text: str) -> str | None:
    t = text.lower()
    if any(w in t for w in ["sắp ra mắt", "upcoming", "sắp có", "coming soon"]):
        return "Upcoming"
    if any(w in t for w in ["đặt cọc", "pre-order", "đặt trước"]):
        return "Pre-order"
    if any(w in t for w in ["ngừng sản xuất", "discontinued"]):
        return "Discontinued"
    if any(w in t for w in ["concept", "khái niệm"]):
        return "Concept"
    if any(w in t for w in ["mua ngay", "order now", "đặt mua", "liên hệ mua"]):
        return "Available"
    return None


def _normalize_range(specs: dict, text: str) -> dict | None:
    """Extract range value (km) and testing cycle."""
    range_keys = re.compile(r"phạm vi|tầm xa|quãng đường|range|hành trình", re.IGNORECASE)
    cycle_map = {
        "WLTP": re.compile(r"WLTP", re.IGNORECASE),
        "NEDC": re.compile(r"NEDC", re.IGNORECASE),
        "CLTC": re.compile(r"CLTC", re.IGNORECASE),
        "EPA": re.compile(r"EPA", re.IGNORECASE),
    }

    # Search spec table first
    for key, val in specs.items():
        if range_keys.search(key):
            m = re.search(r"(\d[\d\s,\.]*)\s*km", val, re.IGNORECASE)
            if m:
                value = _parse_number(m.group(1))
                cycle = _detect_cycle(val + key, cycle_map)
                return {"value": value, "unit": "km", "cycle": cycle or "Unknown"}

    # Fallback: scan full text
    pattern = re.compile(
        r"(?:tầm xa|phạm vi|range|quãng đường)[^\d]*(\d[\d\s,\.]*)\s*km",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if m:
        value = _parse_number(m.group(1))
        cycle = _detect_cycle(text[max(0, m.start() - 50): m.end() + 50], cycle_map)
        return {"value": value, "unit": "km", "cycle": cycle or "Unknown"}

    return None


def _normalize_efficiency(specs: dict, text: str) -> dict | None:
    pattern = re.compile(r"(\d+[\.,]?\d*)\s*kWh\s*/\s*100\s*km", re.IGNORECASE)
    for val in specs.values():
        m = pattern.search(val)
        if m:
            return {"value": _parse_number(m.group(1)), "unit": "kWh/100 km"}
    m = pattern.search(text)
    if m:
        return {"value": _parse_number(m.group(1)), "unit": "kWh/100 km"}
    return None


def _normalize_weight(specs: dict, text: str) -> dict | None:
    weight_keys = re.compile(r"khối lượng|trọng lượng|weight|gross weight", re.IGNORECASE)
    for key, val in specs.items():
        if weight_keys.search(key):
            m = re.search(r"(\d[\d\s,\.]+)\s*kg", val, re.IGNORECASE)
            if m:
                return {"value": _parse_number(m.group(1)), "unit": "kg"}
    pattern = re.compile(r"(\d[\d\s,\.]+)\s*kg", re.IGNORECASE)
    m = pattern.search(text)
    if m:
        return {"value": _parse_number(m.group(1)), "unit": "kg"}
    return None


def _normalize_acceleration(specs: dict, text: str) -> dict | None:
    accel_keys = re.compile(r"tăng tốc|0[-–]100|acceleration", re.IGNORECASE)
    pattern = re.compile(r"(\d+[\.,]?\d*)\s*s(?:ec|econds|giây)?", re.IGNORECASE)
    for key, val in specs.items():
        if accel_keys.search(key):
            m = pattern.search(val)
            if m:
                return {"value": _parse_number(m.group(1)), "unit": "s"}
    m = re.search(
        r"(?:tăng tốc|0[-–]100|acceleration)[^\d]*(\d+[\.,]?\d*)\s*s",
        text,
        re.IGNORECASE,
    )
    if m:
        return {"value": _parse_number(m.group(1)), "unit": "s"}
    return None


def _normalize_battery(specs: dict, text: str) -> dict | None:
    battery_keys = re.compile(r"pin|battery|dung lượng", re.IGNORECASE)
    pattern = re.compile(r"(\d+[\.,]?\d*)\s*kWh", re.IGNORECASE)
    for key, val in specs.items():
        if battery_keys.search(key):
            m = pattern.search(val)
            if m:
                return {"capacity": _parse_number(m.group(1)), "unit": "kWh"}
    m = pattern.search(text)
    if m:
        return {"capacity": _parse_number(m.group(1)), "unit": "kWh"}
    return None


def _normalize_fastcharge(specs: dict, text: str) -> dict | None:
    charge_keys = re.compile(r"sạc nhanh|fast.?charge|dc charge|sạc dc", re.IGNORECASE)
    power_pattern = re.compile(r"(\d+[\.,]?\d*)\s*kW", re.IGNORECASE)
    time_pattern = re.compile(r"(\d+)\s*(?:phút|min)", re.IGNORECASE)
    window_pattern = re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*%", re.IGNORECASE)

    power_kw = None
    charging_time = None
    charging_window = None

    for key, val in specs.items():
        if charge_keys.search(key):
            m = power_pattern.search(val)
            if m:
                power_kw = _parse_number(m.group(1))
            t = time_pattern.search(val)
            if t:
                charging_time = f"{t.group(1)} min"
            w = window_pattern.search(val)
            if w:
                charging_window = f"{w.group(1)}-{w.group(2)}%"

    if power_kw is None:
        # Scan text
        chunk = re.search(
            r"(?:sạc nhanh|fast.?charge)[^\n]{0,200}", text, re.IGNORECASE
        )
        if chunk:
            snippet = chunk.group(0)
            m = power_pattern.search(snippet)
            if m:
                power_kw = _parse_number(m.group(1))
            t = time_pattern.search(snippet)
            if t:
                charging_time = f"{t.group(1)} min"
            w = window_pattern.search(snippet)
            if w:
                charging_window = f"{w.group(1)}-{w.group(2)}%"

    if power_kw is not None:
        return {
            "power_kw": power_kw,
            "charging_time": charging_time,
            "charging_window": charging_window,
        }
    return None


def _normalize_towing(specs: dict, text: str) -> dict | None:
    tow_keys = re.compile(r"kéo|towing|tải kéo", re.IGNORECASE)
    for key, val in specs.items():
        if tow_keys.search(key):
            m = re.search(r"(\d[\d,\.]+)\s*kg", val, re.IGNORECASE)
            if m:
                return {"value": _parse_number(m.group(1)), "unit": "kg"}
    return None


def _normalize_cargo(specs: dict, text: str) -> dict | None:
    cargo_keys = re.compile(r"khoang hành lý|cốp|cargo|luggage|trunk", re.IGNORECASE)
    std = None
    mx = None
    for key, val in specs.items():
        if cargo_keys.search(key):
            nums = re.findall(r"(\d[\d,\.]*)\s*(?:lít|l\b|L)", val, re.IGNORECASE)
            if nums:
                std = _parse_number(nums[0])
                if len(nums) > 1:
                    mx = _parse_number(nums[1])
    if std is not None:
        return {"standard_l": std, "maximum_l": mx}
    return None


def _normalize_pricing(pricing_strs: list[str], raw_text: str) -> dict | None:
    """
    Extract VND prices and return structured pricing dict.

    Parse order (most → least reliable):
    1. Dotted VND format from raw_pricing: "853.100.000 VND"  ← unambiguous
    2. Dotted VND format from raw_text (context-restricted near price keywords)
    3. Trieu/Ty from raw_pricing ONLY as fallback when no dotted prices found

    Filter: amounts >= 150.000.000 VND considered vehicle prices.
    Triệu/Tỷ values are only used when NO dotted-VND prices exist, because
    "159 triệu" / "170 triệu" are often monthly installments shown on the page.
    """
    MIN_VEHICLE_PRICE = 150_000_000   # 150 trieu – VF2 starts at ~171-188M

    dotted_prices: list[int] = []   # unambiguous dotted-format prices
    trieu_ty_prices: list[int] = [] # triệu/tỷ prices (more ambiguous)

    dotted_re = re.compile(r"(\d{1,3}(?:\.\d{3}){2,})", re.UNICODE)
    ty_re     = re.compile(r"(\d+[.,]?\d*)\s*t[y\u1ef7]", re.IGNORECASE | re.UNICODE)
    trieu_re  = re.compile(r"(\d+[.,]?\d*)\s*tri[e\u1ec7]u", re.IGNORECASE | re.UNICODE)

    # ── 1. Dotted VND from raw_pricing strings ─────────────────────────────
    for s in pricing_strs:
        for m in dotted_re.finditer(s):
            val = int(m.group(1).replace(".", ""))
            if val >= MIN_VEHICLE_PRICE:
                dotted_prices.append(val)

    # ── 2. Dotted VND from raw_text (restricted to price-indicator lines) ──
    price_ctx_re = re.compile(
        r"(?:gi[a\u00e1\xc1]\s*(?:t[u\u1eeb]\s*)?|from\s*|price\s*)[^\n]{0,100}",
        re.IGNORECASE | re.UNICODE,
    )
    for m in price_ctx_re.finditer(raw_text):
        for dm in dotted_re.finditer(m.group(0)):
            val = int(dm.group(1).replace(".", ""))
            if val >= MIN_VEHICLE_PRICE:
                dotted_prices.append(val)

    # ── 3. Triệu/Tỷ from raw_pricing — ONLY used as fallback ──────────────
    for s in pricing_strs:
        for m in ty_re.finditer(s):
            try:
                val = int(float(m.group(1).replace(",", ".")) * 1_000_000_000)
                if val >= MIN_VEHICLE_PRICE:
                    trieu_ty_prices.append(val)
            except ValueError:
                pass
        for m in trieu_re.finditer(s):
            try:
                val = int(float(m.group(1).replace(",", ".")) * 1_000_000)
                if val >= MIN_VEHICLE_PRICE:
                    trieu_ty_prices.append(val)
            except ValueError:
                pass

    # Prefer dotted prices; fall back to triệu/tỷ only if nothing found
    car_prices = sorted(set(dotted_prices)) or sorted(set(trieu_ty_prices))

    if not car_prices:
        return None

    return {
        "starting_price": car_prices[0],
        "battery_included": car_prices[0],
        "battery_subscription": car_prices[1] if len(car_prices) > 1 else None,
        "currency": "VND",
    }
def _calc_price_per_range(
    pricing: dict | None, rng: dict | None
) -> dict | None:
    """
    price_per_range = starting_price / range.value  (VND/km)
    """
    if pricing is None or rng is None:
        return None
    price = pricing.get("starting_price")
    km = rng.get("value")
    if price and km and km > 0:
        return {"value": round(price / km, 2), "unit": "VND/km"}
    return None


# ── Utility functions ─────────────────────────────────────────────────────────

def _parse_number(s: str) -> float:
    """Parse a number string that may contain spaces, dots, or commas."""
    s = s.strip().replace("\xa0", "").replace(" ", "")
    # Decide decimal separator: if last separator is comma → decimal comma
    if "," in s and "." in s:
        # e.g. "1.234,5" → European format
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Could be thousands separator "1,234" or decimal "1,5"
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    return float(s)


def _parse_vnd(s: str) -> int:
    """Parse a raw VND string like '302.000.000' into an integer."""
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else 0


def _detect_cycle(text: str, cycle_map: dict) -> str | None:
    for cycle, pattern in cycle_map.items():
        if pattern.search(text):
            return cycle
    return None


# ──────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Starting VinFast EV Crawler Pipeline")
    log.info("Target: %s", BASE_URL)

    session = requests.Session()
    session.headers.update(HEADERS)

    # ── Stage 1 ──────────────────────────────────────────────────────────────
    vehicles = stage1_discover_vehicles(session)

    if not vehicles:
        log.error("Stage 1 returned no vehicles. Aborting.")
        return

    # Save Stage-1 output
    stage1_path = OUTPUT_DIR / "stage1_vehicles.json"
    stage1_path.write_text(json.dumps(vehicles, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Stage 1 saved → %s", stage1_path)

    # ── Stage 2 ──────────────────────────────────────────────────────────────
    raw_records = stage2_extract_details(vehicles, session)

    # Save Stage-2 output (raw, for debugging)
    raw_path = OUTPUT_DIR / "vinfast_raw.json"
    raw_path.write_text(json.dumps(raw_records, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Stage 2 (raw) saved → %s", raw_path)

    # ── Stage 3 ──────────────────────────────────────────────────────────────
    normalized = stage3_normalize(raw_records)

    # Save normalized JSON array
    json_path = OUTPUT_DIR / "vinfast_vehicles.json"
    json_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Stage 3 (JSON) saved → %s", json_path)

    # Save JSONL (one object per line)
    jsonl_path = OUTPUT_DIR / "vinfast_vehicles.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for record in normalized:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("Stage 3 (JSONL) saved → %s", jsonl_path)

    log.info("Pipeline complete. %d vehicles processed.", len(normalized))

    # ── Quick Summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  VinFast EV Crawler — {len(normalized)} vehicles found")
    print("=" * 60)
    for v in normalized:
        model = v.get("model") or "—"
        variant = v.get("variant") or ""
        price = v.get("pricing") or {}
        sp = price.get("starting_price")
        rng = v.get("range") or {}
        km = rng.get("value")
        print(
            f"  {v['brand']} {model} {variant}".ljust(30)
            + f"  {sp:>15,} VND  {km or '?':>5} km"
            if sp
            else f"  {v['brand']} {model} {variant}"
        )
    print("=" * 60)
    print(f"  Output directory: {OUTPUT_DIR.resolve()}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()