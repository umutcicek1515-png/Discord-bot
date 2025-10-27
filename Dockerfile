FROM python:3.11-slim

WORKDIR /app

RUN apt-get update 
    ffmpeg \
ECHO is off.
ECHO is off.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "musicbot.py"]
