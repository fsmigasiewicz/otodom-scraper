FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Harmonogram crona - nadpisywalny zmienna CRON_SCHEDULE.
ENV CRON_SCHEDULE="*/15 * * * *"
# Katalog na stan aplikacji (seen_offers.json). Reszta konfiguracji
# przychodzi przez zmienne srodowiskowe - patrz README.
ENV DATA_DIR="/app/data"

VOLUME ["/app/data"]

ENTRYPOINT ["./entrypoint.sh"]
