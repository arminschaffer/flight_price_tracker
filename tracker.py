from datetime import datetime, timedelta
import time

from logger import logger_setup
from schemas import FlightSchema, ConnectionSchema
from db import FlightDB, PriceListDB
from web_scraper import get_flight_data, get_price_list


logger = logger_setup("tracker.log", logger_name="tracker")


def write_flights_to_db(
        session,
        flight_data: list[FlightSchema],
        connection: ConnectionSchema
        ) -> None:
    """
    Converts list of FlightSchema to FlightDB objects and saves them to the database.
    """
    if not flight_data:
        logger.warning("No flight data to save.")
        return

    new_flights = [
        FlightDB(
            **flight.model_dump(exclude={"origin", "destination"}),
            search_id=connection.search_id,
            price_list_id=connection.id
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
        raise


def write_price_list_to_db(
        session,
        connection: ConnectionSchema
        ) -> ConnectionSchema:
    new_connection = PriceListDB(
        price_list=connection.price_list, search_id=connection.search_id
        )

    try:
        session.add(new_connection)
        session.commit()
        logger.info("Successfully saved price snapshot to the database.")
        return ConnectionSchema(id=new_connection.id, **connection.model_dump(exclude={'id'}))
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save price snapshot to DB: {e}")
        raise


def check_departure_date_in_past(connection: ConnectionSchema) -> bool:
    dep_date_obj = connection.departure_date

    if dep_date_obj < datetime.now().date():
        logger.info(
            f"Skipping connection. Departure date {connection.departure_date} is in the past."
        )
        return True
    return False


def run_tracker(SessionLocal, searches):
    try:
        timer_tracker_start = time.time()

        for search in searches:
            timer_search_start = time.time()
            logger.info("========================================")
            logger.info(
                f"Start search for {search.origin} -> {search.destination}..."
            )
            for connection in search.connections:
                if check_departure_date_in_past(connection):
                    continue

                connection = get_price_list(connection)
                connection = write_price_list_to_db(SessionLocal, connection)

                flight_data = get_flight_data(
                    connection=connection,
                    cheapest_flights=False,
                    more_flights=False,
                    top_n=5,
                )
                connection.flights = flight_data
                write_flights_to_db(SessionLocal, flight_data, connection)

            time_search = str(timedelta(seconds=int(time.time() - timer_search_start)))
            logger.info(
                f"Completed search for {search.origin} -> {search.destination} ({time_search})."
            )
        time_tracker = str(timedelta(seconds=int(time.time() - timer_tracker_start)))
        logger.info(f"Flight-price-tracker run completed ({time_tracker}).")

    except Exception as e:
        logger.error(f"Scheduled task failed: {e}")
