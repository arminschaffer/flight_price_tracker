import os
from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage
import pandas as pd
from sqlalchemy import create_engine

from logger import logger_setup
from db import DATABASE

logger = logger_setup("email_notifier.log", logger_name="email_notifier")
engine = create_engine(f'sqlite:///{DATABASE}', echo=False)

load_dotenv()


def send_mail(recipient_email: str, subject: str, content: str):
    SENDER_EMAIL = str(os.getenv("GMAIL_ADDRESS"))
    EMAIL_PW = str(os.getenv("GMAIL_PW"))

    msg = EmailMessage()
    msg.set_content(content)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            # Use your email and the 16-character App Password
            smtp.login(SENDER_EMAIL, EMAIL_PW)
            smtp.send_message(msg)

        logger.info(f'Email sent to: {recipient_email}, subject: {subject}.')
        return msg
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return None
    

def get_flight_prices():
    query = """
    SELECT * FROM searches
    INNER JOIN price_list ON searches.id = price_list.search_id
    INNER JOIN flights ON price_list.id = flights.price_list_id
    """
    df = pd.read_sql(query, con=engine)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    return None


def get_flight_price_range():
    return None
    

def notifier():
    return None