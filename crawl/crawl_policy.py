"""
crawl_policy.py
===============
4-Stage VinFast Policy Crawler

Stage 1 : Discovery       – Khám phá tất cả URL/chính sách từ 2 trang nguồn
Stage 2 : Raw Extraction  – Lấy dữ liệu thô (title, PDF link, download link…)
Stage 3 : Normalization   – Chuẩn hoá dữ liệu thành schema thống nhất
Stage 4 : Download (opt.) – Tải PDF nếu download=True

Targets :
    https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-oto/2026
    https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-may-dien

Output  :
    crawl/data/output/policies.csv
    crawl/data/pdfs/<normalized>.pdf   (only when download=True)
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────────────
# LOGGER – giống format crawl.py / crawl_motobike_vin.py
# ──────────────────────────────────────────────────────────────────────────────
try:
    from src.telemetry.logger import logger  # project logger nếu có
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

# Selenium – giữ đúng format import như crawl.py
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
    NoSuchElementException,
)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

SOURCE_PAGES: list[dict[str, str]] = [
    {
        "url": "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-oto/2026",
        "category": "Xe o to",
    },
    {
        "url": "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-may-dien",
        "category": "Xe may dien",
    },
]

BASE_DIR   = Path(__file__).parent          # crawl/
OUTPUT_DIR = BASE_DIR / "data"
PDF_DIR    = BASE_DIR / "data" / "pdfs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT        = 30
DELAY_BETWEEN_REQUESTS = 1.5
PAGE_LOAD_WAIT         = 5       # giay cho JS render


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: Selenium WebDriver
# ──────────────────────────────────────────────────────────────────────────────

def _create_webdriver() -> webdriver.Chrome:
    """Khoi tao Chrome WebDriver (headless)."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: Normalize filename for PDF
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_filename(title: str, year: str | None = None) -> str:
    """
    Chuyen title + year thanh ten file PDF an toan.
    Vi du: 'Chinh sach bao hanh VF3' + '2026' -> 'Chinh_sach_bao_hanh_VF3_2026.pdf'
    """
    name = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE)
    name = name.strip().replace(" ", "_")
    name = re.sub(r"_+", "_", name)
    name = re.sub(r"[^\x00-\x7F]", "", name)   # strip non-ASCII
    if year:
        name = f"{name}_{year}"
    if not name:
        name = f"policy_{int(time.time())}"
    return name + ".pdf"


# ──────────────────────────────────────────────────────────────────────────────
# MAIN CLASS
# ──────────────────────────────────────────────────────────────────────────────

class CrawlPolicy:
    """
    Pipeline 4-stage de crawl chinh sach PDF tu 2 trang VinFast.

    Vi du:
        crawler = CrawlPolicy()
        crawler.run(download=False)   # chi metadata + CSV
        crawler.run(download=True)    # metadata + tai PDF vao data/pdfs/
    """

    def __init__(
        self,
        output_path: str | Path = OUTPUT_DIR,
        pdf_path: str | Path = PDF_DIR,
    ) -> None:
        self.output_path = Path(output_path)
        self.pdf_path    = Path(pdf_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.pdf_path.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        # Ket qua trung gian giua cac stage
        self._stage1_items: list[dict[str, Any]] = []
        self._stage2_items: list[dict[str, Any]] = []
        self._stage3_items: list[dict[str, Any]] = []

    # ──────────────────────────────────────────────────────────────────────────
    # STAGE 1 – Discovery
    # ──────────────────────────────────────────────────────────────────────────

    def _discovery(self) -> list[dict[str, Any]]:
        """
        Stage 1: Discovery
        Dung Selenium de render JS, sau do parse toan bo the chua policy card.
        Tra ve list[dict] voi cac key: url, category, source_page, raw_html_snippet
        """
        logger.info("=" * 60)
        logger.info("=== STAGE 1: Discovery ===")
        logger.info("=" * 60)

        discovered: list[dict[str, Any]] = []
        driver = _create_webdriver()

        try:
            for source in SOURCE_PAGES:
                page_url = source["url"]
                category = source["category"]
                logger.info(f"[Discovery] Dang mo: {page_url}")

                driver.get(page_url)
                time.sleep(PAGE_LOAD_WAIT)

                # Cuon trang xuong de kich hoat lazy-load
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                page_html = driver.page_source
                soup = BeautifulSoup(page_html, "html.parser")

                # Tim tat ca link co href chua .pdf hoac link preview/download
                raw_links = soup.find_all("a", href=True)
                found = 0
                for a_tag in raw_links:
                    href = a_tag["href"].strip()
                    if any(kw in href.lower() for kw in [".pdf", "chinh-sach", "policy", "hop-dong"]):
                        abs_url = urllib.parse.urljoin(page_url, href)
                        entry: dict[str, Any] = {
                            "source_page":    page_url,
                            "category":       category,
                            "discovered_url": abs_url,
                            "link_text":      a_tag.get_text(strip=True),
                            "raw_html":       str(a_tag),
                        }
                        discovered.append(entry)
                        found += 1

                # Neu khong tim thay link PDF truc tiep, lay toan bo card/item
                if found == 0:
                    logger.warning(
                        f"[Discovery] Khong tim thay link PDF truc tiep tren {page_url} – "
                        "thu parse cards..."
                    )
                    card_selectors = [
                        "div.policy-item", "div.document-item", "li.policy",
                        "article", "div[class*='policy']", "div[class*='document']",
                        "div.field-item", "div.views-row",
                    ]
                    for selector in card_selectors:
                        cards = soup.select(selector)
                        if cards:
                            for card in cards:
                                a = card.find("a", href=True)
                                href = a["href"].strip() if a else ""
                                abs_url = urllib.parse.urljoin(page_url, href) if href else ""
                                entry = {
                                    "source_page":    page_url,
                                    "category":       category,
                                    "discovered_url": abs_url,
                                    "link_text":      card.get_text(" ", strip=True)[:200],
                                    "raw_html":       str(card)[:500],
                                }
                                discovered.append(entry)
                                found += 1
                            logger.info(f"[Discovery] Selector '{selector}' tim duoc {found} cards")
                            break

                logger.info(f"[Discovery] {page_url} -> {found} muc tim duoc")
                time.sleep(DELAY_BETWEEN_REQUESTS)

        finally:
            driver.quit()
            logger.info("[Discovery] Dong trinh duyet.")

        logger.info(f"[Discovery] Tong cong: {len(discovered)} muc")
        self._stage1_items = discovered
        logger.info("Completed: Discovery completed")
        return discovered

    # ──────────────────────────────────────────────────────────────────────────
    # STAGE 2 – Raw Extraction
    # ──────────────────────────────────────────────────────────────────────────

    def _raw_extraction(self) -> list[dict[str, Any]]:
        """
        Stage 2: Raw Extraction
        Voi moi muc da kham pha, dung Selenium mo tung trang chi tiet (neu can)
        de lay: title, preview_pdf_url, download_url, nam, va metadata tho.
        """
        logger.info("=" * 60)
        logger.info("=== STAGE 2: Raw Extraction ===")
        logger.info("=" * 60)

        raw_items: list[dict[str, Any]] = []
        source_pages_done: set[str] = set()
        driver = _create_webdriver()

        try:
            for source in SOURCE_PAGES:
                page_url = source["url"]
                category = source["category"]

                if page_url in source_pages_done:
                    continue
                source_pages_done.add(page_url)

                logger.info(f"[RawExtraction] Mo: {page_url}")
                driver.get(page_url)
                time.sleep(PAGE_LOAD_WAIT)

                # Cuon de lazy load
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)

                page_html = driver.page_source
                soup = BeautifulSoup(page_html, "html.parser")

                # Tim tat ca <a> dan toi PDF
                pdf_anchors = soup.find_all("a", href=re.compile(r"\.pdf", re.I))
                logger.info(f"[RawExtraction] Tim thay {len(pdf_anchors)} link PDF truc tiep")

                if pdf_anchors:
                    for a_tag in pdf_anchors:
                        href = urllib.parse.urljoin(page_url, a_tag["href"].strip())

                        # Tim tieu de: uu tien class="post-title" trong card/parent hoac bat ky dau
                        title = ""
                        card = a_tag.find_parent(
                            lambda tag: tag.name in ["div", "li", "article", "section"]
                            and len(tag.get_text(strip=True)) > 10
                        )
                        
                        if card:
                            post_title_el = card.find(class_=re.compile(r"\bpost-title\b"))
                            if post_title_el:
                                title = post_title_el.get_text(" ", strip=True)

                        if not title:
                            # Search in whole parent tree or ancestors
                            curr = a_tag.parent
                            for _ in range(6):
                                if curr is None:
                                    break
                                post_title_el = curr.find(class_=re.compile(r"\bpost-title\b"))
                                if post_title_el:
                                    title = post_title_el.get_text(" ", strip=True)
                                    break
                                curr = curr.parent

                        # Fallback neu khong co post-title
                        if not title and card:
                            h_tag = card.find(re.compile(r"^h[1-6]$"))
                            if h_tag:
                                title = h_tag.get_text(" ", strip=True)

                        if not title:
                            parent = a_tag.parent
                            for _ in range(6):
                                if parent is None:
                                    break
                                t = parent.get_text(" ", strip=True)
                                if len(t) > 5:
                                    title = t[:300]
                                    break
                                parent = parent.parent

                        # Tim link download rieng trong cung card
                        download_url = href
                        if card:
                            dl_a = card.find(
                                "a",
                                string=re.compile(r"tai|download|pdf", re.I)
                            )
                            if dl_a and dl_a.get("href"):
                                download_url = urllib.parse.urljoin(
                                    page_url, dl_a["href"].strip()
                                )

                        raw_items.append({
                            "source_page":     page_url,
                            "category":        category,
                            "title_raw":       title or a_tag.get_text(strip=True),
                            "preview_pdf_url": href,
                            "download_url":    download_url,
                            "link_text":       a_tag.get_text(strip=True),
                        })

                else:
                    # Khong co link PDF truc tiep -> parse theo card/row
                    logger.warning(
                        f"[RawExtraction] Khong tim thay link PDF tren {page_url} – "
                        "parse toan bo noi dung trang..."
                    )
                    rows = soup.select(
                        "div.views-row, div.field-item, tr, div[class*='item'], "
                        "div[class*='policy'], div[class*='document'], article"
                    )
                    for row in rows:
                        post_title_el = row.find(class_=re.compile(r"\bpost-title\b"))
                        if post_title_el:
                            title_text = post_title_el.get_text(" ", strip=True)
                        else:
                            title_text = row.get_text(" ", strip=True)[:300]

                        if len(title_text) < 5:
                            continue
                        a = row.find("a", href=True)
                        href = urllib.parse.urljoin(page_url, a["href"]) if a else ""
                        raw_items.append({
                            "source_page":     page_url,
                            "category":        category,
                            "title_raw":       title_text,
                            "preview_pdf_url": href,
                            "download_url":    href,
                            "link_text":       a.get_text(strip=True) if a else "",
                        })
                    logger.info(f"[RawExtraction] Parse duoc {len(rows)} rows tu trang")

                time.sleep(DELAY_BETWEEN_REQUESTS)

        finally:
            driver.quit()
            logger.info("[RawExtraction] Dong trinh duyet.")

        logger.info(f"[RawExtraction] Tong cong {len(raw_items)} muc tho")
        self._stage2_items = raw_items
        logger.info("Completed: Raw Extraction completed")
        return raw_items

    # ──────────────────────────────────────────────────────────────────────────
    # STAGE 3 – Normalization
    # ──────────────────────────────────────────────────────────────────────────

    def _normalization(self) -> list[dict[str, Any]]:
        """
        Stage 3: Normalization
        Chuan hoa du lieu tho thanh schema thong nhat:
        title, category, year, preview_pdf_url, download_url,
        source_page, crawl_timestamp, local_pdf_path, status
        """
        logger.info("=" * 60)
        logger.info("=== STAGE 3: Normalization ===")
        logger.info("=" * 60)

        now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()  # dedup theo download_url

        for raw in self._stage2_items:
            download_url = raw.get("download_url", "").strip()
            preview_url  = raw.get("preview_pdf_url", "").strip()
            title_raw    = raw.get("title_raw", "").strip()
            category     = raw.get("category", "").strip()
            source_page  = raw.get("source_page", "").strip()

            # Bo qua ban trung
            dedup_key = download_url or preview_url or title_raw
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Trich nam tu URL hoac title
            year = ""
            year_match = re.search(r"(20\d{2})", download_url + " " + title_raw)
            if year_match:
                year = year_match.group(1)

            # Lam sach title
            title = re.sub(r"\s+", " ", title_raw).strip()
            if len(title) > 200:
                title = title[:200].rsplit(" ", 1)[0] + "..."

            # Xac dinh status
            status = "ok" if (download_url or preview_url) else "no_url"

            record: dict[str, Any] = {
                "title":           title,
                "category":        category,
                "year":            year,
                "preview_pdf_url": preview_url,
                "download_url":    download_url,
                "source_page":     source_page,
                "crawl_timestamp": now_ts,
                "local_pdf_path":  "",      # se dien khi download=True
                "status":          status,
            }
            normalized.append(record)

        logger.info(f"[Normalization] {len(normalized)} ban ghi sau dedup & chuan hoa")
        self._stage3_items = normalized
        logger.info("Completed: Normalization completed")
        return normalized

    # ──────────────────────────────────────────────────────────────────────────
    # STAGE 4 – Download Documents (opt.)
    # ──────────────────────────────────────────────────────────────────────────

    def _download_documents(self) -> None:
        """
        Stage 4: Download Documents
        Tai tung PDF vao data/pdfs/.
        Neu file da ton tai -> bo qua.
        Neu tai that bai -> danh dau status = 'download_failed'.
        """
        logger.info("=" * 60)
        logger.info("=== STAGE 4: Download Documents ===")
        logger.info("=" * 60)

        total   = len(self._stage3_items)
        success = 0
        skipped = 0
        failed  = 0

        for i, record in enumerate(self._stage3_items, start=1):
            dl_url = record.get("download_url") or record.get("preview_pdf_url")
            title  = record.get("title", f"policy_{i}")
            year   = record.get("year", "")

            if not dl_url:
                logger.warning(f"[Download] [{i}/{total}] Khong co URL – bo qua: {title!r}")
                record["status"] = "no_url"
                continue

            filename   = _normalize_filename(title, year)
            local_path = self.pdf_path / filename

            # Bo qua neu da ton tai
            if local_path.exists():
                logger.info(f"[Download] [{i}/{total}] Da ton tai – bo qua: {filename}")
                record["local_pdf_path"] = str(local_path)
                record["status"]         = "already_exists"
                skipped += 1
                continue

            logger.info(f"[Download] [{i}/{total}] Dang tai: {dl_url}")
            try:
                resp = self.session.get(dl_url, timeout=REQUEST_TIMEOUT, stream=True)
                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "")
                if "pdf" in content_type or dl_url.lower().endswith(".pdf"):
                    with open(local_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    record["local_pdf_path"] = str(local_path)
                    record["status"]         = "downloaded"
                    logger.info(f"[Download] OK Da luu: {local_path}")
                    success += 1
                else:
                    logger.warning(
                        f"[Download] Content-Type='{content_type}' khong phai PDF, "
                        "thu Selenium..."
                    )
                    ok = self._selenium_download(dl_url, local_path)
                    if ok:
                        record["local_pdf_path"] = str(local_path)
                        record["status"]         = "downloaded"
                        success += 1
                    else:
                        record["status"] = "download_failed"
                        failed += 1

            except Exception as e:
                logger.error(f"[Download] FAILED Loi khi tai {dl_url}: {e}")
                record["status"] = "download_failed"
                failed += 1

            time.sleep(DELAY_BETWEEN_REQUESTS)

        logger.info(
            f"[Download] Hoan thanh – "
            f"OK {success} thanh cong / SKIP {skipped} bo qua / FAILED {failed} that bai"
        )
        logger.info("Completed: Download Documents completed")

    def _selenium_download(self, url: str, save_path: Path) -> bool:
        """
        Fallback: dung Selenium de click nut tai xuong.
        Tra ve True neu tai thanh cong.
        """
        logger.info(f"[SeleniumDownload] Thu tai qua Selenium: {url}")
        driver = _create_webdriver()
        try:
            driver.get(url)
            time.sleep(PAGE_LOAD_WAIT)

            dl_btn = None
            for selector in [
                "a[href*='.pdf']",
                "a[download]",
                "button[class*='download']",
                "a[class*='download']",
                "a[title*='tai']",
                "a[title*='Tai']",
            ]:
                try:
                    dl_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except NoSuchElementException:
                    continue

            if dl_btn is None:
                logger.warning("[SeleniumDownload] Khong tim thay nut tai xuong.")
                return False

            dl_href = dl_btn.get_attribute("href") or ""
            if dl_href:
                resp = self.session.get(dl_href, timeout=REQUEST_TIMEOUT, stream=True)
                resp.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"[SeleniumDownload] OK Da luu: {save_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"[SeleniumDownload] Loi: {e}")
            return False
        finally:
            driver.quit()

    # ──────────────────────────────────────────────────────────────────────────
    # Export CSV
    # ──────────────────────────────────────────────────────────────────────────

    def _export_csv(self) -> pd.DataFrame:
        """
        Xuat ket qua cuoi cung ra policies.csv (UTF-8 BOM, 1 hang/chinh sach).
        """
        logger.info("=" * 60)
        logger.info("=== Export CSV ===")
        logger.info("=" * 60)

        columns = [
            "title",
            "category",
            "year",
            "preview_pdf_url",
            "download_url",
            "source_page",
            "crawl_timestamp",
            "local_pdf_path",
            "status",
        ]

        df = pd.DataFrame(self._stage3_items, columns=columns)
        output_file = self.output_path / "policies.csv"
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
        logger.info(f"[Export] policies.csv da luu tai: {output_file}")
        logger.info(f"[Export] Tong cong {len(df)} hang")
        logger.info("Completed: policies.csv exported")
        return df

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def run(self, download: bool = False) -> pd.DataFrame:
        """
        Chay toan bo pipeline crawl chinh sach VinFast.

        Parameters
        ----------
        download : bool, default False
            - False : Chi thuc hien Stage 1-3 + xuat CSV (khong tai PDF)
            - True  : Thuc hien Stage 1-4 + xuat CSV (co tai PDF vao data/pdfs/)

        Returns
        -------
        pd.DataFrame
            DataFrame ket qua cuoi cung (giong noi dung policies.csv)
        """
        logger.info("=" * 60)
        logger.info("   CrawlPolicy – VinFast Policy Pipeline")
        logger.info(f"   download={download}")
        logger.info("=" * 60)

        # Stage 1
        self._discovery()

        # Stage 2
        self._raw_extraction()

        # Stage 3
        self._normalization()

        # Stage 4 (tuy chon)
        if download:
            self._download_documents()
        else:
            logger.info("[Pipeline] download=False -> Bo qua Stage 4 (Download)")

        # Export
        df = self._export_csv()

        logger.info("=" * 60)
        logger.info("   Pipeline hoan thanh!")
        logger.info("=" * 60)
        return df


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    crawler = CrawlPolicy()
    crawler.run(download=True)
