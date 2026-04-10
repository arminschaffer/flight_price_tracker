import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from search_manager import get_or_create_search_entry
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
def mock_search() -> SearchSchema:
    """Returns a mock SearchSchema object for testing."""
    return SearchSchema(
        origin="VIE",
        destination="LHR",
        earliest_departure="2026-01-01",
        latest_return="2026-01-30",
    )


def test_create_search_new_record(mock_db_session, mock_search):
    """Test that a record is created if it doesn't exist."""

    result = get_or_create_search_entry(mock_db_session, mock_search)

    assert result.id is not None
    assert result.origin == "VIE"

    # Verify the search is actually in the DB
    assert mock_db_session.query(SearchDB).count() == 1


def test_create_search_existing_record(mock_db_session, mock_search):
    """Test that it returns the existing record without creating a duplicate."""
    # Pre-populate the DB
    existing = SearchDB(origin="VIE", destination="LHR", earliest_departure="2026-01-01", latest_return="2026-01-30")
    mock_db_session.add(existing)
    mock_db_session.commit()

    result = get_or_create_search_entry(mock_db_session, mock_search)

    assert result.id == existing.id
    assert mock_db_session.query(SearchDB).count() == 1  # Still only one record
