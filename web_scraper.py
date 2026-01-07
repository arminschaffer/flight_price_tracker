import os
import time
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
from datetime import date, time as dt_time
from typing import List, Dict, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# --- 1. LOGGING SETUP ---
logger = logging.getLogger("FlightScraper")
logger.setLevel(logging.INFO)

# Rotate logs at 5MB, keep 3 backup files
file_handler = RotatingFileHandler("scraper.log", maxBytes=2*1024*1024, backupCount=3)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def generate_google_flights_url(
        origin: str, 
        dest: str, 
        depature_date: str, 
        return_date: str | None, 
        one_way: bool = False
        ) -> tuple[str, str]:
    """
    Docstring for generate_google_flights_url
    
    :param origin: Airport code of origin or city name (e.g. VIE for Vienna, or Vienna)
    :type origin: str
    :param dest: Airport code of destination or city name (e.g. LHR for London Heathrow, or London)
    :type dest: str
    :param depature_date: Departure date
    :type depature_date: date
    :param return_date: Return date
    :type return_date: date | None
    :param one_way: one way trip if True, defaults to False
    :return: url string for Google Flights search
    :rtype: str
    """

    if one_way or return_date is None:
        query = f"Flights to {dest} from {origin} on {depature_date} oneway"
    else:
        query = f"Flights to {dest} from {origin} on {depature_date} return {return_date}"
    
    # URL encode the spaces to %20
    encoded_query = query.replace(" ", "%20")
    return f"https://www.google.com/travel/flights?q={encoded_query}", encoded_query


def scrape_google_flights(
        url: str, 
        departure_date: str,
        return_date: Optional[str],
        cheapest_flights_option: bool = True, 
        more_flights: bool = False
    ) -> List[Dict]:
    
    chrome_options = Options()
    chrome_options.page_load_strategy = 'eager'
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # --- CROSS-PLATFORM PATH DETECTION ---
    pi_browser_path = "/usr/bin/chromium"
    pi_driver_path = "/usr/bin/chromedriver"

    # If we are on the Raspberry Pi (Linux + specific path exists)
    if os.path.exists(pi_browser_path):
        chrome_options.binary_location = pi_browser_path
        driver_service = Service(executable_path=pi_driver_path)
        driver = webdriver.Chrome(service=driver_service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)
        
    driver.set_page_load_timeout(60)
    
    flights_data = []
    
    try:
        logger.info(f"Scraping URL: {url}")
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        # A. CONSENT SCREEN
        try:
            reject_xpath = "//button[contains(., 'Reject all') or contains(., 'Alle ablehnen')]"
            reject_btn = wait.until(EC.element_to_be_clickable((By.XPATH, reject_xpath)))
            reject_btn.click()
            logger.info("Consent screen cleared.")
        except Exception:
            pass # Already cleared or didn't appear

        # B. POP-UP KILLER (Recommended Flights / Tips)
        try:
            time.sleep(1) # Small pause for animations
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            
            pop_up_xpath = "//button[contains(., 'Got it') or contains(., 'Verstanden') or contains(., 'Done')]"
            pop_ups = driver.find_elements(By.XPATH, pop_up_xpath)
            for btn in pop_ups:
                btn.click()
                logger.info("Recommendation pop-up cleared.")
        except Exception:
            pass

        # C. SORT BY CHEAPEST
        if cheapest_flights_option:
            try:
                cheapest_btn = wait.until(EC.element_to_be_clickable((By.ID, "M7sBEb")))
                cheapest_btn.click()
                time.sleep(2)
            except Exception:
                logger.warning("Could not click 'Cheapest' button.")

        # D. VIEW MORE
        if more_flights:
            try:
                view_more = driver.find_elements(By.CSS_SELECTOR, "li.ZVk93d")
                if view_more:
                    view_more[0].click()
                    time.sleep(2)
            except Exception:
                pass

        # E. DATA EXTRACTION
        flight_elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.pIav2d")))

        for flight in flight_elements:
            try:
                airline = flight.find_element(By.CSS_SELECTOR, ".sSHqwe").text
                duration = flight.find_element(By.CSS_SELECTOR, ".gvkrdb").text
                price_text = flight.find_element(By.CSS_SELECTOR, ".FpEdX span").text
                
                # Robust price cleaning
                price = int(''.join(filter(str.isdigit, price_text)))

                stops_text = flight.find_element(By.CSS_SELECTOR, ".EfT7Ae").text
                stops = 0 if "Nonstop" in stops_text else int(stops_text.split(" ")[0])

                flights_data.append({
                    "airline": airline,
                    "departure_date": departure_date,
                    "return_date": return_date,
                    "price": price,
                    "duration": duration,
                    "stops": stops,
                    "scraped_at": pd.Timestamp.now()
                })
            except Exception:
                continue 

        logger.info(f"Found {len(flights_data)} flights.")
        return flights_data

    except Exception as e:
        logger.error(f"Critical error during scrape: {e}")
        return []
    finally:
        driver.quit()


def flight_data_filter(flights_data: list[dict], 
                       max_stops: int | None = None, 
                       max_duration: dt_time | None = None,
                       top_n: int | None = None
                       ) -> list[dict]:
    filtered_data = []

    for flight in flights_data:
        stops = flight.get("stops", "")
        duration_str = flight.get("duration", "")

        # Filter by max_stops
        if max_stops is not None:
            try:
                if stops > max_stops:
                    continue
            except:
                continue  # Unable to parse stops, skip this flight

        # Filter by max_duration
        if max_duration is not None:
            try:
                hours, minutes = 0, 0
                if 'h' in duration_str:
                    hours = int(duration_str.split(' ')[0].strip())
                    duration_str = duration_str.split('hr ')[1].strip()
                if 'm' in duration_str:
                    minutes = int(duration_str.split(' ')[0].strip())
                total_duration = dt_time(hour=hours, minute=minutes)
                if total_duration > max_duration:
                    continue
            except:
                continue  # Unable to parse duration, skip this flight

        filtered_data.append(flight)

    return filtered_data[:top_n] if top_n is not None else filtered_data


def get_flight_data(
        origin: str, 
        dest: str, 
        depature_date: str, 
        return_date: str | None, 
        one_way: bool = False,
        cheapest_flights_option: bool = False,
        more_flights: bool = False,
        max_stops: int | None = None, 
        max_duration: dt_time | None = None,
        top_n: int | None = None
        ) -> list[dict]:
    
    url, _ = generate_google_flights_url(origin, dest, depature_date, return_date, one_way)
    data = scrape_google_flights(url, depature_date, return_date, cheapest_flights_option, more_flights)
    return flight_data_filter(data, max_stops, max_duration, top_n)


def main():
    # Simple test run
    # Example: Search VIE (IVienna) to LHR (London Heathrow) from 2026-01-01 to 2026-01-10
    search_url, encoded_query = generate_google_flights_url("VIE", "LHR", "2026-01-01", "2026-01-10")

    data = scrape_google_flights(search_url, "2026-01-01", "2026-01-10", cheapest_flights_option=True, more_flights=True)

    # for flight in data:
    #     print(flight)

    filtered_flights = flight_data_filter(data, max_stops=1, max_duration=dt_time(hour=5, minute=0))

    # print("Filtered Flights:")
    # for flight in filtered_flights:
    #     print(flight)

    # 4. Save to CSV for your Databank
    if filtered_flights:
        df = pd.DataFrame(filtered_flights)
        df.to_csv(f"flight_prices_{encoded_query}.csv", mode='a', index=False, header=not os.path.isfile(f"flight_prices_{encoded_query}.csv"))
        logger.info(f"Saved {len(df)} flights to csv.")


if __name__ == "__main__":
    main()