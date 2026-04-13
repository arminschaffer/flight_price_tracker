from datetime import timedelta, datetime
from typing import Generator

from logger import logger_setup
from schemas import FlightSchema, SearchSchema, ConnectionSchema
from db import Session, FlightDB
from search_manager import manage_searches
from web_scraper import get_flight_data


logger = logger_setup("tracker.log")


def generate_date_combinations(search: SearchSchema) -> Generator[ConnectionSchema, None, None]:

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


def write_flights_to_db(session, flight_data: list[FlightSchema], search: SearchSchema) -> None:
    """
    Converts list of FlightSchema to FlightDB objects and saves them to the database.
    """
    if not flight_data:
        logger.info("No flight data to save.")
        return

    new_flights = [
        FlightDB(
            **flight.model_dump(exclude={"origin", "destination"}),
            search_id=search.id
        )
        for flight in flight_data
    ]

    try:
        session.add_all(new_flights)
        session.commit()
        logger.info(f"Successfully saved {len(new_flights)} flights to the database.")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save flights to DB: {e}")


def run_tracker():
    logger.info("=== Starting flight-price-tracker ===")

    try:
        # Setup DB session
        SessionLocal = Session()

        search_list = manage_searches(SessionLocal, "searches.json")

        for search in search_list:
            logger.info(
                f"Start search for {search.origin} -> {search.destination}..."
            )

            connection_generator = generate_date_combinations(search)

            n_combos = 0
            for connection in connection_generator:
                dep_date_obj = datetime.strptime(connection.departure_date, "%Y-%m-%d").date()

                if dep_date_obj < datetime.now().date():
                    logger.info(
                        f"Skipping date combo. Departure date {connection.departure_date} is in the past."
                    )
                    continue

                flight_data = get_flight_data(
                    connection=connection,
                    one_way=False,
                    cheapest_flights_option=True,
                    more_flights=False,
                    top_n=3,
                )

                write_flights_to_db(SessionLocal, flight_data, search)
                n_combos += 1

            logger.info(
                f"Completed search for {search.origin} -> {search.destination}. "
                f"Processed {n_combos} date combinations."
            )

        logger.info("Flight-price-tracker run completed.")

    except Exception as e:
        logger.error(f"Scheduled task failed: {e}")
