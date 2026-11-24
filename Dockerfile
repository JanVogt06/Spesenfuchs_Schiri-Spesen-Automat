# Multi-stage build: build the frontend, then the backend
# The frontend build is platform-independent and therefore runs on the
# builder's architecture - otherwise npm would be emulated for the arm64 image.
FROM --platform=$BUILDPLATFORM node:26-slim AS frontend-builder

WORKDIR /frontend

# Install frontend dependencies
COPY frontend/package*.json ./
RUN npm ci

# Copy the frontend code and build it
COPY frontend/ ./
RUN npm run build

# ===== Backend Stage =====
FROM python:3.14-slim

# At release time the version comes from the Git tag. Without it, the fallback
# value in core/config.py applies - a manual build is not a release.
ARG APP_VERSION=""
ENV APP_VERSION=${APP_VERSION}

LABEL org.opencontainers.image.title="Spesenfuchs" \
      org.opencontainers.image.description="Schiri-Spesen-Automat: erstellt Spesenabrechnungen automatisch aus DFB.net-Ansetzungen" \
      org.opencontainers.image.source="https://github.com/JanVogt06/spesenfuchs" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# System dependencies for Playwright + LibreOffice (DOCX/XLSX->PDF conversion).
# Carlito is metrically identical to Calibri, the font of the NOFV template.
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libreoffice-writer \
    libreoffice-calc \
    fonts-crosextra-carlito \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the Playwright browser - fixed path in the image, so it does not
# depend on HOME and does not end up in the data volume
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Copy the backend code
COPY src/ ./src/

# Copy the frontend build
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Everything mutable lives under /data, so a single volume is enough:
#   /data/.env     secrets (JWT_SECRET_KEY, ENCRYPTION_KEY)
#   /data/app.db   SQLite database (users, matches, officials, travel costs)
# Documents are not stored - they are generated on download.
ENV DATA_DIR=/data \
    FRONTEND_DIR=/app/frontend/dist \
    API_HOST=0.0.0.0 \
    API_PORT=8001 \
    TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data

VOLUME /data

# Expose the port
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('API_PORT', '8001') + '/api/health').read()"]

# Start command
CMD ["python", "src/main.py"]
