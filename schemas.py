from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator, model_validator


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

    max_stops: int | None = None
    max_duration_hours: int | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "admin"

    connections: list["ConnectionSchema"] = []

    @field_validator('earliest_departure', 'latest_departure', 'earliest_return', 'latest_return', mode='before')
    @classmethod
    def parse_google_dates(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, (date, datetime)):
            return v
        if isinstance(v, str):
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
        return v

    @field_validator('created_at', mode='before')
    @classmethod
    def parse_google_timestamp(cls, v):
        if v is None or v == "":
            return datetime.now()
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.strptime(v, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                try:
                    return datetime.strptime(v, "%d/%m/%Y %H:%M")
                except ValueError:
                    return v
        return v
    
    @field_validator('max_stops', 'max_duration_hours', mode='before')
    @classmethod
    def empty_string_to_default(cls, v, info):
        if v == "":
            return cls.model_fields[info.field_name].default
        return v
    
    @model_validator(mode='after')
    def check_dates(self) -> 'SearchSchema':
        # Check if latest departure not in past
        today = date.today()
        if self.latest_departure and self.latest_departure < today:
            raise ValueError(f"Latest departure ({self.latest_departure}) cannot be in the past.")
        
        # Departure (earliest vs latest)
        if self.earliest_departure > self.latest_departure:
            raise ValueError(f"Earliest departure ({self.earliest_departure}) cannot be after latest departure ({self.latest_departure})")

        # Return (earliest vs latest)
        if self.earliest_return and self.latest_return:
            if self.earliest_return > self.latest_return:
                raise ValueError(f"Earliest return ({self.earliest_return}) cannot be after latest return ({self.latest_return})")

        return self

    @model_validator(mode='after')
    def check_return_fields(self) -> 'SearchSchema':
        if self.earliest_return and self.latest_return:
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

    max_stops: int | None = None
    max_duration_hours: int | None = None

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
