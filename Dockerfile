FROM python:3.11-slim 
 
WORKDIR /app 
 
    ffmpeg  
 
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt 
 
COPY . . 
 
CMD ["python", "musicbot.py"] 
