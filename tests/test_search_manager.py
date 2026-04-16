import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from search_manager import write_searches_to_db, read_searches_from_db, read_searches_from_json
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
def mock_search() -> list[SearchSchema]:
    """Returns a mock SearchSchema object for testing."""
    return [
        SearchSchema(
            one_way=False,
            origin="VIE",
            destination="LHR",
            earliest_departure=date(year=2026, month=1, day=1),
            latest_departure=date(year=2026, month=1, day=2),
            earliest_return=date(year=2026, month=1, day=15),
            latest_return=date(year=2026, month=1, day=30),
            )
    ]


def test_create_search_new_record(mock_db_session, mock_search):
    """Test that a record is created if it doesn't exist."""

    write_searches_to_db(mock_db_session, mock_search)

    searches = read_searches_from_db(mock_db_session)

    assert searches[0].id is not None
    assert searches[0].origin == "VIE"

    # Verify the search is actually in the DB
    assert mock_db_session.query(SearchDB).count() == 1


def test_create_search_existing_record(mock_db_session, mock_search):
    """Test that it returns the existing record without creating a duplicate."""
    # Pre-populate the DB
    existing = SearchDB(
        origin="VIE",
        destination="LHR",
        earliest_departure=date(year=2026, month=1, day=1),
        latest_departure=date(year=2026, month=1, day=2),
        earliest_return=date(year=2026, month=1, day=15),
        latest_return=date(year=2026, month=1, day=30),
        )
    mock_db_session.add(existing)
    mock_db_session.commit()

    write_searches_to_db(mock_db_session, mock_search)

    searches = read_searches_from_db(mock_db_session)

    assert searches[0].id == existing.id
    assert mock_db_session.query(SearchDB).count() == 1  # Still only one record


def test_create_search_new_record_with_existing_record(mock_db_session, mock_search):
    """Test that it returns the existing record without creating a duplicate."""
    # Pre-populate the DB
    existing = SearchDB(
        origin="LHR",
        destination="VIE",
        earliest_departure=date(year=2026, month=1, day=1),
        latest_departure=date(year=2026, month=1, day=2),
        earliest_return=date(year=2026, month=1, day=15),
        latest_return=date(year=2026, month=1, day=30),
        )
    mock_db_session.add(existing)
    mock_db_session.commit()

    write_searches_to_db(mock_db_session, mock_search)

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
    assert searches[1].destination == "Agadir"
