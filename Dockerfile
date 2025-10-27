FROM python:3.11-slim

WORKDIR /app

RUN apt-get update ^&^& apt-get install -y echo    ffmpeg echo    ^&^& rm -rf /var/lib/apt/lists/* echo    ^&^& apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "musicbot.py"]
