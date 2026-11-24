FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0 requests==2.32.3

COPY app.py /app/app.py
COPY static /app/static

RUN mkdir -p /app/cache

EXPOSE 8505

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8505"]
