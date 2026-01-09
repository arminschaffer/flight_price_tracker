#!/bin/bash

# Start the tracker (main.py) in the background
uv run main.py &

# Start the Dash app (app.py) in the foreground
# The container stays alive as long as this process is running
uv run app.py