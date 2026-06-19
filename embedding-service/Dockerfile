FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FASTEMBED_CACHE_PATH=/models/fastembed

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

COPY app.py .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
