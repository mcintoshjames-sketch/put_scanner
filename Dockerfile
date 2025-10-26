# Strategy Lab Streamlit app Dockerfile
FROM python:3.11-slim

# Prevents Python from writing .pyc files and buffers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set workdir
WORKDIR /app

# System deps (optional: add tini/curl if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . /app

# Expose default Streamlit port
EXPOSE 8501

# Run the Strategy Lab app
ENTRYPOINT ["streamlit", "run", "strategy_lab.py", "--server.address=0.0.0.0", "--server.port=8501"]
