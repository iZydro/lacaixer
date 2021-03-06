#!/opt/python3/bin/python
# -*- coding: utf-8 -*-

import urllib.request
import urllib.parse
import datetime
import os
import pytz
import ssl
import boto3
#import sqlite3
from decimal import Decimal
import configparser
import chart_studio.plotly as py      # Every function in this module will communicate with an external plotly server

from bs4 import BeautifulSoup

_EPOCH = datetime.datetime(1970, 1, 1)
money = "{:,.2f}"

my_plans = None

config = None


def print_add_text(message):
    print(message)
    return message + "\n"


def send_mail(mail_body, image_name=""):

    import smtplib
    import os
    from email.mime.image import MIMEImage

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

        if image_name != "":
            img_data = open(image_name, 'rb').read()
            image = MIMEImage(img_data, name=os.path.basename(image_name))
            msg.attach(image)

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
    #url = "https://portal4.lacaixa.es/apl/planes/fichas.index_es.html?PLA_idPla=" + str(stock_plan)
    #url = "https://www1.caixabank.es/apl/planes/fichas.index_es.html?PLA_idPla=" + str(stock_plan)
    url = "https://www1.caixabank.es/apl/planes/fichas.datosFundamentales_es.html?PLA_continuar=continuar&PLA_idPla=" + str(stock_plan)

    #https_sslv3_handler = urllib.request.HTTPSHandler(context=ssl.SSLContext(ssl.PROTOCOL_TLSv1))
    #opener = urllib.request.build_opener(https_sslv3_handler)
    #urllib.request.install_opener(opener)

    request = urllib.request.Request(url, urllib.parse.urlencode(params).encode('utf-8'), headers)
    resp = urllib.request.urlopen(request)

    soup = BeautifulSoup(resp.read(), features="html.parser")

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

    # Dynamo way of things...
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    dynamodb = boto3.resource(
        'dynamodb',
        aws_access_key_id=config["aws"]["aws_key"],
        aws_secret_access_key=config["aws"]["aws_secret"]
    )

    table = dynamodb.Table('lacaixer')

    # conn = sqlite3.connect('database.db')
    #c = conn.cursor()
    # c.execute('create table if not exists plans (id string, timestamp date, parts real) ')
    # conn.commit()

    text = ""

    total = Decimal(0)
    new_data = False

    for plan in my_plans:
        date, value = get_price(plan["id"])

        ts = Decimal((date - _EPOCH).total_seconds())
        print(ts)

        v = float(int(plan["parts"]*value*100))/100
        plan_value = Decimal(str(v))

        info = str(date)[:10] + " -> " + plan["name"] + " : " + str(value) + " = " + money.format(plan_value)
        text += info + "\n"
        total += plan_value

        # Check if exists in dynamo, if not, insert it

        # Convert "042" to "42" :|
        plan_id = str(int(plan["id"]))

        result = table.get_item(
            Key={
                'id': plan_id,
                'timestamp': ts
            }
        )
        if "Item" in result:
            print("Already inserted!")
        else:
            print("Inserting: " + plan_id + ", " + str(ts) + ", " + str(plan_value))
            table.put_item(
                Item={
                    'id': plan_id,
                    'timestamp': ts,
                    'parts': plan_value
                }
            )
            new_data = True

        # result = c.execute("select * from plans where id=? and timestamp=?", (plan["id"], ts))
        # results = result.fetchone()
        # if results:
        #     print("Already inserted!")
        # else:
        #     c.execute("insert into plans (id, timestamp, parts) values (?, ?, ?)", (plan["id"], ts, plan_value))
        #     conn.commit()
        #     new_data = True

    text = "Total value: " + money.format(total) + "\n" + text
    print(text)

    '''
    results = c.execute("select * from plans order by timestamp desc, id")
    for result in results.fetchall():
        id_plan = result[0]
        date = datetime.datetime.fromtimestamp(result[1], tz=pytz.utc)
        parts = result[2]
        print(date, id_plan, parts)
'''
    # conn.close()

    if new_data:

        image_created = ""

        x = []
        y = []

        # Read from dynamodb!
        print("Reading from dynamo")
        result = table.scan()

        print("Preparing data")
        data = {}
        for item in result["Items"]:
            id_plan = item["id"]
            date = datetime.datetime.fromtimestamp(item["timestamp"], tz=pytz.utc)
            parts = item["parts"]

            if date not in data:
                data[date] = 0

            data[date] += parts

        print("Sorting data")
        for datum in sorted(data):
            if data[datum] >= 100000:
                x.append(datum)
                y.append(data[datum])

        # conn = sqlite3.connect('database.db')
        # c = conn.cursor()
        # results = c.execute("select id, timestamp, sum(parts), count(id) from plans group by timestamp order by timestamp desc, id")
        # for result in results.fetchall():
        #     id_plan = result[0]
        #     date = datetime.datetime.fromtimestamp(result[1], tz=pytz.utc)
        #     parts = result[2]
        #     countid = result[3]
        #     if countid == 3:
        #         print(date, id_plan, parts)
        #         x.append(date)
        #         y.append(parts)

        # conn.close()

        try:
            print("Log in plotly")
            py.sign_in(config["plotly"]["plotly_username"], config["plotly"]["plotly_api_key"])

            print("Plotting")
            py.plot({                      # use `py.iplot` inside the ipython notebook
                "data": [{"x": x, "y": y}],
                "layout": {
                    "title": "Plans"
                }
            },
                filename='pensions_graph',      # name of the file as saved in your plotly account
                sharing='public',            # 'public' | 'private' | 'secret': Learn more: https://plot.ly/python/privacy
                auto_open=False
            )

            print("Saving screen")
            py.image.save_as({"data": [{"x": x, "y": y}]}, "pensions_graph.png")
            image_created = "pensions_graph.png"

            print("Sending mail")
            send_mail(text, image_created)

        except Exception as e:
            print("Could not send plot because of that:")
            print(e)

