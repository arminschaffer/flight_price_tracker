from datetime import date, datetime
from pydantic import BaseModel, Field


class SearchSchema(BaseModel):
    """Schema for search requests"""
    id: int | None = None
    origin: str
    destination: str
    earliest_departure: date
    latest_return: date
    min_stay_days: int = 7
    max_stay_days: int = 14
    max_stops: int = 0
    max_duration_hours: int = 12
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "admin"


class ConnectionSchema(BaseModel):
    """Schema for specific flight connections"""
    origin: str
    destination: str
    departure_date: date
    return_date: date
    stay_duration: int
    max_stops: int = 0
    max_duration_hours: int = 12


class FlightSchema(BaseModel):
    """Schema for specific flight data extracted from the web scraper"""
    origin: str
    destination: str
    airline: str
    departure_date: date
    flight_time: str
    return_date: date
    price: int
    duration: str
    stops: int
    scraped_at: datetime = Field(default_factory=datetime.now)
