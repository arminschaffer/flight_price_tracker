import pytest
from datetime import time as dt_time
from web_scraper import generate_google_flights_url, flight_data_filter, scrape_google_flights

## --- UNIT TESTS (No Browser Required) ---

def test_generate_url_one_way():
    """Test that the URL generator formats one-way queries correctly."""
    url, query = generate_google_flights_url("VIE", "LHR", "2026-01-01", None, one_way=True)
    assert "oneway" in query
    assert "VIE" in query
    assert "LHR" in query
    assert url.startswith("http")

def test_flight_data_filter_stops():
    """Test that the filter correctly removes flights with too many stops."""
    mock_data = [
        {"stops": 0, "duration": "2h 0m", "price": 100},
        {"stops": 2, "duration": "5h 0m", "price": 50},
    ]
    # Filter for max 1 stop
    filtered = flight_data_filter(mock_data, max_stops=1)
    assert len(filtered) == 1
    assert filtered[0]["stops"] == 0

def test_flight_data_filter_duration():
    """Test that the filter handles flight duration limits."""
    mock_data = [
        {"stops": 0, "duration": "1 hr 30 min", "price": 100},
        {"stops": 0, "duration": "10 hr 0 min", "price": 200},
    ]
    # Filter for max 5 hours
    limit = dt_time(hour=5, minute=0)
    filtered = flight_data_filter(mock_data, max_duration=limit)
    assert len(filtered) == 1
    assert "1 hr 30 min" in filtered[0]["duration"]

## --- INTEGRATION TEST (slow) ---

# @pytest.mark.skip(reason="Slow test - runs actual browser")
def test_scrape_execution():
    """Runs a live scrape to ensure the Chrome setup and extraction works."""
    
    test_url, _ = generate_google_flights_url("VIE", "LHR", "2026-06-01", "2026-06-05")
    results = scrape_google_flights(test_url, "2026-06-01", "2026-06-05", cheapest_flights_option=True)
    
    assert isinstance(results, list)
    if len(results) > 0:
        assert "price" in results[0]
        assert "airline" in results[0]