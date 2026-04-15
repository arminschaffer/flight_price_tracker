import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from search_manager import get_or_create_search_entry
from db import Base, FlightDB, PriceSnapshotDB
from schemas import SearchSchema, FlightSchema
from tracker import write_flights_to_db, write_price_snapshot_to_db


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
def mock_search() -> SearchSchema:
    """Returns a mock SearchSchema object for testing."""
    return SearchSchema(
        origin="VIE",
        destination="LHR",
        earliest_departure=date(year=2026, month=1, day=1),
        latest_return=date(year=2026, month=1, day=30),
    )


@pytest.fixture
def mock_flights() -> list[FlightSchema]:
    return [
        FlightSchema(
            origin="VIE",
            destination="LHR",
            airline="Test Airline",
            departure_date=date(year=2026, month=1, day=1),
            return_date=date(year=2026, month=1, day=30),
            price=100,
            duration="2 hr 0 min",
            stops=0
            ),
        FlightSchema(
            origin="VIE",
            destination="LHR",
            airline="Test Airline",
            departure_date=date(year=2026, month=1, day=1),
            return_date=date(year=2026, month=1, day=30),
            price=50,
            duration="5 hr 0 min",
            stops=0
            ),
        FlightSchema(
            origin="VIE",
            destination="LHR",
            airline="Test Airline",
            departure_date=date(year=2026, month=1, day=1),
            return_date=date(year=2026, month=1, day=30),
            price=50,
            duration="3 hr 0 min",
            stops=3
            ),
    ]


@pytest.fixture
def mock_snapshot() -> list[int]:
    return [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650]


def test_write_flights_to_db_success(mock_db_session, mock_search: SearchSchema, mock_flights: list[FlightSchema]):
    """Test that flights are correctly saved and linked to a search."""

    search_record = get_or_create_search_entry(mock_db_session, mock_search)

    write_flights_to_db(mock_db_session, mock_flights, search_record)

    # Check that 2 flights were saved
    saved_flights = mock_db_session.query(FlightDB).all()
    assert len(saved_flights) == 3

    # Check that they are linked to the correct search ID
    for flight in saved_flights:
        assert flight.search_id == search_record.id

    # Check specific data integrity for one entry
    saved_flights = mock_db_session.query(FlightDB).all()
    saved_flight = saved_flights[0]
    assert saved_flight.price == 100
    assert saved_flight.stops == 0

    saved_flight = saved_flights[2]
    assert saved_flight.price == 50
    assert saved_flight.stops == 3


def test_write_flights_to_db_empty_list(mock_db_session, mock_search: SearchSchema):
    """Test that the function handles an empty list gracefully."""
    search_record = get_or_create_search_entry(mock_db_session, mock_search)

    # Should not raise an error or add anything to DB
    write_flights_to_db(mock_db_session, [], search_record)

    assert mock_db_session.query(FlightDB).count() == 0


def test_write_price_snapshot_to_db(mock_db_session, mock_snapshot: list[int], mock_search: SearchSchema):
    """Test that price snapshots are correctly saved and linked to a search."""
    search_record = get_or_create_search_entry(mock_db_session, mock_search)

    # Should not raise an error or add anything to DB
    write_price_snapshot_to_db(mock_db_session, mock_snapshot, search_record)

    assert mock_db_session.query(PriceSnapshotDB).count() == 1
    assert mock_db_session.query(PriceSnapshotDB).first().price_list == mock_snapshot
