# 🛫 Flight Price Tracker

A robust, automated Google Flights scraper built with Python, Selenium, and SQLAlchemy. It features a daily scheduler, structured logging, and smart "stealth" browser configurations to track flight prices without manual intervention.

## ✨ Features

Daily Automation: Scheduled to run every day.

Smart Scraper: Handles Google consent screens, clears pop-up recommendations, and extracts flight data reliably.

Database Integration: Saves all scraped data into a structured format for long-term price analysis.

External Requests: handles user track request via google forms/sheets.

Tracker App: tracked prices can be accessed via a dashboard web app.

## 🚀 Getting Started

### 1. Installation

Clone the repository:

```bash
git clone https://github.com/arminschaffer/flight_price_tracker
cd flight_price_tracker
```

### 2. Create virtual environment and install dependencies

```bash
uv sync
```

### 3. Configuration

Create a searches.json file in the root directory to define the flights you want to track (e.g. searches_examples.json):

```json
[
  {
    "origin": "VIE",
    "destination": "LHR",
    "earliest_departure": "2026-03-01",
    "latest_return": "2026-03-10",
    "min_stay_days": 3,
    "max_stay_days": 7
  }
]
```

## 🛠 Usage

Run Manually
To execute the scraper:

```bash
uv run main.py
```

## 🦭📦 Using Docker (Raspberry Pi / Linux)

### 1. Prerequisites

Ensure you have podman (or docker) and git installed on your Pi:

```bash
sudo apt update && sudo apt install -y podman git
```

### 2. Clone and Prepare

Pull the code directly onto the target device to ensure the build matches the CPU architecture:

```bash
git clone https://github.com/arminschaffer/flight_price_tracker
cd flight_price_tracker

# Create empty files for volumes to prevent permission issues
touch flight_database.db searches.json tracker.log scraper.log search_manager.log
```

### 3. Build and Run

To build the images and start the multi-container stack locally on the Pi, run:

```bash
podman-compose up --build -d
```

This command performs the following:

- Builds the ARM-native Chromium environment for the tracker.

- Orchestrates two services: the Tracker (data collection) and the Dash Web App (data visualization).

- Detaches the process (-d) to run the application in the background.

## 📋 Monitoring

The results can be viewed in a dash app by running the app.py.

The project maintains a detailed log of all activities:

- Terminal: Real-time progress updates.

- tracker.log: A persistent record of searches and any errors (timeouts, missing elements).

- scraper.log: Deep-dive logs from the Selenium driver.

## 📂 Project Structure

- main.py: Orchestrator and Scheduler.

- web_scraper.py: Selenium logic and Google Flights interaction.

- db.py: SQLAlchemy models and database configuration.

- searches.json: Your flight search configurations.

- app.py: dashboard web app.
