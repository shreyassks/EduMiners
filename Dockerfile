# Optional: containerizes the entry point for the reproducibility bonus.
# Build:  docker build -t eduminers .
# Run:    docker run --rm \
#           -v "$PWD/ACSEL:/app/ACSEL" \
#           -v "$PWD/data:/app/data" \
#           -v "$PWD/outputs:/app/outputs" \
#           eduminers
#
# The organizer dataset (ACSEL/ contest data + data/) is git-ignored and is NEVER
# baked into the image. It is mounted at run time, and outputs are written back to
# the mounted ./outputs folder.

FROM python:3.12-slim

# Reproducible, offline-friendly, no .pyc noise
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONHASHSEED=0

WORKDIR /app

# Install pinned dependencies first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only source and submission metadata (no dataset)
COPY src/ ./src/
COPY manifest.yml claims.json README.md ./

# ./ACSEL, ./data and ./outputs are provided via volume mounts at run time
CMD ["python", "src/run_all.py"]
