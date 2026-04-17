import os
import time
import pandas as pd
from datetime import date, time as dt_time
from typing import List
import shutil
import re

from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver as Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from schemas import ConnectionSchema, FlightSchema
from logger import logger_setup


logger = logger_setup("scraper.log", logger_name="web_scraper")


def generate_google_flights_url(connection: ConnectionSchema) -> tuple[str, str]:
    """
    Generate google flight search url based on the connection details.
    """

    if connection.one_way:
        query = (
            f"Flights to {connection.destination} from {connection.origin} "
            f"on {connection.departure_date} oneway"
            )
    else:
        query = (
            f"Flights to {connection.destination} from {connection.origin} "
            f"on {connection.departure_date} return {connection.return_date}"
            )

    # URL encode the spaces to %20
    encoded_query = query.replace(" ", "%20")
    return f"https://www.google.com/travel/flights?q={encoded_query}", encoded_query


class Selectors:
    # interaction selectors
    CONSENT_REJECT = "//button[contains(., 'Reject all') or contains(., 'Alle ablehnen')]"
    POP_UP = "//button[contains(., 'Got it') or contains(., 'Verstanden') or contains(., 'Done')]"
    # tabs
    CHEAPEST_TAB = "M7sBEb"
    MORE_TAB = "li.ZVk93d"
    # data selectors
    FLIGHT_CARD = "li.pIav2d"
    AIRLINE = ".sSHqwe"
    DURATION = ".gvkrdb"
    FLIGHT_TIME = ".zxVSec"
    STOPS = ".EfT7Ae"
    PRICE = ".FpEdX span"
    # calender selectors
    DEPARTURE_INPUT = "//input[@placeholder='Departure']"
    NEXT_BTN = "button[jsname='KpyLEe']"
    PREV_BTN = "button[jsname='ux1Cpc']"
    PRICE_TAG = "div[jsname='qCDwBb']"


class GoogleFlightsScraper:
    def __init__(self, headless: bool = True):
        self.options = self._build_options(headless)
        self._driver = None

    @property
    def driver(self):
        """Returns the current driver or starts a new one if needed."""
        if self._driver is None:
            self._driver = self._init_driver()
        return self._driver

    @property
    def wait(self):
        return WebDriverWait(self.driver, 15)

    @property
    def wait_short(self):
        return WebDriverWait(self.driver, 2)

    def _build_options(self, headless: bool) -> Options:
        """Configures Chrome options for scraping."""
        options = Options()
        options.page_load_strategy = 'eager'
        if headless:
            options.add_argument("--headless")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return options

    def _init_driver(self) -> Chrome:
        """Handles cross-platform path detection and driver startup."""
        exe_path = shutil.which("chromium") or shutil.which("chromium-browser")
        driver_path = shutil.which("chromedriver")

        if exe_path and driver_path:
            self.options.binary_location = exe_path
            service = Service(executable_path=driver_path)
            return Chrome(service=service, options=self.options)

        return Chrome(options=self.options)

    def _handle_overlays(self):
        """Clears consent screens and initial pop-ups."""
        # Consent Screen
        try:
            reject_xpath = Selectors.CONSENT_REJECT
            reject_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, reject_xpath)))
            reject_btn.click()
            logger.info("Consent screen cleared.")
        except Exception:
            logger.warning("Could not clear consent screen.")

        # Pop-up Killer
        try:
            time.sleep(1)
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            pop_up_xpath = Selectors.POP_UP
            pop_ups = self.driver.find_elements(By.XPATH, pop_up_xpath)
            for btn in pop_ups:
                btn.click()
            logger.info("Pop-ups cleared.")
        except Exception:
            pass

    def _displayed_flights(self, cheapest: bool = False, more: bool = False):
        """Applies sorting and expansion filters."""
        if cheapest:
            try:
                cheapest_btn = self.wait.until(EC.element_to_be_clickable((By.ID, Selectors.CHEAPEST_TAB)))
                cheapest_btn.click()
                time.sleep(2)
            except Exception:
                logger.warning("Could not click 'Cheapest' button.")

        if more:
            try:
                view_more = self.driver.find_elements(By.CSS_SELECTOR, Selectors.MORE_TAB)
                if view_more:
                    view_more[0].click()
                    time.sleep(2)
            except Exception:
                logger.warning("Could not click 'View More' button.")

    def _parse_flight_element(self, element, connection: ConnectionSchema) -> FlightSchema:
        """Extracts data from a single flight row."""
        airline = element.find_element(By.CSS_SELECTOR, Selectors.AIRLINE).text
        duration = element.find_element(By.CSS_SELECTOR, Selectors.DURATION).text
        flight_time = element.find_element(By.CSS_SELECTOR, Selectors.FLIGHT_TIME).text.replace("\n", "")
        price_text = element.find_element(By.CSS_SELECTOR, Selectors.PRICE).text

        price = int(''.join(filter(str.isdigit, price_text)))

        stops_text = element.find_element(By.CSS_SELECTOR, Selectors.STOPS).text
        stops = 0 if "Nonstop" in stops_text else int(stops_text.split(" ")[0])

        return FlightSchema(
            origin=connection.origin,
            destination=connection.destination,
            airline=airline,
            departure_date=connection.departure_date,
            return_date=connection.return_date,
            flight_time=flight_time,
            price=price,
            duration=duration,
            stops=stops
        )

    def scrape_flights(
            self,
            url: str,
            connection: ConnectionSchema,
            cheapest_flights: bool = False,
            more_flights: bool = False
            ) -> List[FlightSchema]:
        """Scrape flight data for specific connection."""
        try:
            logger.info(f"Scraping URL: {url}")
            self.driver.get(url)

            self._handle_overlays()
            self._displayed_flights(cheapest_flights, more_flights)

            # Data Extraction
            flight_elements = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, Selectors.FLIGHT_CARD))
            )

            flights_data = []
            for element in flight_elements:
                try:
                    flight = self._parse_flight_element(element, connection)
                    flights_data.append(flight)
                except Exception:
                    logger.warning("Failed to parse a flight entry, skipping.")

            logger.info(f"Found {len(flights_data)} flights.")
            return flights_data

        except Exception as e:
            logger.error(f"Critical error during scrape: {e}")
            return []
        finally:
            if self._driver:
                self._driver.quit()
                self._driver = None

    def scrape_flights_with_retry(
            self, url, connection, cheapest_flights=True, more_flights=False, max_retries=3
            ) -> List[FlightSchema]:
        """Wraps the scraper with a retry loop."""
        # clean up any hanging processes before starting
        # self.cleanup_chrome()

        for attempt in range(max_retries):
            try:
                result = self.scrape_flights(url, connection, cheapest_flights, more_flights)
                if result:
                    return result
                else:
                    logger.warning(f"Attempt {attempt + 1}: No flights found. Retrying...")
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed with error: {e}")

            wait_time = (attempt + 1) * 10
            if attempt < max_retries - 1:
                logger.info(f"Waiting {wait_time}s before next attempt...")
                time.sleep(wait_time)

        logger.error(f"All {max_retries} attempts failed.")
        return []

    def scrape_price_list(
            self,
            url: str,
            ) -> List[int]:
        """Scraping flight price list."""
        try:
            logger.info(f"Scraping price list URL: {url}")
            self.driver.get(url)

            self._handle_overlays()
            self._displayed_flights()

            # Data Extraction
            # Click departure input to open the price calendar
            try:
                departure_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, Selectors.DEPARTURE_INPUT)))
                departure_input.click()
                logger.info("'Departure' input clicked.")
            except Exception as e:
                logger.warning(f"Could not click 'Departure' input: {e}")

            # Load all monthly price sheets
            # Click previous button as often as possible
            i = 0
            while True:
                try:
                    prev_btn = self.wait_short.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, Selectors.PREV_BTN))
                    )
                    self.driver.execute_script("arguments[0].click();", prev_btn)
                    i += 1
                    # Small buffer to prevent the browser from freezing
                    time.sleep(0.25)
                except Exception:
                    break
            logger.info(f"Clicked 'Previous' button {i} times.")

            # Click next button an wait for prices to load
            i = 0
            while True:
                try:
                    # Use a short wait to ensure the button is ready for the next click
                    next_btn = self.wait_short.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, Selectors.NEXT_BTN))
                    )
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    i += 1
                    # Small buffer to load data and prevent freezing
                    time.sleep(3)
                except Exception:
                    break
            logger.info(f"Clicked 'Next' button {i} times.")

            logger.info("Price calendar loaded.")

            # Scrape prices currently in the HTML
            all_elements = self.driver.find_elements(By.CSS_SELECTOR, Selectors.PRICE_TAG)
            logger.info(f"Total elements found in HTML: {len(all_elements)}.")

            prices = []
            for element in all_elements:
                price = None
                # logger.info(f"Extracted element: {element}")
                try:
                    price_tag = element.get_attribute("aria-label")
                    # logger.info(f"Extracted price tag: {price_tag}")
                    if price_tag:
                        price = re.sub(r'\D', '', price_tag)
                        # logger.info(f"Extracted price: {price} from tag: {price_tag}")

                        if price:
                            price = int(price)
                except Exception as e:
                    logger.warning(f"Error occurred while parsing price: {e}")
                    pass

                if price:
                    prices.append(price)

            logger.info(f"Extracted {len(prices)}/{len(all_elements)} price tags.")
            return prices

        except Exception as e:
            logger.error(f"Critical error during price list scrape: {e}")
            return []
        finally:
            if self._driver:
                self._driver.quit()
                self._driver = None


def parse_duration(duration_str: str) -> dt_time:
    hours = re.search(r'(\d+) h', duration_str)
    minutes = re.search(r'(\d+) m', duration_str)

    if hours:
        hours = int(hours.group(1))
    else:
        hours = 0

    if minutes:
        minutes = int(minutes.group(1))
    else:
        minutes = 0

    return dt_time(hour=hours, minute=minutes)


def flight_data_filter(
        flights_data: list[FlightSchema],
        connection: ConnectionSchema,
        top_n: int | None = None
        ) -> list[FlightSchema]:
    filtered_data = []

    for flight in flights_data:
        # Filter by max_stops
        if connection.max_stops is not None:
            try:
                if flight.stops > connection.max_stops:
                    continue
            except Exception:
                continue  # Unable to parse stops, skip this flight

        # Filter by max_duration
        if connection.max_duration_hours is not None:
            try:
                total_duration = parse_duration(flight.duration)
                if total_duration > dt_time(hour=connection.max_duration_hours, minute=0):
                    continue
            except Exception:
                continue  # Unable to parse duration, skip this flight

        filtered_data.append(flight)

    return filtered_data[:top_n] if top_n is not None else filtered_data


def get_flight_data(
        connection: ConnectionSchema,
        cheapest_flights: bool = False,
        more_flights: bool = False,
        top_n: int | None = None
        ) -> list[FlightSchema]:

    url, _ = generate_google_flights_url(connection)
    scraper = GoogleFlightsScraper(headless=True)
    data = scraper.scrape_flights_with_retry(
        url, connection, cheapest_flights, more_flights
    )
    return flight_data_filter(data, connection, top_n)


def get_price_list(
        connection: ConnectionSchema
        ) -> ConnectionSchema:

    url, _ = generate_google_flights_url(connection)
    scraper = GoogleFlightsScraper(headless=True)
    data = scraper.scrape_price_list(url)
    return ConnectionSchema(price_list=data, **connection.model_dump(exclude={"price_list"}))


def main():
    # Simple test run
    # Example: Search VIE (IVienna) to LHR (London Heathrow) from 2026-01-01 to 2026-01-10
    connection = ConnectionSchema(
        origin="VIE",
        destination="LHR",
        departure_date=date(year=2026, month=1, day=1),
        return_date=date(year=2026, month=1, day=10),
        stay_duration=10,
    )
    search_url, encoded_query = generate_google_flights_url(connection)

    scraper = GoogleFlightsScraper(headless=True)
    result = scraper.scrape_flights(search_url, connection, cheapest_flights=True, more_flights=True)

    filtered_flights = flight_data_filter(result, connection=connection)

    # print("Filtered Flights:")
    # for flight in filtered_flights:
    #     print(flight)

    # Save to CSV for your data base
    if filtered_flights:
        df = pd.DataFrame(filtered_flights)
        df.to_csv(f"flight_prices_{encoded_query}.csv", mode='a', index=False,
                  header=not os.path.isfile(f"flight_prices_{encoded_query}.csv"))
        logger.info(f"Saved {len(df)} flights to csv.")


if __name__ == "__main__":
    # main()
    print(parse_duration("2 hr 30 min"))
