import numpy as np
import pandas as pd
import ast
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from sqlalchemy import create_engine


# --- Configuration ---
DATABASE = "flight_database.db"
PORT = 8000
QUANTILES = [0., 0.01, 0.1, 0.25, 0.75, 0.9, 0.99, 1.]
QUANTILE_COLORS = [
    'rgba(215, 48, 39, 0.7)',       # Deep Red
    'rgba(244, 109, 67, 0.7)',      # Light Red
    'rgba(253, 174, 97, 0.7)',      # Orange-ish
    'rgba(200, 200, 200, 0.7)',     # Grey
    'rgba(102, 189, 99, 0.7)',      # Light Green
    'rgba(26, 152, 80, 0.7)',       # Medium Green
    'rgba(0, 100, 0, 0.7)',         # Deep Green
]

engine = create_engine(f'sqlite:///{DATABASE}', echo=False)


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     loop = asyncio.get_event_loop()
#     loop.call_later(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}"))
#     yield

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_processed_data(include_archived=False):
    query = """
        SELECT * FROM searches
        INNER JOIN price_list ON searches.id = price_list.search_id
        INNER JOIN flights ON price_list.id = flights.price_list_id
    """
    df = pd.read_sql(query, con=engine)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    df['return_date'] = pd.to_datetime(df['return_date']).dt.date
    today = pd.Timestamp.today().date()
    df['archived'] = df.groupby('search_id')['return_date'].transform('max') < today

    return df if include_archived else df[~df['archived']]


@app.get("/")
async def index(): return FileResponse("app/index.html")


@app.get("/routes")
def get_routes(archived: bool = False):
    df = get_processed_data(archived)
    routes = df[['origin', 'destination']].drop_duplicates()
    return [
        {
            "label": f"{r.origin} to {r.destination}",
            "value": f"{r.origin}|{r.destination}"
        } for r in routes.itertuples()
            ]


@app.get("/dates")
def get_dates(route: str, archived: bool = False):
    origin, dest = route.split('|')
    df = get_processed_data(archived)
    relevant = df[(df['origin'] == origin) & (df['destination'] == dest)]
    return sorted(pd.to_datetime(relevant['scraped_at']).dt.date.unique().astype(str), reverse=True)


@app.get("/line-chart")
def get_line_chart(route: str, archived: bool = False):
    origin, dest = route.split('|')
    df = get_processed_data(archived)
    df_temp = df[(df['origin'] == origin) & (df['destination'] == dest)].copy()
    df_temp['scraped_at'] = pd.to_datetime(df_temp['scraped_at']).dt.date
    df_grouped = df_temp.groupby('scraped_at')['price']

    # Displayed x range
    x_window_min = df_temp['scraped_at'].min() - pd.Timedelta(days=1)
    x_window_max = df_temp['scraped_at'].max() + pd.Timedelta(days=1)

    # Quantile/Range Logic
    df_temp['price_list'] = df_temp['price_list'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df_exp = df_temp.explode('price_list')
    df_exp['price_list'] = pd.to_numeric(df_exp['price_list'])
    df_q = df_exp.groupby('scraped_at')['price_list'].quantile(np.array(QUANTILES)).unstack().round()

    # Displayed y range
    y_window_min = df_q[0.01].min() * 0.9
    y_window_max = df_q[0.99].max() * 1.1

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

    # Base metrics
    res = {
        "x": sorted(df_temp['scraped_at'].unique().astype(str).tolist()),
        "min": df_grouped.min().tolist(),
        "mean": df_grouped.mean().tolist(),
        "x_q": sorted(df_q_extended.index.astype(str).tolist()),
        "quantiles": {},
        "y_window": [y_window_min, y_window_max],
        "x_window": [x_window_min, x_window_max]
    }

    for q in QUANTILES:
        res["quantiles"][str(q)] = df_q_extended[q].tolist()

    return res


@app.get("/heatmap")
def get_heatmap(route: str, date: str, archived: bool = False):
    origin, dest = route.split('|')
    df = get_processed_data(archived)
    mask = (
        (df['origin'] == origin)
        & (df['destination'] == dest)
        & (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == date)
        )
    f_df = df[mask].copy()
    if f_df.empty:
        return {}

    f_df['departure_date'] = pd.to_datetime(f_df['departure_date']).dt.date
    f_df['return_date'] = pd.to_datetime(f_df['return_date']).dt.date

    is_one_way = f_df['return_date'].isna().all()

    # Calculate Levels based on price_list for coloring
    f_df['price_list'] = f_df['price_list'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    prices_all = pd.to_numeric(f_df.explode('price_list')['price_list'])
    q_list = QUANTILES[1:]
    levels = np.array(prices_all.quantile(q_list).round().values)

    if is_one_way:
        z_df = f_df.pivot_table(index='destination', columns='departure_date', values='price', aggfunc='min')
        airline_df = f_df.sort_values('price').pivot_table(
            index='destination', columns='departure_date', values='airline', aggfunc='first'
            )
        stay_df = z_df.copy().fillna(0)
    else:
        f_df['days_stayed'] = (pd.to_datetime(f_df['return_date']) - pd.to_datetime(f_df['departure_date'])).dt.days + 1
        z_df = f_df.pivot_table(index='departure_date', columns='return_date', values='price', aggfunc='min')
        airline_df = f_df.sort_values('price').pivot_table(
            index='departure_date', columns='return_date', values='airline', aggfunc='first'
            )
        stay_df = f_df.pivot_table(
            index='departure_date', columns='return_date', values='days_stayed', aggfunc='first'
            )

    all_x = pd.date_range(start=min(z_df.columns), end=max(z_df.columns)).date
    z_df = z_df.reindex(columns=all_x)

    z_values = z_df.values
    z_indexed = np.digitize(z_values, levels)
    z_indexed = np.where(np.isnan(z_values), np.nan, z_indexed)

    mask = np.isnan(z_indexed)

    z_values = z_values.astype(object)
    z_indexed = z_indexed.astype(object)
    airline_df = airline_df.reindex(columns=all_x).values.astype(object)
    stay_df = stay_df.reindex(columns=all_x).values.astype(object)

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


@app.get("/table")
def get_table(route: str, scrape_date: str, dep_date: str, ret_date: str | None = None, archived: bool = False):
    origin, dest = route.split('|')
    df = get_processed_data(archived)
    df['days_stayed'] = (pd.to_datetime(df['return_date']) - pd.to_datetime(df['departure_date'])).dt.days + 1
    df['days_stayed'] = df['days_stayed'].fillna(0)

    df = df[[
        'origin', 'destination', 'departure_date', 'return_date',
        'price', 'airline', 'stops', 'flight_time', 'duration', 'scraped_at', 'days_stayed'
        ]]
    mask = (df['origin'] == origin) & (df['destination'] == dest) & \
           (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == scrape_date) & \
           (pd.to_datetime(df['departure_date']).dt.date.astype(str) == dep_date)

    if ret_date and ret_date != 'null':
        mask &= (pd.to_datetime(df['return_date']).dt.date.astype(str) == ret_date)
    else:
        mask &= df['return_date'].isna()

    table_df = df[mask].sort_values('price')

    return jsonable_encoder(table_df.to_dict(orient="records"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
