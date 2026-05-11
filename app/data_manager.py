import pandas as pd
import ast
from sqlalchemy import create_engine
from db import DATABASE

class DataManager:
    def __init__(self):
        self.engine = create_engine(f'sqlite:///{DATABASE}')
        self._df = None
        self.refresh_data()

    def refresh_data(self):
        """Load and pre-process everything once."""
        query = """
            SELECT * FROM searches
            INNER JOIN price_list ON searches.id = price_list.search_id
            INNER JOIN flights ON price_list.id = flights.price_list_id
        """
        df = pd.read_sql(query, con=self.engine)
        df = df.loc[:, ~df.columns.duplicated()].copy()

        df['return_date'] = pd.to_datetime(df['return_date'])
        df['scraped_at'] = pd.to_datetime(df['scraped_at'])
        df['departure_date'] = pd.to_datetime(df['departure_date'])
        df['scraped_date'] = df['scraped_at'].dt.date
        df['scraped_date_str'] = df['scraped_date'].astype(str)

        today = pd.Timestamp.today().normalize()
        df['archived'] = df.groupby('search_id')['return_date'].transform('max') < today

        df['price_list'] = df['price_list'].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) else x
        )
        
        self._df = df

    def get_data(self, include_archived=False):
        if self._df is None:
            self.refresh_data()
        assert self._df is not None, "DataFrame was not initialized"
        return self._df if include_archived else self._df[~self._df['archived']]

data_manager = DataManager()