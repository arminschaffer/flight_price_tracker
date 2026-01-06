# 🛫 Flight Price Tracker
A robust, automated Google Flights scraper built with Python, Selenium, and SQLAlchemy. It features a daily scheduler, structured logging, and smart "stealth" browser configurations to track flight prices without manual intervention.

## ✨ Features
Daily Automation: Scheduled to run every day at 10:00 AM using the schedule library.

Smart Scraper: Handles Google consent screens, clears pop-up recommendations, and extracts flight data reliably.

Structured Logging: Uses RotatingFileHandler to keep track of successes and errors without filling up your disk.

High Performance: Optimized with uv for lightning-fast environment management and execution.

Database Integration: Saves all scraped data into a structured format for long-term price analysis.

## 🚀 Getting Started
1. Prerequisites
Ensure you have uv installed on your system:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Installation
Clone the repository and sync the environment:

```bash
git clone <your-repo-url>
cd flight_price_tracker
```

### Create virtual environment and install dependencies
```bash
uv sync
```

3. Configuration
Create a searches.json file in the root directory to define the flights you want to track:

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
To execute the scraper once immediately:

```bash

uv run main.py --now
```

Start the Scheduler
To start the script in "Waiting" mode (it will run every day at 10:00):

```bash

uv run main.py
```

Background Execution (Linux)
To keep the scheduler running after you close your terminal:

```bash

nohup uv run main.py &
```

## 📋 Monitoring
The project maintains a detailed log of all activities:

Terminal: Real-time progress updates.

tracker.log: A persistent record of searches and any errors (timeouts, missing elements).

scraper.log: Deep-dive logs from the Selenium driver.

## 📂 Project Structure
main.py: Orchestrator and Scheduler.

web_scraper.py: Selenium logic and Google Flights interaction.

db.py: SQLAlchemy models and database configuration.

searches.json: Your flight search configurations.