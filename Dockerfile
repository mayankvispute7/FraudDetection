# 1. Base Image: Lightweight, official Python Linux environment
FROM python:3.10-slim

# 2. Working Directory: Create a folder inside the container
WORKDIR /app

# 3. Copy Dependencies: Copy requirements first for Docker layer caching
COPY requirements.txt .

# 4. Install Dependencies: Run pip with extended timeout
RUN pip install --default-timeout=300 --no-cache-dir -r requirements.txt

# 5. Copy the Application Code
COPY . .

# 6. Expose Port
EXPOSE 8000

# 7. Run Uvicorn: Supports dynamic $PORT on Render/Railway/Cloud or defaults to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
