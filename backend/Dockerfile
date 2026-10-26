FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY . .
ENV PYTHONUNBUFFERED=1
RUN useradd -m -u 10001 convertflow && mkdir /data && chown convertflow:convertflow /data
USER convertflow
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
