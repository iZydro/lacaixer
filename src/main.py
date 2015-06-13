#!/opt/python3/bin/python
# -*- coding: utf-8 -*-

import urllib.request
import urllib.parse
import datetime
import pytz
import ssl
import sqlite3
import configparser

from bs4 import BeautifulSoup

_EPOCH = datetime.datetime(1970, 1, 1)
money = "{:,.2f}"

my_plans = None

config = None


def print_add_text(message):
    print(message)
    return message + "\n"


def send_mail(mail_body):

    import smtplib

    '''
A config.ini file must exist in order to send mails.

config.ini example:

[Mailer]
from: from_address
to: to_address
username: your_user_name
password: your_secret_password

[Plans]

'''
    try:
        from_address = config["Mailer"]["from"]
        to_address = config["Mailer"]["to"]
        username = config["Mailer"]["username"]
        password = config["Mailer"]["password"]

        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg['From'] = from_address
        msg['To'] = to_address
        msg['Subject'] = 'Planes'
        msg.attach(MIMEText(mail_body))

        # The actual mail send
        server = smtplib.SMTP_SSL('smtp.gmail.com:465')
        server.login(username, password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Could not send mail because of that:")
        print(e)


def get_price(stock_plan):
    headers = {}
    params = {}
    url = "https://portal4.lacaixa.es/apl/planes/fichas.index_es.html?PLA_idPla=" + str(stock_plan)

    #https_sslv3_handler = urllib.request.HTTPSHandler(context=ssl.SSLContext(ssl.PROTOCOL_TLSv1))
    #opener = urllib.request.build_opener(https_sslv3_handler)
    #urllib.request.install_opener(opener)

    request = urllib.request.Request(url, urllib.parse.urlencode(params).encode('utf-8'), headers)
    resp = urllib.request.urlopen(request)

    soup = BeautifulSoup(resp.read())

    datos_generales = soup.find(id="tabla_datos_generales")

    row = datos_generales.findAll("tr")[3]
    all_date_string = row.findAll("th")[0].contents[0]
    date_string = all_date_string.split("[")[1].split("]")[0]
    stock_date = datetime.datetime.strptime(date_string + " UTC", "%d-%m-%Y %Z")

    stock_value = row.findAll("td")[0].string
    stock_number = float(stock_value.split(" ")[0].replace(",", "."))

    return stock_date, stock_number


if __name__ == "__main__":

    config = configparser.ConfigParser()
    files = config.read("config.ini")
    if len(files) == 0:
        print("Could not read config file")
        exit(1)

    '''
    Fill in the plan array with data read form the ini file, as follows:

    [Plan 1]
    id: 999
    name: PlanCaixa Viejete
    parts: 1.5

    [Plan 2]
    id: 998
    name: PlanCaixa Bolsa
    parts: 10
    '''

    my_plans = []

    sections = config.sections()
    for section in sections:
        if "Plan" in section:
            my_plans.append(
                {"id": config[section]["id"], "name": config[section]["name"], "parts": float(config[section]["parts"])}
            )

    if len(my_plans) == 0:
        print("No plans found in config.ini file")
        exit(1)

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('create table if not exists plans (id string, timestamp date, parts real) ')
    conn.commit()

    text = "Plans value\n"

    total = 0.0
    new_data = False

    for plan in my_plans:
        date, value = get_price(plan["id"])

        ts = (date - _EPOCH).total_seconds()
        print(ts)

        plan_value = plan["parts"]*value
        info = str(date) + " -> " + plan["name"] + " : " + str(value) + " = " + money.format(plan_value)
        text += print_add_text(info)
        total += plan_value

        result = c.execute("select * from plans where id=? and timestamp=?", (plan["id"], ts))
        results = result.fetchone()
        if results:
            print("Already inserted!")
        else:
            c.execute("insert into plans (id, timestamp, parts) values (?, ?, ?)", (plan["id"], ts, plan_value))
            conn.commit()
            new_data = True

    text += print_add_text("Total value: " + money.format(total))

    results = c.execute("select * from plans order by timestamp desc, id")
    for result in results.fetchall():
        id_plan = result[0]
        date = datetime.datetime.fromtimestamp(result[1], tz=pytz.utc)
        parts = result[2]
        print(date, id_plan, parts)

    conn.close()

    if new_data:
        send_mail(text)
