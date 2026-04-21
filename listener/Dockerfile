FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# COPY EVERYTHING (config.py, worker.py, handlers.py, etc.)
COPY . .

# Run the new conductor
CMD ["python", "main.py"]