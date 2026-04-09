import os
import json
import logging
import schedule
import time
import pandas as pd
from pydantic import TypeAdapter, ValidationError
from logging.handlers import RotatingFileHandler
from datetime import timedelta, datetime
from typing import Generator

from schemas import SearchSchema, ConnectionSchema
from db import Session, engine, SearchDB
from web_scraper import get_flight_data


# --- 1. LOGGING SETUP ---
logger = logging.getLogger("FlightPriceTracker")
logger.setLevel(logging.INFO)

# Rotate logs at 5MB, keep 3 backup files
file_handler = RotatingFileHandler(
    "tracker.log", maxBytes=2 * 1024 * 1024, backupCount=3, delay=False
)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def get_or_create_search_entry(session, search: SearchSchema) -> SearchSchema:
    """
    Checks if a search with specific parameters exists,
    otherwise creates a new one.
    """
    # Attempt to find the existing record
    instance = session.query(SearchDB).filter_by(**search.model_dump(exclude={'id'})).first()

    if instance:
        logger.info(f"Search found in DB (ID: {instance.id}).")
        return SearchSchema(id=instance.id, **search.model_dump(exclude={'id'}))
    else:
        # If not found, create it using the same dictionary
        instance = SearchDB(**search.model_dump())
        session.add(instance)
        session.commit()
        session.refresh(instance)
        logger.info(f"New search created (ID: {instance.id}).")
        return SearchSchema(id=instance.id, **search.model_dump(exclude={'id'}))


def generate_date_combinations(
        search: SearchSchema
        ) -> Generator[ConnectionSchema, None, None]:

    # Convert strings to datetime objects
    start_dt = datetime.strptime(search.earliest_departure, "%Y-%m-%d")
    end_dt = datetime.strptime(search.latest_return, "%Y-%m-%d")

    # The absolute latest someone could depart is (Latest Return - Min Stay)
    latest_departure_possible = end_dt - timedelta(days=search.min_stay_days)

    current_depart = start_dt
    while current_depart <= latest_departure_possible:

        for stay in range(search.min_stay_days, search.max_stay_days + 1):
            current_return = current_depart + timedelta(days=stay)

            # THE KEY CHECK: Ensure we aren't returning after our hard deadline
            if current_return <= end_dt:
                yield ConnectionSchema(
                    origin=search.origin,
                    destination=search.destination,
                    departure_date=current_depart.strftime("%Y-%m-%d"),
                    return_date=current_return.strftime("%Y-%m-%d"),
                    stay_duration=stay,
                    max_stops=search.max_stops,
                    max_duration_hours=search.max_duration_hours
                )
            else:
                break

        current_depart += timedelta(days=1)


def load_searches(filepath="searches.json") -> list[SearchSchema]:
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "r") as f:
            raw_data = json.load(f)

        # This one line validates every item in the list
        return TypeAdapter(list[SearchSchema]).validate_python(raw_data)

    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Data loading failed in {filepath}: {e}")
        return []


def run_tracker():
    logger.info("=== Starting flight-price-tracker ===")

    try:
        # Setup DB session
        SessionLocal = Session()

        search_list = load_searches("searches.json")

        for search in search_list:
            logger.info(
                f"Start search for {search.origin} "
                f"-> {search.destination}..."
            )

            # If search does not exist, create new one in DB
            search = get_or_create_search_entry(SessionLocal, search)

            connection_generator = generate_date_combinations(search)

            n_combos = 0
            for connection in connection_generator:
                dep_date_obj = datetime.strptime(connection.departure_date, "%Y-%m-%d").date()

                if dep_date_obj < datetime.now().date():
                    logger.info(
                        "Skipping date combo. Departure date "
                        f"{connection.departure_date} is in the past."
                    )
                    continue

                flight_data = get_flight_data(
                    connection=connection,
                    one_way=False,
                    cheapest_flights_option=True,
                    more_flights=False,
                    top_n=3,
                )

                if flight_data:
                    new_data = pd.DataFrame(flight_data)
                    new_data["search_id"] = search.id
                    new_data.to_sql(
                        "price_history", con=engine, if_exists="append", index=False
                    )
                    n_combos += 1
                else:
                    continue

            logger.info(
                f"Completed search for {search.origin} -> {search.destination}. "
                f"Processed {n_combos} date combinations."
            )

        logger.info("Flight-price-tracker run completed.")

    except Exception as e:
        logger.error(f"Scheduled task failed: {e}")


# Schedule the task
schedule_time = "10:00"
schedule.every().day.at(schedule_time).do(run_tracker)

if __name__ == "__main__":
    RUN_MODE_SCHEDULED = True  # Change to True to enable scheduling

    if RUN_MODE_SCHEDULED:
        if datetime.now().time() > datetime.strptime(schedule_time, "%H:%M").time():
            logger.info(
                f"Scheduled time {schedule_time} has already passed today. "
                f"Running tracker immediately before scheduling."
            )
            run_tracker()
        logger.info("Scheduler active. Waiting...")
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    else:
        logger.info("Run price tracker once...")
        run_tracker()
