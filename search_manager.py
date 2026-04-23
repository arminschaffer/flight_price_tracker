import os
import json
import pandas as pd
from datetime import datetime, timedelta
from pydantic import TypeAdapter, ValidationError
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from db import SearchDB
from schemas import ConnectionSchema, SearchSchema
from logger import logger_setup


logger = logger_setup("search_manager.log", logger_name="search_manager")

load_dotenv()


def rename_dict_keys(d: dict, key_map: dict) -> dict:
    return {key_map.get(k, k): v for k, v in d.items() if k in key_map}


def read_searches_from_google_sheets(
        delete_after_processing: bool = False
        ) -> list[SearchSchema]:

    spreadsheet_id = str(os.getenv("GOOGLE_SPREADSHEET_ID"))
    credentials_file = str(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    # new header names
    HEADERS_MAP = {
        "Timestamp": "created_at",
        "Origin": "origin",
        "Earliest Departure Date": "earliest_departure",
        "Latest Departure Date": "latest_departure",
        "Destination": "destination",
        "Earliest Return Date": "earliest_return",
        "Latest Return Date": "latest_return",
        "Min Duration": "min_stay_days",
        "Max Duration": "max_stay_days",
        "Max Stops": "max_stops",
        "Max Flight Duration": "max_duration_hours",
        "Name": "created_by",
        "Email": "email"
    }

    creds = Credentials.from_service_account_file(
        credentials_file,
        scopes=SCOPES
        )
    client = gspread.authorize(creds)

    search_list = []

    try:
        sheet = client.open_by_key(spreadsheet_id).sheet1

        all_search_requests = sheet.get_all_records()

        if not all_search_requests:
            logger.info("No requests found in Google Sheets.")
        else:
            logger.info(f"{len(all_search_requests)} request(s) found in Google Sheets.")

            for search_request in all_search_requests:
                search_request = rename_dict_keys(search_request, HEADERS_MAP)
                search_request.pop('email', None)  # remove email for now
                search_request["one_way"] = False

                # fill default values
                if search_request.get("destination") == "":
                    search_request["destination"] = None
                if search_request.get("earliest_return") == "":
                    search_request["earliest_return"] = None
                    search_request["one_way"] = True
                if search_request.get("latest_return") == "":
                    search_request["latest_return"] = None
                    search_request["one_way"] = True
                if search_request.get("min_stay_days") == "":
                    search_request["min_stay_days"] = None
                if search_request.get("max_stay_days") == "":
                    search_request["max_stay_days"] = None
                if search_request.get("max_stops") == "":
                    search_request["max_stops"] = 0
                if search_request.get("max_duration_hours") == "":
                    search_request["max_duration_hours"] = 12

                search_list.append(SearchSchema(**search_request))

            if delete_after_processing:
                start_row = 2
                end_row = len(all_search_requests) + 1

                sheet.delete_rows(start_row, end_row)
                logger.info("Google Sheets requests cleared.")

    except gspread.exceptions.APIError as e:
        print(f"API Error (Check permissions/sharing): {e}")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

    return search_list


def read_searches_from_json(filepath: str = "searches.json") -> list[SearchSchema]:
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "r") as f:
            raw_data = json.load(f)

        # This one line validates every item in the list
        return TypeAdapter(list[SearchSchema]).validate_python(raw_data)
        logger.info(f"{len(raw_data)} search(es) loaded from {filepath}.")

    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Loading searches from {filepath} failed: {e}")
        return []


def write_searches_to_db(session, searches: list[SearchSchema]) -> None:
    for search in searches:
        try:
            instance = session.query(SearchDB).filter_by(
                **search.model_dump(exclude={
                    'id', 'created_at', 'created_by', 'connections', 'one_way'
                    })).first()

            if instance:
                pass
            else:
                instance = SearchDB(**search.model_dump(exclude={'connections', 'one_way'}))
                session.add(instance)
                session.flush()
                logger.info(f"New search queued (ID: {instance.id}).")
        except Exception as e:
            logger.error(f"Failed to process search {search}: {e}")
    # commit new searches to DB
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Final commit failed: {e}")


def read_searches_from_db(session) -> list[SearchSchema]:
    try:
        search_records = session.query(SearchDB).all()
        return [SearchSchema.model_validate(record.__dict__) for record in search_records]
    except Exception as e:
        logger.error(f"Failed to read searches from DB: {e}")
        return []


def add_connections_to_search(search: SearchSchema) -> SearchSchema:
    if search.one_way:
        early_dep = search.earliest_departure
        late_dep = search.latest_departure
        current_dep = early_dep
        while current_dep <= late_dep:
            connection = ConnectionSchema(
                search_id=search.id,
                one_way=search.one_way,
                origin=search.origin,
                destination=search.destination,
                departure_date=current_dep,
                max_stops=search.max_stops,
                max_duration_hours=search.max_duration_hours
            )
            search.connections.append(connection)
            current_dep += timedelta(days=1)
        return search

    elif (search.earliest_return and search.latest_return):
        early_dep = search.earliest_departure
        late_dep = search.latest_departure
        early_ret = search.earliest_return
        late_ret = search.latest_return

        departure_dates = pd.date_range(start=early_dep, end=late_dep)
        return_dates = pd.date_range(start=early_ret, end=late_ret)

        for dep in departure_dates:
            for ret in return_dates:
                stay_duration = (ret - dep).days + timedelta(days=1).days

                if (
                    (search.min_stay_days is None or stay_duration >= search.min_stay_days)
                    and (search.max_stay_days is None or stay_duration <= search.max_stay_days)
                ):
                    connection = ConnectionSchema(
                        search_id=search.id,
                        one_way=search.one_way,
                        origin=search.origin,
                        departure_date=dep,
                        destination=search.destination,
                        return_date=ret,
                        stay_duration=stay_duration,
                        max_stops=search.max_stops,
                        max_duration_hours=search.max_duration_hours
                    )
                    search.connections.append(connection)
        return search

    else:
        logger.error(
            f"Search ID {search.id} has invalid parameters for generating connections."
        )
        raise


def manage_searches(session, json_file: str = "searches.json", filter_past_searches: bool = True) -> list[SearchSchema]:
    # handle google sheet requests
    search_list = read_searches_from_google_sheets(delete_after_processing=False)

    if search_list:
        write_searches_to_db(session, search_list)

    # handle json file requests
    search_list = read_searches_from_json(json_file)

    if search_list:
        write_searches_to_db(session, search_list)

    searches = read_searches_from_db(session)

    if filter_past_searches:
        today = datetime.now().date()
        searches = [search for search in searches if search.earliest_departure >= today]

    # add connections to each search
    searches = [add_connections_to_search(search) for search in searches]

    return searches


def update_search_id(session, search: SearchSchema) -> SearchSchema:
    try:
        instance = session.query(SearchDB).filter_by(
            **search.model_dump(exclude={'id', 'created_at', 'created_by', 'one_way'})
            ).first()

        if not instance:
            logger.warning(f"Search parameters not found in DB: {search}")
            raise ValueError("No matching search record found in database.")

        logger.info(f"ID resolved: {instance.id}")
        return SearchSchema(id=instance.id, **search.model_dump(exclude={'id'}))

    except Exception as e:
        logger.error(f"Failed to update search ID for {search}: {e}")
        raise


def get_or_create_search_entry(session, search: SearchSchema) -> SearchSchema:
    """
    Checks if a search with specific parameters exists,
    otherwise creates a new one.
    """
    # Attempt to find the existing record
    instance = session.query(SearchDB).filter_by(
        **search.model_dump(exclude={
            'id', 'created_at', 'created_by', 'connections', 'one_way'
            })).first()

    if instance:
        logger.info(f"Search found in DB (ID: {instance.id}).")
        return SearchSchema(id=instance.id, **search.model_dump(exclude={'id'}))
    else:
        instance = SearchDB(**search.model_dump(exclude={'id', 'connections', 'one_way'}))
        session.add(instance)
        session.commit()
        session.refresh(instance)
        logger.info(f"New search created (ID: {instance.id}).")
        return SearchSchema(id=instance.id, **search.model_dump(exclude={'id'}))


if __name__ == "__main__":
    # quick google sheet test run
    print(read_searches_from_google_sheets(delete_after_processing=False))
