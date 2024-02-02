from email import encoders
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
import os
import smtplib

from custom_modules.log import logger

def send_email_with_attachment(host='127.0.0.1',
                               from_addr='test@test.test',
                               to_emails=[],
                               cc_emails=[],
                               bcc_emails=[],
                               subject='Test subject',
                               body_text='Test body',
                               files_to_attach=[]):
    # create the message
    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["To"] = ', '.join(to_emails)
    msg["cc"] = ', '.join(cc_emails)
    emails = to_emails + cc_emails + bcc_emails
    
    if body_text:
        # Determine text type (plain or html)
        mime_type, mime_subtype = ('html', 'html') if "<html>" in body_text else ('plain', 'plain')
        msg.attach(MIMEText(body_text, mime_subtype))

    for file_to_attach in files_to_attach:
        try:
            with open(file_to_attach, "rb") as file:
                data = file.read()
                attachment = MIMEApplication(data, Name=os.path.basename(file_to_attach))
                attachment['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_to_attach)}"'
                msg.attach(attachment)
        except IOError:
            logger.error(f"Error opening attachment file {file_to_attach}")

    try:
        with smtplib.SMTP(host) as server:
            server.sendmail(from_addr, emails, msg.as_string())
    except smtplib.SMTPException as e:
        logger.error(f"Failed to send email: {e}")
        return False
    return True
