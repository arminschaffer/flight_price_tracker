import numpy as np
import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
import ast
from sqlalchemy import create_engine

# Database Setup
DATABASE = "flight_database.db"
engine = create_engine(f'sqlite:///{DATABASE}', echo=False)


def mark_archived(df):
    today = pd.Timestamp.today().date()

    # ensure datetime
    df['return_date'] = pd.to_datetime(df['return_date']).dt.date

    # find max return date per search
    max_return_per_search = df.groupby('search_id')['return_date'].transform('max')

    # archived flag
    df['archived'] = max_return_per_search < today

    return df


def get_data(include_archived=True):
    # Fetch data from SQL
    query = (
        'SELECT * '
        'FROM searches '
        'INNER JOIN '
        'price_range_snapshots '
        'ON '
        'searches.id = price_range_snapshots.search_id '
        'INNER JOIN '
        'flights '
        'ON '
        'searches.id = flights.search_id'
        )

    df = pd.read_sql(query, con=engine)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    df = mark_archived(df)

    if not include_archived:
        df = df[~df['archived']]

    return df


# App Setup
app = dash.Dash(__name__)

app.layout = html.Div(style={'fontFamily': 'Arial', 'padding': '20px', 'margin': '0 auto'}, children=[
    html.H2("Flight Tracker:"),

    # --- ROW 1: Archive Toggle Button ---
    html.Div([
        dcc.Checklist(
            id='archive-toggle',
            options=[{'label': ' Show Archived Flights', 'value': 'show'}],
            value=[],  # default = hide archived
            labelStyle={'display': 'inline-block', 'marginRight': '20px', 'cursor': 'pointer'}
        )
    ], style={'marginBottom': '20px'}),

    # --- ROW 2: Route Dropdown (Full Width or Centered) ---
    html.Div([
        html.Label("Route:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(id='route-drop')
    ], style={'width': '100%', 'marginBottom': '20px'}),

    # --- ROW 3: Checklist + Date Dropdown (Side-by-Side) ---
    html.Div([
        # Left Side: Checklist
        html.Div([
            html.Label("Toggle Price Metrics:", style={'fontWeight': 'bold'}),
            dcc.Checklist(
                id='price-mode',
                options=[
                    {'label': ' Min Price', 'value': 'min'},
                    {'label': ' Average Price', 'value': 'mean'},
                    {'label': ' Price Range', 'value': 'price_range'}
                ],
                value=['min'],
                labelStyle={'display': 'inline-block', 'marginRight': '20px', 'cursor': 'pointer'}
            ),
        ], style={'width': '49%'}),

        # Right Side: Scrape Date
        html.Div([
            html.Label("Look-up Date:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(id='date-drop'),
        ], style={'width': '49%'})
    ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-end', 'marginBottom': '30px'}),

    # --- ROW 4: Graphs (Side-by-Side) ---
    html.Div([
        html.Div([
            dcc.Graph(id='lowest-price-line', style={'height': '400px'})
        ], style={'width': '49%'}),

        html.Div([
            dcc.Graph(id='price-heatmap', style={'height': '400px'})
        ], style={'width': '49%'})
    ], style={'display': 'flex', 'justifyContent': 'space-between'}),

    dcc.Interval(id='interval-component', interval=30*60*1000, n_intervals=0),

    # --- ROW 5: Drop downs for departure and return ---
    html.Div([
        # Left Side: Checklist
        html.Div([
            html.Label("Departure date:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(id='departure-drop')
        ], style={'width': '49%'}),

        # Right Side: Scrape Date
        html.Div([
            html.Label("Return date:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(id='return-drop')
        ], style={'width': '49%'})
    ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-end', 'marginBottom': '0px'}),

    # --- ROW 6: Table of all flights fitting connection ---
    html.Div([
        html.H3("Available Offers"),
        dcc.Graph(id='flights-table')
    ], style={'padding': '20px 0'})
])


# Callback to update line plot (id='lowest-price-line')
@app.callback(
    Output('lowest-price-line', 'figure'),
    Input('route-drop', 'value'),
    Input('price-mode', 'value'),
    Input('archive-toggle', 'value'),
    Input('interval-component', 'n_intervals')
)
def update_scatter(selected_route, selected_metrics, archived_flag, n):
    if not selected_route:
        return go.Figure()

    origin, dest = selected_route.split('|')
    df = get_data(archived_flag)

    mask = (df['origin'] == origin) & (df['destination'] == dest)
    df_temp = df[mask].copy()
    df_temp['scraped_at'] = pd.to_datetime(df_temp['scraped_at']).dt.date

    fig = go.Figure()

    if 'min' in selected_metrics:
        df_min = df_temp.groupby('scraped_at')['price'].min()
        fig.add_trace(go.Scatter(
            x=df_min.index,
            y=df_min.values,
            name='Min Price',
            line=dict(color='#2ca02c', width=3),
            mode='lines+markers'
        ))

    if 'mean' in selected_metrics:
        df_mean = df_temp.groupby('scraped_at')['price'].mean()
        fig.add_trace(go.Scatter(
            x=df_mean.index,
            y=df_mean.values,
            name='Avg Price',
            line=dict(color='#1f77b4', width=3, dash='dash'),
            mode='lines+markers'
        ))

    if 'price_range' in selected_metrics:
        df_temp['price_list'] = df_temp['price_list'].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
        df_exp = df_temp.explode('price_list')
        df_exp['price_list'] = pd.to_numeric(df_exp['price_list'])
        df_range = df_exp.groupby('scraped_at')['price_list']
        print(df_range.min())
        df_range_min = df_range.min()
        df_range_max = df_range.max()

        fig.add_trace(go.Scatter(
            x=df_range_max.index,
            y=df_range_max.values,
            name='Max Price',
            mode='lines+markers',
            line=dict(color="#6B7D8A", width=3, dash='dash'),
            ))
        fig.add_trace(go.Scatter(
            x=df_range_min.index,
            y=df_range_min.values,
            name='Min Price',
            mode='lines+markers',
            line=dict(color="#6B7D8A", width=3, dash='dash'),
            fill='tonexty'
        ))

    fig.update_layout(
        xaxis_title="Look-up Date",
        yaxis_title="Price",
        plot_bgcolor='#f9f9f9',
        hovermode="x unified",
        xaxis={'tickformat': '%d %b', 'showgrid': False, 'tickangle': -45},
        yaxis={'tickprefix': '€', 'showgrid': True, 'gridcolor': 'white'},
        margin=dict(t=30, b=30, l=30, r=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return fig


# Callback to update Route Dropdown options periodically
@app.callback(
    Output('route-drop', 'options'),
    Input('archive-toggle', 'value'),
    Input('interval-component', 'n_intervals')
)
def update_route_options(archived_flag, n):
    df = get_data(archived_flag)
    # Create new options list from the latest database state
    options = [
        {'label': f"{r.origin} to {r.destination}", 'value': f"{r.origin}|{r.destination}"}
        for r in df[['origin', 'destination']].drop_duplicates().itertuples()
    ]
    return options


# Callback to update Date Dropdown based on Route
@app.callback(
    Output('date-drop', 'options'),
    Output('date-drop', 'value'),
    Input('route-drop', 'value'),
    Input('archive-toggle', 'value')
)
def update_date_options(selected_route, archived_flag):
    if not selected_route:
        return [], None

    origin, dest = selected_route.split('|')
    # Use the live data to find available dates for THIS specific route
    df = get_data(archived_flag)
    relevant_dates = sorted(
        pd.to_datetime(
            df[(df['origin'] == origin) & (df['destination'] == dest)]['scraped_at']
            ).dt.date.unique(), reverse=True
            )

    options = [
        {'label': d.strftime('%d %b %Y') + ' (latest)', 'value': str(d)} if d == relevant_dates[0]
        else {'label': d.strftime('%d %b %Y'), 'value': str(d)}
        for d in relevant_dates
        ]
    return options, options[0]['value'] if options else None


# Callback to update Heatmap (id='price-heatmap')
@app.callback(
    Output('price-heatmap', 'figure'),
    Input('route-drop', 'value'),
    Input('date-drop', 'value'),
    Input('archive-toggle', 'value'),
    Input('interval-component', 'n_intervals')
)
def update_heatmap(selected_route, selected_date, archived_flag, n):
    if not selected_date:
        return go.Figure()

    origin, dest = selected_route.split('|')
    df = get_data(archived_flag)

    mask = (df['origin'] == origin) & \
           (df['destination'] == dest) & \
           (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == selected_date)

    # Filter the data
    filtered_df = df[mask].copy()
    filtered_df['departure_date'] = pd.to_datetime(filtered_df['departure_date'])
    filtered_df['return_date'] = pd.to_datetime(filtered_df['return_date'])

    # create df for stay length
    filtered_df['days_stayed'] = (filtered_df['return_date'] - filtered_df['departure_date']).dt.days
    stay_df = filtered_df.pivot_table(
        index='departure_date',
        columns='return_date',
        values='days_stayed',
        aggfunc='first'
        )

    # create an airline df
    airline_df = filtered_df.sort_values('price').pivot_table(
        index='departure_date',
        columns='return_date',
        values='airline',
        aggfunc='first'
        )

    # Convert columns to date-only
    filtered_df['departure_date'] = pd.to_datetime(filtered_df['departure_date']).dt.date
    filtered_df['return_date'] = pd.to_datetime(filtered_df['return_date']).dt.date

    # Pivot
    z_df = filtered_df.pivot_table(
        index='departure_date',
        columns='return_date',
        values='price',
        aggfunc='min'
        )

    # add all dates within the range
    if not z_df.empty:
        # Create ranges using .date() to match the index type
        all_departure_dates = pd.date_range(start=z_df.index.min(), end=z_df.index.max()).date
        all_return_dates = pd.date_range(start=z_df.columns.min(), end=z_df.columns.max()).date

        # Reindex (now the types match perfectly)
        z_df = z_df.reindex(index=all_departure_dates, columns=all_return_dates)
        stay_df = stay_df.reindex(index=all_departure_dates, columns=all_return_dates)
        airline_df = airline_df.reindex(index=all_departure_dates, columns=all_return_dates)

    # create custom data for hover over info
    custom_info = np.stack((stay_df.values, airline_df.values), axis=-1)

    fig = go.Figure(data=go.Heatmap(
        z=z_df.values, x=z_df.columns, y=z_df.index,
        customdata=custom_info,
        colorscale='RdYlGn_r',
        text=z_df.map(lambda x: f'€{x:.0f}' if pd.notnull(x) else "-").values,
        texttemplate="%{text}",
        showscale=False,
        hovertemplate=(
            "<b>Departure:</b> %{y|%d %b %Y}<br>" +
            "<b>Return:</b> %{x|%d %b %Y}<br>" +
            "<b>Stay:</b> %{customdata[0]} days<br>" +
            "<b>Lowest Price:</b> €%{z:.0f}<br>" +
            "<b>Airline:</b> %{customdata[1]}<br>" +
            "<extra></extra>"
            ),
        xgap=5, ygap=5
    ))

    fig.update_layout(
        xaxis_title="Return Date",
        yaxis_title="Departure Date",
        plot_bgcolor='#f2f2f2',
        xaxis={'tickformat': '%d %b', 'dtick': 'D1', 'showgrid': False, 'tickangle': -45},
        yaxis={'tickformat': '%d %b', 'dtick': 'D1', 'showgrid': False},
        margin=dict(t=30, b=30, l=30, r=30)
    )
    return fig


# Callback to update Departure Dropdown options
@app.callback(
    Output('departure-drop', 'options'),
    Output('departure-drop', 'value'),
    Input('route-drop', 'value'),
    Input('date-drop', 'value'),
    Input('archive-toggle', 'value')
)
def update_departure_options(selected_route, scrape_date, archived_flag):
    if not selected_route:
        return [], None

    origin, dest = selected_route.split('|')
    scrape_date = scrape_date
    # Use the live data to find available dates for THIS specific route
    df = get_data(archived_flag)

    mask = (
        (df['origin'] == origin) &
        (df['destination'] == dest) &
        (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == scrape_date)
    )

    relevant_flights = sorted(
        pd.to_datetime(
            df[mask]['departure_date']).dt.date.unique(), reverse=True)

    options = [
        {'label': d.strftime('%d %b %Y'), 'value': str(d)} for d in relevant_flights
        ]
    return options, options[0]['value'] if options else None


# Callback to update Return Dropdown options
@app.callback(
    Output('return-drop', 'options'),
    Output('return-drop', 'value'),
    Input('route-drop', 'value'),
    Input('date-drop', 'value'),
    Input('archive-toggle', 'value')
)
def update_return_options(selected_route, scrape_date, archived_flag):
    if not selected_route:
        return [], None

    origin, dest = selected_route.split('|')
    scrape_date = scrape_date
    # Use the live data to find available dates for THIS specific route
    df = get_data(archived_flag)
    relevant_flights = sorted(
        pd.to_datetime(
            df[
                (df['origin'] == origin) &
                (df['destination'] == dest) &
                (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == scrape_date)
            ]['return_date']).dt.date.unique(), reverse=True)

    options = [
        {'label': d.strftime('%d %b %Y'), 'value': str(d)} for d in relevant_flights
        ]
    return options, options[0]['value'] if options else None


# Callback to update the Table (id='flights-table')
@app.callback(
    Output('flights-table', 'figure'),
    Input('route-drop', 'value'),
    Input('date-drop', 'value'),
    Input('departure-drop', 'value'),
    Input('return-drop', 'value'),
    Input('archive-toggle', 'value'),
    Input('interval-component', 'n_intervals')
)
def update_table(selected_route, scrape_date, dep_date, ret_date, archived_flag, n):
    if not all([selected_route, scrape_date, dep_date, ret_date]):
        return go.Figure()

    origin, dest = selected_route.split('|')
    df = get_data(archived_flag)

    # Filter data based on all selections
    mask = (
        (df['origin'] == origin) &
        (df['destination'] == dest) &
        (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == scrape_date) &
        (pd.to_datetime(df['departure_date']).dt.date.astype(str) == dep_date) &
        (pd.to_datetime(df['return_date']).dt.date.astype(str) == ret_date)
    )

    table_df = df[mask].copy()
    table_df['scraped_at'] = pd.to_datetime(table_df['scraped_at']).dt.strftime('%Y-%m-%d %H:%M:%S')

    # Sort by price ascending
    table_df = table_df.sort_values(by='price', ascending=True)

    # Create the Plotly Table
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=[
                '<b>Airline</b>',
                '<b>Departure</b>',
                '<b>Departing Flight Time</b>',
                '<b>Return</b>',
                '<b>Stops</b>',
                '<b>Duration</b>',
                '<b>Price</b>',
                '<b>Scraped at</b>'
                ],
            align='left',
            font=dict(size=12)
        ),
        cells=dict(
            values=[
                table_df.airline,
                table_df.departure_date,
                table_df.flight_time,
                table_df.return_date,
                table_df.stops,
                table_df.duration,
                table_df.price.map('€{:,.2f}'.format),
                table_df.scraped_at
            ],
            fill_color='lavender',
            align='left',
            font=dict(size=11)
        ))
    ])

    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        height=400
    )

    return fig


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)
