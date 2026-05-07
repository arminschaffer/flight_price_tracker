import os
import pytest
from dotenv import load_dotenv

from email_notifier import send_mail


def test_send_mail():
    TEST_MAIL_ADDRESS = str(os.getenv("TEST_MAIL_ADDRESS"))

    subject = "Testing E-Mail Notifier"
    content = "This is a test mail to check if the mail notifier works correctly."
    msg = send_mail(TEST_MAIL_ADDRESS, subject, content)
    assert msg is not None