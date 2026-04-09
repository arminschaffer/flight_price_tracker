import gspread
from google.oauth2.service_account import Credentials
from main import logger

from db import SearchDB


def rename_dict_keys(d: dict, key_map: dict) -> dict:
    return {key_map.get(k, k): v for k, v in d.items() if k in key_map}


def read_external_requests(
        delete_after_processing: bool = False
        ) -> list[SearchDB]:

    SPREADSHEET_ID = "1ZTGekZAL3LD_eNNgAYqJpuK2L7xZhVaCvhBRFdgjQMI"

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
        "google_key.json",
        scopes=SCOPES
        )
    client = gspread.authorize(creds)

    search_list = []

    try:
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1

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
                search_list.append(SearchDB(**search_request))

            if delete_after_processing:
                start_row = 2
                end_row = len(all_search_requests) + 1

                sheet.delete_rows(start_row, end_row)

    except gspread.exceptions.APIError as e:
        print(f"API Error (Check permissions/sharing): {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

    return search_list


def create_search(session, **search_data) -> SearchDB:
    """
    Checks if a search with specific parameters exists,
    otherwise creates a new one.
    """
    # Attempt to find the existing record
    instance = session.query(SearchDB).filter_by(**search_data).first()

    if instance:
        logger.info(f"Search found in DB (ID: {instance.id}).")
        return instance

    # If not found, create it using the same dictionary
    instance = SearchDB(**search_data)
    session.add(instance)
    session.commit()
    session.refresh(instance)
    logger.info(f"New search created (ID: {instance.id}).")
    return instance
