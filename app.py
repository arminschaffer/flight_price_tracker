import numpy as np
import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
from sqlalchemy import create_engine

# Database Setup
DATABASE = "flight_database.db"
engine = create_engine(f'sqlite:///{DATABASE}', echo=False)

def get_data():
    # Fetch data from SQL
    query = 'SELECT * FROM searches INNER JOIN price_history ON searches.id = price_history.search_id'
    df = pd.read_sql(query, con=engine)
    return df.loc[:,~df.columns.duplicated()].copy()

# Initial load for dropdown options
initial_df = get_data()

# App Setup
app = dash.Dash(__name__)

app.layout = html.Div(style={'fontFamily': 'Arial', 'padding': '20px', 'margin': '0 auto'}, children=[
    html.H2("Flight Tracker:"),

    # --- ROW 1: Route Dropdown (Full Width or Centered) ---
    html.Div([
        html.Label("Route:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id='route-drop', 
            options=[{'label': f"{r.origin} to {r.destination}", 'value': f"{r.origin}|{r.destination}"} 
                    for r in initial_df[['origin', 'destination']].drop_duplicates().itertuples()],
            value=f"{initial_df.iloc[0]['origin']}|{initial_df.iloc[0]['destination']}"
        )
    ], style={'width': '100%', 'marginBottom': '20px'}),

    # --- ROW 2: Checklist + Date Dropdown (Side-by-Side) ---
    html.Div([
        # Left Side: Checklist
        html.Div([
            html.Label("Toggle Price Metrics:", style={'fontWeight': 'bold'}),
            dcc.Checklist(
                id='price-mode',
                options=[
                    {'label': ' Min Price', 'value': 'min'},
                    {'label': ' Average Price', 'value': 'mean'}
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

    # --- ROW 3: Graphs (Side-by-Side) ---
    html.Div([
        html.Div([
            dcc.Graph(id='lowest-price-line', style={'height': '400px'})
        ], style={'width': '49%'}),

        html.Div([
            dcc.Graph(id='price-heatmap', style={'height': '400px'})
        ], style={'width': '49%'})
    ], style={'display': 'flex', 'justifyContent': 'space-between'}),

    dcc.Interval(id='interval-component', interval=30*60*1000, n_intervals=0)
])


# Callback to update line plot (id='lowest-price-line')
@app.callback(
    Output('lowest-price-line', 'figure'),
    Input('route-drop', 'value'),
    Input('price-mode', 'value'), # This is now a LIST
    Input('interval-component', 'n_intervals')
)
def update_scatter(selected_route, selected_metrics, n):
    if not selected_route: return go.Figure()
    
    origin, dest = selected_route.split('|')
    df = get_data()

    mask = (df['origin'] == origin) & (df['destination'] == dest)
    df_temp = df[mask].copy()
    df_temp['scraped_at'] = pd.to_datetime(df_temp['scraped_at']).dt.date

    fig = go.Figure()

    # Check if 'min' is in the list of selected metrics
    if 'min' in selected_metrics:
        df_min = df_temp.groupby('scraped_at')['price'].min()
        fig.add_trace(go.Scatter(
            x=df_min.index, y=df_min.values,
            name='Min Price',
            line=dict(color='#2ca02c', width=3), # Clean green
            mode='lines+markers'
        ))

    # Check if 'mean' is in the list of selected metrics
    if 'mean' in selected_metrics:
        df_mean = df_temp.groupby('scraped_at')['price'].mean()
        fig.add_trace(go.Scatter(
            x=df_mean.index, y=df_mean.values,
            name='Avg Price',
            line=dict(color='#1f77b4', width=3, dash='dash'), # Dotted blue
            mode='lines+markers'
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

    return fig

# Callback to update Date Dropdown based on Route
@app.callback(
    Output('date-drop', 'options'),
    Output('date-drop', 'value'),
    Input('route-drop', 'value')
)
def update_date_options(selected_route):
    origin, dest = selected_route.split('|')
    # Use the live data to find available dates for THIS specific route
    df = get_data()
    relevant_dates = sorted(pd.to_datetime(df[(df['origin'] == origin) & (df['destination'] == dest)]['scraped_at']).dt.date.unique(), reverse=True)
    
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
    Input('interval-component', 'n_intervals') # Refresh when interval triggers
)
def update_heatmap(selected_route, selected_date, n):
    if not selected_date: return go.Figure()
    
    origin, dest = selected_route.split('|')
    df = get_data() # Pull fresh data
    
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
        plot_bgcolor='#f2f2f2', # Light grey
        xaxis={'tickformat': '%d %b', 'dtick': 'D1', 'showgrid': False, 'tickangle': -45},
        yaxis={'tickformat': '%d %b', 'dtick': 'D1', 'showgrid': False},
        margin=dict(t=30, b=30, l=30, r=30)
    )
    return fig


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)