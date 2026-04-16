from datetime import datetime

from logger import logger_setup
from schemas import FlightSchema, ConnectionSchema
from db import Session, FlightDB, PriceListDB
from search_manager import manage_searches
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


def run_tracker():
    logger.info("=== Starting flight-price-tracker ===")

    try:
        # Setup DB session
        SessionLocal = Session()

        search_list = manage_searches(SessionLocal, "searches.json", filter_past_searches=True)

        for search in search_list:
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
                    cheapest_flights=True,
                    more_flights=False,
                    top_n=5,
                )
                connection.flights = flight_data
                write_flights_to_db(SessionLocal, flight_data, connection)

            logger.info(
                f"Completed search for {search.origin} -> {search.destination}."
            )

        logger.info("Flight-price-tracker run completed.")

    except Exception as e:
        logger.error(f"Scheduled task failed: {e}")
