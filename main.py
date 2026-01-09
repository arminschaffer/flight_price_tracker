import os
import json
import logging
import schedule
import time
import pandas as pd
from logging.handlers import RotatingFileHandler
from datetime import timedelta, datetime, time as dt_time
from typing import Generator, TypedDict
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from web_scraper import get_flight_data
from db import Session, engine, Search


# --- 1. LOGGING SETUP ---
logger = logging.getLogger("FlightPriceTracker")
logger.setLevel(logging.INFO)

# Rotate logs at 5MB, keep 3 backup files
file_handler = RotatingFileHandler(
    "tracker.log", 
    maxBytes=2*1024*1024, 
    backupCount=3,
    delay=False
    )
stream_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


class FlightDates(TypedDict):
    departure_date: str
    return_date: str
    stay_duration: int


def get_or_create_search(session, **kwargs) -> Search:
    """
    Checks if a search with specific parameters exists, 
    otherwise creates a new one.
    """
    # 1. Attempt to find the existing record
    instance = session.query(Search).filter_by(**kwargs).first()

    if instance:
        logger.info(f"Search found in DB (ID: {instance.id}).")
        return instance
    
    # 2. If not found, create it using the same dictionary
    instance = Search(**kwargs)
    session.add(instance)
    session.commit()
    session.refresh(instance)
    logger.info(f"New search created (ID: {instance.id}).")

    return instance


def generate_date_combinations(
        earliest_departure: str,
        latest_return: str,
        min_stay_days: int,
        max_stay_days: int
        ) -> Generator[FlightDates, None, None]:
    
    # Convert strings to datetime objects
    start_dt = datetime.strptime(earliest_departure, "%Y-%m-%d")
    end_dt = datetime.strptime(latest_return, "%Y-%m-%d")
    
    # The absolute latest someone could depart is (Latest Return - Min Stay)
    latest_departure_possible = end_dt - timedelta(days=min_stay_days)
    
    current_depart = start_dt
    while current_depart <= latest_departure_possible:
        
        for stay in range(min_stay_days, max_stay_days + 1):
            current_return = current_depart + timedelta(days=stay)
            
            # THE KEY CHECK: Ensure we aren't returning after our hard deadline
            if current_return <= end_dt:
                yield {
                    "departure_date": current_depart.strftime("%Y-%m-%d"),
                    "return_date": current_return.strftime("%Y-%m-%d"),
                    "stay_duration": stay
                }
            else:
                # If this stay is too long, any longer stay on this 
                # departure date will also be too long.
                break

        current_depart += timedelta(days=1)


def load_searches(filepath="searches.json"):
    # 1. Check if the file even exists
    if not os.path.exists(filepath):
        logger.warning(f"File not found: {filepath}")
        return []

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            
            # 2. Check if data is a list and has items
            if isinstance(data, list) and data:
                return data
            else:
                logger.warning(f"{filepath} is empty or not a valid list.")
                return []
                
    except json.JSONDecodeError:
        logger.warning(f"Failed to decode JSON in {filepath}. Check for syntax errors.")
        return []


def run_tracker():
    logger.info("=== Starting flight-price-tracker ===")

    try:
        # Setup DB session
        SessionLocal = Session()

        search_configs = load_searches('searches.json')

        for search_config in search_configs:
            logger.info(f"Start search for {search_config['origin']} -> {search_config['destination']}...")
            
            search = get_or_create_search(SessionLocal, **search_config)

            date_combos = generate_date_combinations(
                search.earliest_departure,
                search.latest_return,
                search.min_stay_days,
                search.max_stay_days
            )

            n_combos = 0
            for date_combo in date_combos:
                flight_data = get_flight_data(
                    origin=search.origin,
                    dest=search.destination,
                    depature_date=date_combo["departure_date"],
                    return_date=date_combo["return_date"],
                    one_way=False,
                    cheapest_flights_option=True,
                    more_flights=False,
                    max_stops=search.max_stops,
                    max_duration=dt_time(hour=search.max_duration_hours, minute=0),
                    top_n=3
                )

                if flight_data:
                    new_data = pd.DataFrame(flight_data)
                    new_data["search_id"] = search.id
                    new_data.to_sql('price_history', con=engine, if_exists='append', index=False)
                    n_combos += 1
                else:
                    continue

            logger.info(f"Completed search for {search.origin} -> {search.destination}. Processed {n_combos} date combinations.")
        
        logger.info("Flight-price-tracker run completed.")
        
    except Exception as e:
        logger.error(f"Scheduled task failed: {e}")
        

# Schedule the task
schedule.every().day.at("10:00").do(run_tracker)

if __name__ == "__main__":
    # logger.info("Scheduler active. Waiting...")
    # while True:
    #     schedule.run_pending()
    #     time.sleep(60) # Check every minute
    logger.info("Run price tracker once...")
    run_tracker()