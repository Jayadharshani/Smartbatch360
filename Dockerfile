FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=10000
EXPOSE 10000
# Demo mode: loads sample data on every start, then serves the app on the platform's $PORT (Render sets it).
CMD ["sh", "-c", "flask --app run demo && gunicorn -b 0.0.0.0:${PORT} run:app --workers 1 --threads 4"]
