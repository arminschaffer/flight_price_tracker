import pytest
from datetime import date, datetime, timedelta
from web_scraper import GoogleFlightsScraper, generate_google_flights_url, flight_data_filter
from schemas import ConnectionSchema, FlightSchema


@pytest.fixture
def mock_flights() -> list[FlightSchema]:
    return [
        # good flight
        FlightSchema(
            origin="VIE",
            destination="LHR",
            airline="Test Airline",
            departure_date=date(year=2026, month=1, day=1),
            return_date=date(year=2026, month=1, day=5),
            flight_time="6:00 AM - 8:00 AM",
            price=100,
            duration="2 hr 0 min",
            stops=0
            ),
        # too long
        FlightSchema(
            origin="VIE",
            destination="LHR",
            airline="Test Airline",
            departure_date=date(year=2026, month=1, day=1),
            return_date=date(year=2026, month=1, day=5),
            flight_time="6:00 AM - 11:00 AM",
            price=50,
            duration="5 hr 0 min",
            stops=0
            ),
        # too many stops
        FlightSchema(
            origin="VIE",
            destination="LHR",
            airline="Test Airline",
            departure_date=date(year=2026, month=1, day=1),
            return_date=date(year=2026, month=1, day=5),
            flight_time="7:00 AM - 10:00 AM",
            price=50,
            duration="3 hr 0 min",
            stops=3
            ),
    ]


@pytest.fixture
def mock_connection() -> ConnectionSchema:
    return ConnectionSchema(
        origin="VIE",
        destination="LHR",
        departure_date=date(year=2026, month=1, day=1),
        return_date=date(year=2026, month=1, day=5),
        stay_duration=4,
        max_stops=1,
        max_duration_hours=3
    )


@pytest.fixture
def dynamic_mock_connection():
    today = datetime.now().date()
    departure_date = today + timedelta(days=30)
    return_date = today + timedelta(days=35)
    return ConnectionSchema(
        origin="VIE",
        destination="LHR",
        departure_date=departure_date,
        return_date=return_date,
        stay_duration=5,
        max_stops=1,
        max_duration_hours=3
    )


def test_generate_url_one_way(mock_connection: ConnectionSchema):
    """Test that the URL generator formats one-way queries correctly."""
    url, query = generate_google_flights_url(mock_connection, one_way=False)
    assert "VIE" in query
    assert "LHR" in query
    assert url.startswith("http")


def test_flight_data_filter(mock_flights: list[FlightSchema], mock_connection: ConnectionSchema):
    """Test that the filter correctly removes flights with too many stops."""
    filtered = flight_data_filter(mock_flights, mock_connection)
    assert len(filtered) == 1
    assert filtered[0].stops == 0
    assert filtered[0].duration == "2 hr 0 min"


def test_scrape_execution(dynamic_mock_connection: ConnectionSchema):
    """Runs a live scrape to ensure the Chrome setup and extraction works."""

    test_url, _ = generate_google_flights_url(dynamic_mock_connection)
    scraper = GoogleFlightsScraper(headless=True)
    results = scraper.scrape_flights(test_url, dynamic_mock_connection, cheapest_flights=True)

    assert isinstance(results, list)
    assert type(results[0].price) is int
    assert type(results[0].airline) is str
    assert type(results[0].duration) is str


def test_price_range_scrape_execution(dynamic_mock_connection: ConnectionSchema):
    """Runs a live scrape to ensure the Chrome setup and extraction works."""

    test_url, _ = generate_google_flights_url(dynamic_mock_connection)
    scraper = GoogleFlightsScraper(headless=True)
    results = scraper.scrape_price_range(test_url)
    print(results)
    assert isinstance(results, list)
    assert len(results) > 0
    assert type(results[0]) is int
