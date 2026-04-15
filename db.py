from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class SearchDB(Base):
    __tablename__ = 'searches'

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(100), nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)

    earliest_departure: Mapped[str] = mapped_column(String(10), nullable=False)
    latest_return: Mapped[str] = mapped_column(String(10), nullable=False)

    min_stay_days: Mapped[int] = mapped_column(Integer, default=7)
    max_stay_days: Mapped[int] = mapped_column(Integer, default=14)
    max_stops: Mapped[int] = mapped_column(Integer, default=0)
    max_duration_hours: Mapped[int] = mapped_column(Integer, default=12)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    created_by: Mapped[str] = mapped_column(String(100), default="admin")

    # Link to the flights and price list
    prices: Mapped[List["FlightDB"]] = relationship(
        "FlightDB", back_populates="search", cascade="all, delete-orphan"
        )
    price_list: Mapped[List["PriceListDB"]] = relationship(
        "PriceListDB", back_populates="search", cascade="all, delete-orphan"
        )

    __table_args__ = (
        UniqueConstraint(
            'origin',
            'destination',
            'earliest_departure',
            'latest_return',
            'min_stay_days',
            'max_stay_days',
            'max_stops',
            'max_duration_hours',
            name='_search_params_uc'
        ),
    )


class PriceListDB(Base):
    """
    Stores the price list of the 12-month calendar for a specific connection.
    """
    __tablename__ = 'price_list'

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey('searches.id'))

    price_list: Mapped[List[int]] = mapped_column(JSON, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationship back to the parent search
    search: Mapped["SearchDB"] = relationship("SearchDB", back_populates="price_list")


class FlightDB(Base):
    __tablename__ = 'flights'

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey('searches.id'))
    price_list_id: Mapped[int] = mapped_column(ForeignKey('price_list.id'))

    # Specifics of the actual flight found
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_date: Mapped[str] = mapped_column(String(10), nullable=False)
    return_date: Mapped[Optional[str]] = mapped_column(String(10))
    flight_time: Mapped[str] = mapped_column(String(30))
    airline: Mapped[Optional[str]] = mapped_column(String(512))
    stops: Mapped[Optional[int]] = mapped_column(Integer)
    duration: Mapped[Optional[str]] = mapped_column(String)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationship back to the parent search
    search: Mapped["SearchDB"] = relationship("SearchDB", back_populates="prices")


# --- Database Setup ---
DATABASE = "flight_database.db"
engine = create_engine(f'sqlite:///{DATABASE}', echo=False)

# This creates the tables if they don't exist
Base.metadata.create_all(engine)

# Session factory for use in your scraper
Session = sessionmaker(bind=engine)
