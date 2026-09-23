from src.telemetry.logger import logger
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from pathlib import Path
from selenium.common.exceptions import TimeoutException
from urllib.parse import urljoin
import time

from time import sleep

COUNTRY_MAP = {
    "de": "Germany",
    "nl": "Netherlands",
    "uk": "United Kingdom"
}
def chrome_webdriver():
    options = webdriver.ChromeOptions()
    #options.add_argument("--headless")  # Chạy Chrome không hiển thị giao diện
    options.add_argument("--disable-gpu")  # Tắt GPU tăng hiệu suất
    options.add_argument("--no-sandbox")  # Tránh lỗi sandbox trong môi trường Linux

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def wait() -> None:
    time.sleep(5)

class Crawl:
    """
    Class này dùng để crawl dữ liệu từ các trang web của từng hãng xe
    - Các dữ liệu được crawl sẽ được lưu vào thư mục crawl/data.
    """
    def __init__(self, driver, output_path: str | Path, url: str) -> None:
        """
        Khởi tạo đối tượng Crawl
        - driver: đối tượng WebDriver của Selenium
        - output_path: đường dẫn để lưu dữ liệu crawl được
        """
        self.driver = driver
        self.url = url
        self.output_path = Path(output_path)
        self.wait = WebDriverWait(self.driver, 15)  # Thời gian chờ tối đa là 10 giây
    def open_page(self) -> None:
        """
        Mở trang web với URL được cung cấp
        - url: URL của trang web cần mở
        """
        self.driver.get(self.url)
        logger.info(f"Đang mở trang web: {self.url}")
        try:
            # Chờ cho đến khi phần tử có class "search-form" xuất hiện
            wait()
            logger.info("Trang web đã tải xong.")
        except Exception as e:
            logger.error(f"Không thể tải trang web: {e}")
            self.driver.quit()
    def click_next_page(self) -> bool:
        """
        Click vào nút "Next Page" => để chuyển sang trang tiếp theo
        """
        next_btn = self.wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "button[data-type='next']")
            )
        )

        old_page = next_btn.get_attribute("data-page")

        self.driver.execute_script("arguments[0].click();", next_btn)

        try:
            self.wait.until(
                lambda d: d.find_element(
                    By.CSS_SELECTOR,
                    "button[data-type='next']"
                ).get_attribute("data-page") != old_page
            )

            return True

        except TimeoutException:
            return False
    def crawl_current_page(self, item) -> dict:
        """
        Lấy dữ liệu của trang hiện tại
        """
        brand = item.select_one("a.title span:first-child").get_text(strip=True)
        model_text = item.select_one("span.model").get_text(" ", strip=True)
        parts = model_text.split()
        model = parts[0]
        variant = " ".join(parts[1:])
        body = item.select_one("span[class^='shape-']")
        body_type = body.text.strip() if body else None
        year = item.select_one("span.year_from").text.strip()
        status = item.select_one("div.availability").get_text(" ", strip=True)
        specs = item.select_one("div.specs")
        range_ = specs.select_one(".erange_real").get_text(strip=True)
        efficiency = specs.select_one(".efficiency").get_text(strip=True)
        weight = specs.select_one(".weight_p").get_text(strip=True)
        acceleration_0_100 = specs.select_one(".acceleration_p").get_text(strip=True)
        one_stop_range = specs.select_one(".long_distance_total").get_text(strip=True)
        battery = specs.select_one(".battery_p").get_text(strip=True)
        fastcharge = specs.select_one(".fastcharge_speed_print").get_text(strip=True)
        towing = specs.select_one(".towweight_p").get_text(strip=True)
        cargo_volume = specs.select_one(".cargo").get_text(strip=True)
        price_per_range = specs.select_one(".priceperrange_p").get_text(strip=True)
        if status.startswith("Available"):
            status = "Available"

        image = urljoin(
            self.url,
            item.select_one("img")["src"]
        )
        detail_link = urljoin(
            self.url,
            item.select_one("a.title")["href"]
        )
        pricing = {}
        pricing_div = item.select_one("div.pricing.org")
        if pricing_div:
            for span in pricing_div.select("div.price_buy span[class^='country_']"):
                code = span["class"][0].replace("country_", "")
                pricing[COUNTRY_MAP.get(code, code)] = span.get_text(strip=True)
        return {
            "brand": brand,
            "model": model,
            "variant": variant,
            "body_type": body_type,
            "year": year,
            "status": status,
            "range": range_,
            "efficiency": efficiency,
            "weight": weight,
            "acceleration_0_100": acceleration_0_100,
            "one_stop_range": one_stop_range,
            "battery": battery,
            "fastcharge": fastcharge,
            "towing": towing,
            "cargo_volume": cargo_volume,
            "price_per_range": price_per_range,
            "pricing": pricing,
            "image": image,
            "detail_link": detail_link
        }
    def save_csv(self, data: list[dict], filename: str) -> None:
        """
        Lưu dữ liệu vào file CSV
        - data: danh sách các dict chứa dữ liệu
        - filename: tên file CSV
        """
        import pandas as pd

        df = pd.DataFrame(data)
        output_file = self.output_path / filename
        df.to_csv(output_file, index=False)
        logger.info(f"Đã lưu dữ liệu vào {output_file}")
    def run(self):
        self.open_page()
        all_cars = []
        while True:
            print(self.driver.current_url)
            soup = BeautifulSoup(
                self.driver.page_source,
                "html.parser"
            )
            items = soup.select("div.list-item")
            for item in items:
                all_cars.append(
                    self.crawl_current_page(item)
                )
            print(f"Crawl xong {len(items)} xe")
            # Nếu đã là trang cuối
            if not self.click_next_page():
                break
        self.save_csv(all_cars, "all_cars.csv")
        logger.info("Done!")
if __name__ == "__main__":
    driver = chrome_webdriver()
    crawl = Crawl(driver, "crawl/data", "https://ev-database.org/")
    crawl.run()