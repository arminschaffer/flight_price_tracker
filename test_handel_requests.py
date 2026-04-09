import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from read_external_requests import create_search
from db import SearchDB, Base


# Fixture to set up the Database
@pytest.fixture
def db_session():
    """Creates a fresh in-memory database for every test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_search_new_record(db_session):
    """Test that a record is created if it doesn't exist."""
    search_params = {"origin": "VIE", "destination": "LHR", "earliest_departure": "2026-01-01", "latest_return": "2026-01-10"}

    # We pass the class 'Search' and the session
    result = create_search(db_session, **search_params)

    assert result.id is not None
    assert result.origin == "VIE"

    # Verify the search is actually in the DB
    assert db_session.query(SearchDB).count() == 1


def test_create_search_existing_record(db_session):
    """Test that it returns the existing record without creating a duplicate."""
    # Pre-populate the DB
    existing = SearchDB(origin="VIE", destination="LHR", earliest_departure="2026-01-01", latest_return="2026-01-10")
    db_session.add(existing)
    db_session.commit()

    search_params = {"origin": "VIE", "destination": "LHR", "earliest_departure": "2026-01-01", "latest_return": "2026-01-10"}
    result = create_search(db_session, **search_params)

    assert result.id == existing.id
    assert db_session.query(SearchDB).count() == 1  # Still only one record
