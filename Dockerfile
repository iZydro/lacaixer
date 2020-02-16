FROM python:3

ENV PYTHONUNBUFFERED 1

ADD src/ /

RUN pip install beautifulsoup4 chart_studio configparser boto3 pytz

CMD [ "python", "./main.py" ]
