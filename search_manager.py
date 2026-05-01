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


# class SearchList:



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

        search_requests = sheet.get_all_records()

        if not search_requests:
            logger.info("No requests found in Google Sheets.")
        else:
            logger.info(f"{len(search_requests)} request(s) found in Google Sheets.")

            for search_request in search_requests:
                try:
                    search_request = rename_dict_keys(search_request, HEADERS_MAP)
                    search_request.pop('email', None)  # remove email for now
                    # search_request["one_way"] = False

                    cleaned_data = {k: v for k, v in search_request.items() if v != ""}

                    search = SearchSchema.model_validate(cleaned_data)
                    search_list.append(search)

                except Exception as e:
                    logger.error(f"Invalid search request {search_request}: {e}")

            if delete_after_processing:
                start_row = 2
                end_row = len(search_requests) + 1

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
    search_list = []

    if not os.path.exists(filepath):
        logger.warning(f"Search json file does not exist: {filepath}.")
        return []

    try:
        with open(filepath, "r") as f:
            search_requests = json.load(f)

        logger.info(f"{len(search_requests)} search(es) loaded from {filepath}.")
        for search_request in search_requests:
            try:
                search = SearchSchema.model_validate(search_request)
                search_list.append(search)
            except Exception as e:
                logger.error(f"Invalid search request {search_request}: {e}")
        return search_list

    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Loading searches from {filepath} failed: {e}")
        return []


def delete_searches_from_db(session, searches: list[SearchSchema]) -> None:
    if not searches:
        logger.info("No searches deleted.")
        return

    deleted_count = 0
    for search in searches:
        try:
            instance = session.query(SearchDB).filter_by(
                    **search.model_dump(exclude={
                        'id', 'created_at', 'created_by', 'connections', 'one_way'
                        })).first()

            if instance:
                session.delete(instance)
                deleted_count += 1
                logger.info(f"Marked search for deletion (ID: {instance.id}).")
            else:
                logger.warning(f"Search not found in DB, skipping deletion: {search}")
        
        except Exception as e:
            logger.error(f"Error deleting search {search}: {e}")

    # Commit the changes
    if deleted_count > 0:
        try:
            session.commit()
            logger.info(f"Successfully deleted {deleted_count} searches from DB.")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to commit deletions: {e}")


def write_searches_to_db(session, searches: list[SearchSchema]) -> None:
    if not searches:
        logger.info("No new searches added.")
        return

    added_count = 0
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
                added_count += 1
                session.flush()
                logger.info(f"New search queued (ID: {instance.id}).")
        except Exception as e:
            logger.error(f"Error adding search {search}: {e}")

    # commit new searches to DB
    if added_count > 0:
        try:
            session.commit()
            logger.info(f"Successfully added {added_count} searches from DB.")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed final commit: {e}")      


def read_searches_from_db(session) -> list[SearchSchema]:
    try:
        search_records = session.query(SearchDB).all()
        return [SearchSchema.model_validate(record.__dict__) for record in search_records]
    except Exception as e:
        logger.error(f"Failed to read searches from DB: {e}")
        return []


def add_connections_to_search(search: SearchSchema) -> SearchSchema:
    try:
        today = datetime.now().date()
        if search.one_way:
            early_dep = search.earliest_departure
            late_dep = search.latest_departure
            current_dep = max(early_dep, today)
            while (current_dep <= late_dep):
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

            if len(search.connections) == 0:
                logger.warning(f"No connections added for search ID {search.id}.")

            return search

        elif (search.earliest_return and search.latest_return):
            early_dep = max(search.earliest_departure, today)
            late_dep = search.latest_departure
            early_ret = max(search.earliest_return, today)
            late_ret = search.latest_return

            departure_dates = pd.date_range(start=early_dep, end=late_dep)
            return_dates = pd.date_range(start=early_ret, end=late_ret)

            for dep in departure_dates:
                for ret in return_dates:
                    if ret < dep:
                        continue

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

            if len(search.connections) == 0:
                logger.warning(f"No connections added for search ID {search.id}.")

            return search

        else:
            logger.error(f"Search ID {search.id} has invalid parameters for generating connections.")
            raise ValueError(
                f"one_way flag (={search.one_way}) cannot be false with "
                "earliest_return (={search.earliest_return}) or "
                "latest_return (={search.latest_return}) being None."
                )

    except Exception as e:
        logger.error(f"Search ID {search.id} has invalid parameters for generating connections: {e}.")
        raise


def search_is_same(s1: SearchSchema, s2: SearchSchema) -> bool:
    exclude_set = {'id', 'created_at', 'created_by', 'connections', 'one_way'}
    
    dict1 = s1.model_dump(exclude=exclude_set)
    dict2 = s2.model_dump(exclude=exclude_set)
    
    return dict1 == dict2


def sync_search_lists(
        active_searches: list[SearchSchema], 
        searches_db: list[SearchSchema]
        ) -> tuple[list[SearchSchema], list[SearchSchema]]:
    
    new_searches = [
        a for a in active_searches 
        if not any(search_is_same(a, db) for db in searches_db)
    ]

    old_searches = [
        db for db in searches_db 
        if not any(search_is_same(db, a) for a in active_searches)
    ]

    return new_searches, old_searches


def remove_expired_searches(searches: list[SearchSchema]) -> list[SearchSchema]:
    today = datetime.now().date()
    return [search for search in searches if search.latest_departure >= today]


def manage_searches(
        session, 
        read_google_sheets: bool = True,
        read_json: bool = True,
        json_file: str = "searches.json"
        ) -> list[SearchSchema]:
    
    # Load active searches
    active_searches = []
    if read_google_sheets:
        active_searches.extend(read_searches_from_google_sheets(delete_after_processing=False))
    if read_json:
        active_searches.extend(read_searches_from_json(json_file))

    active_searches = remove_expired_searches(active_searches)

    # Load searches from db
    searches_db = read_searches_from_db(session)

    # Find new searches and no longer active ones
    searches_to_add, searches_to_delete = sync_search_lists(active_searches, searches_db)

    # Delete searches
    delete_searches_from_db(session, searches_to_delete)

    # Write new searches to db
    write_searches_to_db(session, searches_to_add)

    # Read all active searches from dn
    searches = read_searches_from_db(session)
    
    # No searches
    if not searches:
        logger.warning("No searches found.")
        return []

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
    # Google sheet test run
    print(read_searches_from_google_sheets(delete_after_processing=False))
