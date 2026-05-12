import os
import ast
from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import create_engine

from logger import logger_setup
from db import DATABASE


logger = logger_setup("email_notifier.log", logger_name="email_notifier")
engine = create_engine(f'sqlite:///{DATABASE}', echo=False)

load_dotenv()

TEST_MAIL_ADDRESS = str(os.getenv("TEST_MAIL_ADDRESS"))
QUANTILES = [0., 0.01, 0.1, 0.25, 0.75, 0.9, 0.99, 1.]
SUBJECT = 'Flight Price Alarm for Flight {origin} to {destination}'
EMAIL_CONTENT = """
<html>
  <body>
    <p>Hello {user},</p>

    <p>
      Good news — I found a flight deal that is currently available at a great price:
    </p>

    <p>
      <b>Flight: {origin} to {destination}<br></b> 
      <b>Price: €{price}</b>
    </p>

    <p>
      You can view all details and track the fare here:<br>
      <a href="https://arminsraspberrypi.tail4b4315.ts.net/">
        Flight Price Tracker
      </a>
    </p>

    <p>
      Happy flight-tracking,<br>
      Your Flight-Price-Tracker-Bot
    </p>
  </body>
</html>
"""

def send_mail(recipient_email: str, subject: str, content: str) -> None:
    SENDER_EMAIL = str(os.getenv("GMAIL_ADDRESS"))
    EMAIL_PW = str(os.getenv("GMAIL_PW"))

    msg = EmailMessage()
    msg.set_content(content, subtype='html')
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SENDER_EMAIL, EMAIL_PW)
            smtp.send_message(msg)

        logger.info(f'Email sent to: {recipient_email}, subject: {subject}.')
        return None
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return None
    

def get_todays_data() -> pd.DataFrame:
    today = datetime.now().date().isoformat()
    print(today)
    query = f"""
    SELECT
        s.origin, 
        s.destination, 
        s.created_by,
        s.user_mail,
        p.price_list, 
        p.scraped_at,
        f.price
    FROM searches s
    INNER JOIN price_list p ON s.id = p.search_id
    INNER JOIN flights f ON p.id = f.price_list_id
    WHERE p.scraped_at >= :today
    """
    df = pd.read_sql(query, con=engine, params={'today': today})
    df = df.loc[:, ~df.columns.duplicated()].copy()

    return df


def get_todays_price_ranges(df) -> pd.DataFrame:
    df['price_list'] = df['price_list'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    df = df.explode('price_list')
    df['price_list'] = pd.to_numeric(df['price_list'])
    df = df['price_list'].quantile(np.array(QUANTILES)).round()
    return df
    

def notifier() -> None:
    df = get_todays_data()
    df_grouped = df.groupby(['origin','destination', 'created_by'])
    mail_count = 0

    for group_key, df_group in df_grouped:
        user_mail_address = df_group.user_mail.value
        # user_mail_address = TEST_MAIL_ADDRESS
        if not user_mail_address:
            continue 

        origin, destination, user = group_key
        df_min_price = df_group['price'].min()
        df_q = get_todays_price_ranges(df_group)

        if df_min_price <= df_q[0.1]:
            send_mail(
                user_mail_address, 
                SUBJECT.format(origin=origin, destination=destination), 
                EMAIL_CONTENT.format(user=user, origin=origin, destination=destination, price=df_min_price)
                )
            mail_count += 1

    logger.info(f'{mail_count} email notifications sent.')

    return None


if __name__ == "__main__":
    notifier()
