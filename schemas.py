from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator


class SearchSchema(BaseModel):
    """Schema for search requests"""
    id: int | None = None

    one_way: bool = True

    origin: str
    destination: str

    earliest_departure: date
    latest_departure: date

    earliest_return: date | None = None
    latest_return: date | None = None
    min_stay_days: int | None = None
    max_stay_days: int | None = None

    max_stops: int = 0
    max_duration_hours: int = 12

    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "admin"

    connections: list["ConnectionSchema"] = []

    @model_validator(mode='after')
    def check_return_fields(self) -> 'SearchSchema':
        if self.earliest_return is not None and self.latest_return is not None:
            self.one_way = False
        if not self.one_way:
            required_fields = [
                'earliest_return',
                'latest_return'
            ]

            missing = [f for f in required_fields if getattr(self, f) is None]

            if missing:
                raise ValueError(
                    f"Round-trip searches (one_way=False) require these fields: {', '.join(missing)}"
                )

        return self


class ConnectionSchema(BaseModel):
    """Schema for specific flight connections"""
    id: int | None = None
    search_id: int | None = None

    one_way: bool = True

    origin: str
    destination: str

    departure_date: date

    return_date: date | None = None
    stay_duration: int | None = None

    max_stops: int = 0
    max_duration_hours: int = 12

    price_list: list[int] | None = None

    flights: list["FlightSchema"] = []


class FlightSchema(BaseModel):
    """Schema for specific flight data extracted from the web scraper"""
    origin: str
    destination: str

    departure_date: date

    return_date: date | None = None

    price: int
    airline: str
    flight_time: str
    duration: str
    stops: int

    scraped_at: datetime = Field(default_factory=datetime.now)
