# Multi-stage Build: Frontend bauen, dann Backend
# Das Frontend-Build ist plattformunabhaengig und laeuft daher auf der
# Architektur des Builders - sonst wuerde npm beim arm64-Image emuliert.
FROM --platform=$BUILDPLATFORM node:26-slim AS frontend-builder

WORKDIR /frontend

# Frontend Dependencies installieren
COPY frontend/package*.json ./
RUN npm ci

# Frontend Code kopieren und bauen
COPY frontend/ ./
RUN npm run build

# ===== Backend Stage =====
FROM python:3.14

LABEL org.opencontainers.image.title="Spesenfuchs" \
      org.opencontainers.image.description="Schiri-Spesen-Automat: erstellt Spesenabrechnungen automatisch aus DFB.net-Ansetzungen" \
      org.opencontainers.image.source="https://github.com/JanVogt06/spesenfuchs" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# System-Dependencies für Playwright + LibreOffice (DOCX->PDF Konvertierung)
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
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Browser installieren - fester Pfad im Image, damit er nicht
# von HOME abhängt und nicht im Daten-Volume landet
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Backend Code kopieren
COPY src/ ./src/

# Frontend Build kopieren
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Alles Veränderliche liegt unter /data, damit ein einziges Volume genügt:
#   /data/.env     Secrets (JWT_SECRET_KEY, ENCRYPTION_KEY)
#   /data/app.db   SQLite-Datenbank (User, Spiele, Unparteiische, Fahrtkosten)
# Dokumente werden nicht abgelegt - sie entstehen beim Download.
ENV DATA_DIR=/data \
    FRONTEND_DIR=/app/frontend/dist \
    API_HOST=0.0.0.0 \
    API_PORT=8001 \
    TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data

VOLUME /data

# Port exposieren
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('API_PORT', '8001') + '/api/health').read()"]

# Start Command
CMD ["python", "src/main.py"]
