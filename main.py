import os
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv

from logger import logger_setup
from tracker import run_tracker

load_dotenv()


logger = logger_setup("tracker.log")

# Schedule the task
schedule_time = str(os.getenv("SCHEDULE_TIME"))
schedule.every().day.at(schedule_time).do(run_tracker)


def main():
    schedule_mode = bool(os.getenv("SCHEDULE_MODE"))

    if schedule_mode:
        if datetime.now().time() > datetime.strptime(schedule_time, "%H:%M").time():
            logger.info(
                f"Scheduled time {schedule_time} has already passed today. "
                f"Running tracker immediately before scheduling."
            )
            run_tracker()
        logger.info("Scheduler active. Waiting...")
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    else:
        logger.info("Run price tracker once...")
        run_tracker()


if __name__ == "__main__":
    main()
