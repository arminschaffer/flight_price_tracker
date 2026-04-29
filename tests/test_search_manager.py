import pytest
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from search_manager import (
    write_searches_to_db,
    read_searches_from_db,
    read_searches_from_json,
    add_connections_to_search
)
from db import SearchDB, Base
from schemas import SearchSchema


@pytest.fixture
def mock_db_session():
    """Creates a fresh in-memory database for every test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_searches() -> list[SearchSchema]:
    """Returns a mock SearchSchema object for testing."""
    return [
        SearchSchema(
            one_way=False,
            origin="VIE",
            destination="LHR",
            earliest_departure=date(year=2026, month=1, day=1),
            latest_departure=date(year=2026, month=1, day=2),
            earliest_return=date(year=2026, month=1, day=15),
            latest_return=date(year=2026, month=1, day=16),
            min_stay_days=15,
        )
    ]


@pytest.fixture
def dynamic_mock_searches() -> list[SearchSchema]:
    """Returns a mock SearchSchema with dynamic dates object for testing."""
    today = datetime.now().date()
    return [
        # Full future search
        SearchSchema(
            one_way=False,
            origin="VIE",
            destination="LHR",
            earliest_departure=today + timedelta(days=30),
            latest_departure=today + timedelta(days=31),
            earliest_return=today + timedelta(days=35),
            latest_return=today + timedelta(days=36),
            min_stay_days=6,
        ),
        # Past date search
        SearchSchema(
            one_way=False,
            origin="VIE",
            destination="LHR",
            earliest_departure=today - timedelta(days=1),
            latest_departure=today + timedelta(days=1),
            earliest_return=today + timedelta(days=5),
            latest_return=today + timedelta(days=6),
            max_stay_days=6,
        )
    ]


@pytest.fixture
def dynamic_mock_one_way_searches() -> list[SearchSchema]:
    """Returns a mock one way SearchSchema with dynamic dates object for testing."""
    today = datetime.now().date()
    return [
        # Full future search
        SearchSchema(
            one_way=True,
            origin="VIE",
            destination="LHR",
            earliest_departure=today + timedelta(days=30),
            latest_departure=today + timedelta(days=31),
        ),
        # Past date search
        SearchSchema(
            one_way=True,
            origin="VIE",
            destination="LHR",
            earliest_departure=today - timedelta(days=1),
            latest_departure=today + timedelta(days=1),
        ),
    ]


def test_create_search_new_record(mock_db_session, mock_searches):
    """Test that a record is created if it doesn't exist."""

    write_searches_to_db(mock_db_session, mock_searches)

    searches = read_searches_from_db(mock_db_session)

    assert searches[0].id is not None
    assert searches[0].origin == "VIE"

    # Verify the search is actually in the DB
    assert mock_db_session.query(SearchDB).count() == 1


def test_create_search_existing_record(mock_db_session, mock_searches):
    """Test that it returns the existing record without creating a duplicate."""
    # Pre-populate the DB
    existing = SearchDB(
        origin="VIE",
        destination="LHR",
        earliest_departure=date(year=2026, month=1, day=1),
        latest_departure=date(year=2026, month=1, day=2),
        earliest_return=date(year=2026, month=1, day=15),
        latest_return=date(year=2026, month=1, day=16),
        min_stay_days=15,
    )
    mock_db_session.add(existing)
    mock_db_session.commit()

    write_searches_to_db(mock_db_session, mock_searches)

    searches = read_searches_from_db(mock_db_session)

    assert searches[0].id == existing.id
    assert mock_db_session.query(
        SearchDB).count() == 1  # Still only one record


def test_create_search_new_record_with_existing_record(mock_db_session, mock_searches):
    """Test that it returns the existing record without creating a duplicate."""
    # Pre-populate the DB
    existing = SearchDB(
        origin="LHR",
        destination="VIE",
        earliest_departure=date(year=2026, month=1, day=1),
        latest_departure=date(year=2026, month=1, day=2),
        earliest_return=date(year=2026, month=1, day=15),
        latest_return=date(year=2026, month=1, day=16),
        min_stay_days=15,
    )
    mock_db_session.add(existing)
    mock_db_session.commit()

    write_searches_to_db(mock_db_session, mock_searches)

    searches = read_searches_from_db(mock_db_session)

    assert searches[0].id == existing.id
    assert searches[0].origin == "LHR"
    assert searches[1].id is not None
    assert searches[1].origin == "VIE"
    assert mock_db_session.query(SearchDB).count() == 2  # Two records in db


def test_read_searches_from_json():
    """Test that searches are correctly read from a JSON file."""
    searches = read_searches_from_json("searches_examples.json")
    assert len(searches) == 2
    assert searches[0].origin == "Vienna"
    assert searches[0].destination == "Lisbon"
    assert searches[1].destination == "London"


def test_add_connections_to_search(dynamic_mock_searches):
    searches = []
    for mock_search in dynamic_mock_searches:
        searches.append(add_connections_to_search(mock_search))
    print(searches[1].connections)
    assert len(searches) == 2
    assert len(searches[0].connections) == 3
    assert len(searches[1].connections) == 3


def test_add_connections_to_one_way_search(dynamic_mock_one_way_searches):
    searches = []
    for mock_search in dynamic_mock_one_way_searches:
        searches.append(add_connections_to_search(mock_search))
    assert len(searches) == 2
    assert len(searches[0].connections) == 2
    assert len(searches[1].connections) == 2
