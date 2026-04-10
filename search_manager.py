import os
import json
from pydantic import TypeAdapter, ValidationError
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from db import SearchDB
from schemas import SearchSchema
from logger import logger_setup


logger = logger_setup("search_manager.log")

load_dotenv()


def rename_dict_keys(d: dict, key_map: dict) -> dict:
    return {key_map.get(k, k): v for k, v in d.items() if k in key_map}


def read_searches_from_google_sheets(
        delete_after_processing: bool = False
        ) -> list[SearchDB]:

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
        "Destination": "destination",
        "Earliest Departure Date": "earliest_departure",
        "Latest Return Date": "latest_return",
        "Minimum Duration": "min_stay_days",
        "Maximum Duration": "max_stay_days",
        "Maximum Number of Stops": "max_stops",
        "Maximum Flight Duration": "max_duration_hours"
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
            print("No new requests found")
        else:
            print(f"Read {len(all_search_requests)} search requests:")

            for search_request in all_search_requests:
                print(search_request)

                search_request = rename_dict_keys(search_request, HEADERS_MAP)
                print(search_request)
                print(f"Processing: {search_request}")
                search_list.append(SearchSchema(**search_request))

            if delete_after_processing:
                start_row = 2
                end_row = len(all_search_requests) + 1

                sheet.delete_rows(start_row, end_row)

    except gspread.exceptions.APIError as e:
        print(f"API Error (Check permissions/sharing): {e}")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

    return search_list


def read_searches_from_json(filepath="searches.json") -> list[SearchSchema]:
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


def write_searches_to_db(session, new_searches: list[SearchSchema]) -> None:
    for search in new_searches:
        try:
            # Attempt to find the existing record
            instance = session.query(SearchDB).filter_by(**search.model_dump(exclude={'id'})).first()

            if instance:
                pass
            else:
                # If not found, create it using the same dictionary
                instance = SearchDB(**search.model_dump())
                session.add(instance)
                session.commit()
                session.refresh(instance)
                logger.info(f"New search created (ID: {instance.id}).")
        except Exception as e:
            logger.error(f"Failed to process search {search}: {e}")


def update_search_id(session, search: SearchSchema) -> SearchSchema:
    try:
        instance = session.query(SearchDB).filter_by(**search.model_dump(exclude={'id'})).first()

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
