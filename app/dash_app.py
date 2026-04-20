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


QUANTILES = [0., 0.01, 0.1, 0.25, 0.75, 0.9, 0.99, 1.]
QUANTILE_COLORS = [
    (1.00, 0.99, 'rgba(215, 48, 39, 0.7)'),     # Deep Red
    (0.99, 0.90, 'rgba(244, 109, 67, 0.7)'),    # Light Red
    (0.90, 0.75, 'rgba(253, 174, 97, 0.7)'),    # Orange-ish
    (0.75, 0.25, 'rgba(200, 200, 200, 0.7)'),   # Grey
    (0.25, 0.10, 'rgba(102, 189, 99, 0.7)'),    # Light Green
    (0.10, 0.01, 'rgba(26, 152, 80, 0.7)'),     # Medium Green
    (0.01, 0.00, 'rgba(0, 100, 0, 0.7)'),       # Deep Green
    ]


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
        'price_list '
        'ON '
        'searches.id = price_list.search_id '
        'INNER JOIN '
        'flights '
        'ON '
        'price_list.id = flights.price_list_id'
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
    ], style={'width': '20%', 'marginBottom': '20px'}),

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
                    {'label': ' Price Range', 'value': 'price_range'},
                    {'label': ' Average Price', 'value': 'mean'}
                ],
                value=['min', 'price_range'],
                labelStyle={'display': 'inline-block', 'marginRight': '20px', 'cursor': 'pointer'}
            ),
        ], style={'width': '10%'}),

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
    df_grouped = df_temp.groupby('scraped_at')['price']
    y_window_min = df_grouped.min().min() * 0.9
    y_window_max = df_grouped.min().min() * 1.1
    x_window_min = df_temp['scraped_at'].min() - pd.Timedelta(days=1)
    x_window_max = df_temp['scraped_at'].max() + pd.Timedelta(days=1)

    fig = go.Figure()

    if 'min' in selected_metrics:
        df_min = df_temp.groupby('scraped_at')['price'].min()
        fig.add_trace(go.Scatter(
            x=df_min.index,
            y=df_min.values,
            name='Min Price',
            line=dict(color="#495258", width=3),
            mode='lines+markers'
        ))

        y_window_min = df_grouped.min().min() * 0.9
        y_window_max = df_grouped.min().min() * 1.1

    if 'price_range' in selected_metrics:
        df_temp['price_list'] = df_temp['price_list'].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
        df_exp = df_temp.explode('price_list')
        df_exp['price_list'] = pd.to_numeric(df_exp['price_list'])
        df_range = df_exp.groupby('scraped_at')['price_list']
        df_q = df_range.quantile(QUANTILES).unstack().round()

        # extend axis for nicer plotting
        df_q_extended = df_q.copy()
        df_q_extended[1.] = 5000
        df_q_extended[0.] = 0

        first_date = df_q.index.min()
        last_date = df_q.index.max()

        before_row = df_q_extended.loc[[first_date]].rename(index={first_date: first_date - pd.Timedelta(days=1)})
        after_row = df_q_extended.loc[[last_date]].rename(index={last_date: last_date + pd.Timedelta(days=1)})
        df_q_extended = pd.concat([before_row, df_q_extended, after_row]).sort_index()

        fig.add_trace(go.Scatter(
            x=df_q_extended.index,
            y=df_q_extended[1.],
            line=dict(width=0),
            showlegend=False,
            hoverinfo='skip',
            mode='lines',
            name='99th Percentile'
        ))

        labels = ['>99%', '90-99%', '75-90%', '25-75%', '10-25%', '1-10%', '<1%']

        for i, upper, lower, color in zip(range(len(QUANTILE_COLORS)), *zip(*QUANTILE_COLORS)):
            fig.add_trace(go.Scatter(
                x=df_q_extended.index,
                y=df_q_extended[lower],
                fill='tonexty',
                fillcolor=color,
                line=dict(width=0),
                hoverinfo='skip',
                mode='lines',
                name=labels[i]
            ))

        y_window_min = df_q[0.01].min() * 0.9
        y_window_max = df_q[0.99].max() * 1.1

    if 'mean' in selected_metrics:
        df_mean = df_temp.groupby('scraped_at')['price'].mean()
        fig.add_trace(go.Scatter(
            x=df_mean.index,
            y=df_mean.values,
            name='Avg Price',
            line=dict(color="#9BACB9", width=3, dash='dash'),
            mode='lines+markers'
        ))

        y_window_min = df_grouped.min().min() * 0.9
        y_window_max = df_grouped.mean().max() * 1.1

    fig.update_layout(
        xaxis_title="Look-up Date",
        yaxis_title="Price",
        plot_bgcolor='#f9f9f9',
        hovermode="x unified",
        xaxis={'tickformat': '%d %b', 'showgrid': False, 'tickangle': -45, 'range': [x_window_min, x_window_max]},
        yaxis={'tickprefix': '€', 'showgrid': True, 'gridcolor': 'white', 'range': [y_window_min, y_window_max]},
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

    filtered_df = df[mask].copy()
    if filtered_df.empty:
        return go.Figure()

    filtered_df['departure_date'] = pd.to_datetime(filtered_df['departure_date']).dt.date
    filtered_df['return_date'] = pd.to_datetime(filtered_df['return_date']).dt.date

    is_one_way = filtered_df['return_date'].isna().all()

    # Quantile based coloring
    df_temp = filtered_df.copy()
    df_temp['price_list'] = df_temp['price_list'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df_exp = df_temp.explode('price_list')
    df_exp['price_list'] = pd.to_numeric(df_exp['price_list'])
    q_list = QUANTILES[1:]
    levels = df_exp['price_list'].quantile(q_list).values.round()

    if is_one_way:
        filtered_df['row_label'] = "One-Way Price"
        z_df = filtered_df.pivot_table(index='row_label', columns='departure_date', values='price', aggfunc='min')
        airline_df = filtered_df.sort_values('price').pivot_table(
            index='row_label', columns='departure_date', values='airline', aggfunc='first'
            )
        stay_df = z_df.copy().fillna(0)

        y_axis_title = ""
        x_axis_title = "Departure Date"
        hover_template = (
            "<b>Departure:</b> %{x|%d %b %Y}<br>" +
            "<b>Price:</b> €%{customdata[2]:.0f}<br>" +
            "<b>Airline:</b> %{customdata[1]}<br>" +
            "<extra></extra>"
        )
    else:
        filtered_df['days_stayed'] = (pd.to_datetime(filtered_df['return_date']) -
                                      pd.to_datetime(filtered_df['departure_date'])).dt.days

        z_df = filtered_df.pivot_table(
            index='departure_date', columns='return_date', values='price', aggfunc='min'
            )
        stay_df = filtered_df.pivot_table(
            index='departure_date', columns='return_date', values='days_stayed', aggfunc='first'
            )
        airline_df = filtered_df.sort_values('price').pivot_table(
            index='departure_date', columns='return_date', values='airline', aggfunc='first'
            )

        y_axis_title = "Departure Date"
        x_axis_title = "Return Date"
        hover_template = (
            "<b>Departure:</b> %{y|%d %b %Y}<br>" +
            "<b>Return:</b> %{x|%d %b %Y}<br>" +
            "<b>Stay:</b> %{customdata[0]} days<br>" +
            "<b>Price:</b> €%{customdata[2]:.0f}<br>" +
            "<b>Airline:</b> %{customdata[1]}<br>" +
            "<extra></extra>"
        )

    # Fill date gaps
    all_x_dates = pd.date_range(start=min(z_df.columns), end=max(z_df.columns)).date
    z_df = z_df.reindex(columns=all_x_dates)
    airline_df = airline_df.reindex(columns=all_x_dates)
    stay_df = stay_df.reindex(columns=all_x_dates)

    # Prepare Heatmap Data
    z_values = z_df.values
    z_indexed = np.digitize(z_values, levels)
    z_indexed = np.where(np.isnan(z_values), np.nan, z_indexed)
    custom_info = np.stack((stay_df.values, airline_df.values, z_values), axis=-1)

    # Discrete color scale
    num_colors = len(QUANTILE_COLORS)
    custom_colorscale = []

    for i, (_, _, color) in enumerate(QUANTILE_COLORS[::-1]):
        custom_colorscale.append([i / num_colors, color])
        custom_colorscale.append([(i + 1) / num_colors, color])

    fig = go.Figure(data=go.Heatmap(
        z=z_indexed,
        x=z_df.columns,
        y=z_df.index,
        customdata=custom_info,
        colorscale=custom_colorscale,
        zmin=0, zmax=len(QUANTILE_COLORS),
        text=z_df.map(lambda x: f'€{x:.0f}' if pd.notnull(x) else "-").values,
        texttemplate="%{text}",
        hovertemplate=hover_template,
        showscale=False,
        xgap=2, ygap=2
    ))

    fig.update_layout(
        xaxis_title=x_axis_title,
        yaxis_title=y_axis_title,
        plot_bgcolor="#f6f6f6",
        xaxis={'tickformat': '%d %b', 'dtick': 'D1', 'showgrid': False, 'tickangle': -45},
        yaxis={'tickformat': '%d %b', 'dtick': 'D1', 'showgrid': False, 'showticklabels': not is_one_way},
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
    if not selected_route or not scrape_date:
        return [], None

    origin, dest = selected_route.split('|')
    df = get_data(archived_flag)

    mask = (
        (df['origin'] == origin) &
        (df['destination'] == dest) &
        (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == scrape_date)
    )

    relevant_flights = df[mask]['departure_date'].dropna().unique()
    relevant_flights = sorted(pd.to_datetime(relevant_flights).date, reverse=True)

    if not relevant_flights:
        return [], None

    options = [{'label': d.strftime('%d %b %Y'), 'value': str(d)} for d in relevant_flights]
    return options, options[0]['value']


# Callback to update Return Dropdown options
@app.callback(
    Output('return-drop', 'options'),
    Output('return-drop', 'value'),
    Input('route-drop', 'value'),
    Input('date-drop', 'value'),
    Input('archive-toggle', 'value')
)
def update_return_options(selected_route, scrape_date, archived_flag):
    if not selected_route or not scrape_date:
        return [], None

    origin, dest = selected_route.split('|')
    df = get_data(archived_flag)

    mask = (
        (df['origin'] == origin) &
        (df['destination'] == dest) &
        (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == scrape_date)
    )

    returns = df[mask]['return_date'].dropna().unique()

    if len(returns) == 0:
        return [], None

    relevant_flights = sorted(pd.to_datetime(returns).date, reverse=True)
    options = [{'label': d.strftime('%d %b %Y'), 'value': str(d)} for d in relevant_flights]

    return options, options[0]['value']


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
    if not all([selected_route, scrape_date, dep_date]):
        return go.Figure()

    origin, dest = selected_route.split('|')
    df = get_data(archived_flag)

    # Filter data based on all selections
    mask = (
        (df['origin'] == origin) &
        (df['destination'] == dest) &
        (pd.to_datetime(df['scraped_at']).dt.date.astype(str) == scrape_date) &
        (pd.to_datetime(df['departure_date']).dt.date.astype(str) == dep_date)
    )

    is_one_way = not ret_date
    print(is_one_way)

    if is_one_way:
        mask &= df['return_date'].isna()
    else:
        mask &= (pd.to_datetime(df['return_date']).dt.date.astype(str) == ret_date)

    table_df = df[mask].copy()

    if table_df.empty:
        return go.Figure()

    table_df['scraped_at'] = pd.to_datetime(table_df['scraped_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    table_df = table_df.sort_values(by='price', ascending=True)

    header_values = ['<b>Airline</b>', '<b>Departure</b>', '<b>Time</b>']
    cell_values = [table_df.airline, table_df.departure_date, table_df.flight_time]

    if not is_one_way:
        header_values.append('<b>Return</b>')
        cell_values.append(table_df.return_date)

    header_values += ['<b>Stops</b>', '<b>Duration</b>', '<b>Price</b>', '<b>Scraped at</b>']
    cell_values += [
        table_df.stops,
        table_df.duration,
        table_df.price.map('€{:,.2f}'.format),
        table_df.scraped_at
    ]

    # Create the Plotly Table
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=header_values,
            align='left',
            font=dict(size=12)
        ),
        cells=dict(
            values=cell_values,
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
