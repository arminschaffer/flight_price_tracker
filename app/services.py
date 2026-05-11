import numpy as np
import pandas as pd
from app.data_manager import data_manager
from fastapi.encoders import jsonable_encoder

QUANTILES = [0., 0.01, 0.1, 0.25, 0.75, 0.9, 0.99, 1.]
QUANTILE_COLORS = [
    # 'rgba(215, 48, 39, 0.7)', 'rgba(244, 109, 67, 0.7)', 
    # 'rgba(253, 174, 97, 0.7)', 'rgba(200, 200, 200, 0.7)', 
    # 'rgba(102, 189, 99, 0.7)', 'rgba(26, 152, 80, 0.7)', 'rgba(0, 100, 0, 0.7)'
    'rgba(239, 68, 68, 0.40)',
    'rgba(249, 115, 22, 0.40)',
    'rgba(245, 158, 11, 0.40)',
    'rgba(148, 163, 184, 0.32)',
    'rgba(167, 243, 208, 0.50)',
    'rgba(52, 211, 153, 0.45)',
    'rgba(6, 78, 59, 0.55)'
]

class FlightService:
    @staticmethod
    def get_routes(archived: bool):
        df = data_manager.get_data(archived)
        routes = df[['origin', 'destination', 'created_by']].drop_duplicates()
        return [{"label": f"{r.origin} to {r.destination} ({r.created_by})", 
                 "value": f"{r.origin}|{r.destination}|{r.created_by}"} for r in routes.itertuples()]

    @staticmethod
    def get_dates(route_str: str, archived: bool):
        origin, dest, user = route_str.split('|')
        df = data_manager.get_data(archived)
        relevant = df[(df['origin'] == origin) & (df['destination'] == dest) & (df['created_by'] == user)]
        return sorted(relevant['scraped_date_str'].unique().tolist(), reverse=True)

    @staticmethod
    def get_line_chart(route_str: str, archived: bool):
        origin, dest, user = route_str.split('|')
        df = data_manager.get_data(archived)
        df_temp = df[(df['origin'] == origin) & (df['destination'] == dest) & (df['created_by'] == user)].copy()
        
        is_one_way = df_temp['return_date'].isna().all()

        # Min/Mean stats
        df_grouped = df_temp.groupby('scraped_date')['price']
        
        # Grid for connections
        group_keys = ['scraped_date', 'departure_date'] if is_one_way else ['scraped_date', 'departure_date', 'return_date']
        df_grouped_con = df_temp.groupby(group_keys)['price'].min().unstack(level='scraped_date').values
        
        mask = np.isnan(df_grouped_con)
        df_grouped_con = df_grouped_con.astype(object)
        df_grouped_con[mask] = None

        # Quantiles
        df_exp = df_temp.explode('price_list')
        df_exp['price_list'] = pd.to_numeric(df_exp['price_list'])
        df_q = df_exp.groupby('scraped_date')['price_list'].quantile(np.array(QUANTILES)).unstack().round().interpolate().round()

        # Expand upper and lower price limits
        df_q[1.] = 5000
        df_q[0.] = 0

        # Expand dates
        first_date = df_q.index.min()
        last_date = df_q.index.max()
        df_q_extended = df_q.copy()
        before_row = df_q_extended.loc[[first_date]].rename(index={first_date: first_date - pd.Timedelta(days=1)})
        after_row = df_q_extended.loc[[last_date]].rename(index={last_date: last_date + pd.Timedelta(days=1)})
        df_q_extended = pd.concat([before_row, df_q_extended, after_row]).sort_index()

        return {
            "x": sorted(df_temp['scraped_date'].unique().astype(str).tolist()),
            "min": df_grouped.min().tolist(),
            "mean": df_grouped.mean().round().tolist(),
            "min_con": df_grouped_con.tolist(),
            "x_q": df_q_extended.index.astype(str).tolist(),
            "quantiles": {str(q): df_q_extended[q].tolist() for q in QUANTILES},
            "y_window": [df_q[0.01].min() * 0.8, df_q[0.99].max() * 1.1],
            "x_window": [str(df_q_extended.index.min()), str(df_q_extended.index.max())]
        }

    @staticmethod
    def get_heatmap(route_str: str, date_str: str, archived: bool):
        origin, dest, user = route_str.split('|')
        df = data_manager.get_data(archived)
        
        f_df = df[
            (df['origin'] == origin) & (df['destination'] == dest) & 
            (df['scraped_date_str'] == date_str) & (df['created_by'] == user)
        ].copy()
        
        if f_df.empty: return {}

        is_one_way = f_df['return_date'].isna().all()
        prices_all = pd.to_numeric(f_df.explode('price_list')['price_list'])
        levels = np.array(prices_all.quantile(QUANTILES[1:]).round().values)

        if is_one_way:
            z_df = f_df.pivot_table(index='destination', columns='departure_date', values='price', aggfunc='min')
            airline_df = f_df.sort_values('price').pivot_table(index='destination', columns='departure_date', values='airline', aggfunc='first')
            stay_df = z_df.copy().fillna(0)
            all_y = airline_df.index
        else:
            f_df['days_stayed'] = (pd.to_datetime(f_df['return_date']) - pd.to_datetime(f_df['departure_date'])).dt.days + 1
            z_df = f_df.pivot_table(index='departure_date', columns='return_date', values='price', aggfunc='min')
            airline_df = f_df.sort_values('price').pivot_table(index='departure_date', columns='return_date', values='airline', aggfunc='first')
            stay_df = f_df.pivot_table(index='departure_date', columns='return_date', values='days_stayed', aggfunc='first')
            all_y = pd.date_range(start=min(z_df.index), end=max(z_df.index)).date

        all_x = pd.date_range(start=min(z_df.columns), end=max(z_df.columns)).date
        z_df = z_df.reindex(index=all_y, columns=all_x)

        z_values = z_df.values
        z_indexed = np.digitize(z_values, levels)
        z_indexed = np.where(np.isnan(z_values), np.nan, z_indexed)
        
        mask = np.isnan(z_indexed)

        z_values = z_values.astype(object)
        z_indexed = z_indexed.astype(object)
        airline_df = airline_df.reindex(index=all_y, columns=all_x).values.astype(object)
        stay_df = stay_df.reindex(index=all_y, columns=all_x).values.astype(object)

        z_indexed[mask] = None
        z_values[mask] = None
        airline_df[mask] = None
        stay_df[mask] = None

        return jsonable_encoder({
            "z": z_indexed.tolist(),
            "x": [str(d) for d in z_df.columns],
            "y": [str(d) for d in z_df.index],
            "original_z": z_values.tolist(),
            "is_one_way": bool(is_one_way),
            "colors": QUANTILE_COLORS[::-1],
            "airline": airline_df.tolist(),
            "days_stayed": stay_df.tolist()
        })
    
    @staticmethod
    def get_table(route: str, scrape_date: str, dep_date: str, ret_date: str | None, archived: bool):
        origin, dest, user = route.split('|')
        df = data_manager.get_data(archived).copy()
        
        df['days_stayed'] = (pd.to_datetime(df['return_date']) - pd.to_datetime(df['departure_date'])).dt.days + 1
        df['days_stayed'] = df['days_stayed'].fillna(0)

        df = df[[
            'origin', 'destination', 'departure_date', 'return_date',
            'price', 'airline', 'stops', 'flight_time', 'duration', 'scraped_date_str', 'days_stayed', 'created_by'
            ]]

        mask = (
            (df['origin'] == origin) & (df['destination'] == dest) & 
            (df['scraped_date_str'] == scrape_date) & (df['created_by'] == user) &
            (df['departure_date'].astype(str) == dep_date)
        )

        if ret_date and ret_date != 'null':
            mask &= (df['return_date'].astype(str) == ret_date)
        else:
            mask &= df['return_date'].isna()

        table_df = df[mask].sort_values('price')

        return jsonable_encoder(table_df.to_dict(orient="records"))