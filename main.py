import os
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv

from logger import logger_setup
from tracker import run_tracker
from search_manager import manage_searches
from db import Session
from email_notifier import notifier

load_dotenv()

logger = logger_setup("tracker.log")


def run_search_manager():
    with Session() as SessionLocal:
        _ = manage_searches(SessionLocal, read_google_sheets=True)


def run_full_tracker():
    with Session() as SessionLocal:
        searches = manage_searches(SessionLocal, read_google_sheets=True)
        if searches:
            run_tracker(SessionLocal, searches)


def run_full_tracker_with_notification():
    with Session() as SessionLocal:
        searches = manage_searches(SessionLocal, read_google_sheets=True)
        if searches:
            run_tracker(SessionLocal, searches)
    notifier()


# Schedule the task
schedule_time = str(os.getenv("SCHEDULE_TIME"))
schedule.every().day.at(schedule_time).do(run_full_tracker_with_notification)


def main():
    logger.info("===== Starting flight-price-tracker =====")

    schedule_mode = bool(os.getenv("SCHEDULE_MODE") == "True")
    late_scheduling_mode = bool(os.getenv("LATE_SCHEDULE_MODE") == "True")

    if schedule_mode:
        if datetime.now().time() > datetime.strptime(schedule_time, "%H:%M").time():
            logger.info(
                f"Scheduled time {schedule_time} has already passed today. "
            )
            if late_scheduling_mode:
                logger.info("Running tracker immediately due to late scheduling mode...")
                run_full_tracker()
        logger.info("Scheduler active. Waiting...")
        while True:
            # run_search_manager()
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    else:
        logger.info("Run flight price tracker once...")
        run_full_tracker()


if __name__ == "__main__":
    main()
