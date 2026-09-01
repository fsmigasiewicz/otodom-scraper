#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/app/data}"
CRON_SCHEDULE="${CRON_SCHEDULE:-*/15 * * * *}"
PYTHON_BIN="$(command -v python)"
ENV_FILE=/etc/otodom-scraper.env

mkdir -p "$DATA_DIR"

if [ -z "$SEARCH_URL" ] && [ ! -f "${CONFIG_PATH:-$DATA_DIR/config.json}" ]; then
    echo "BLAD: brak konfiguracji." >&2
    echo "Ustaw zmienna SEARCH_URL (zalecane) albo zamontuj config.json w $DATA_DIR." >&2
    exit 1
fi

# Cron uruchamia zadania z niemal pustym srodowiskiem - zmienne przekazane do
# kontenera przez docker/compose NIE sa dla niego widoczne. Zrzucamy je wiec do
# pliku, ktory zadanie cronowe sobie zasourcuje.
#
# Wartosci trafiaja tam w pojedynczych cudzyslowach z escapowaniem, bo
# SEARCH_URL zawiera znaki specjalne powloki (&, ?, =) - bez tego cron
# wykonalby fragment URL-a jako polecenie.
: > "$ENV_FILE"
chmod 600 "$ENV_FILE"
for var in SEARCH_URL DISCORD_WEBHOOK_URL NOTIFY_ON_FIRST_RUN REQUEST_TIMEOUT \
           USER_AGENT ACCEPT_LANGUAGE DATA_DIR CONFIG_PATH SEEN_OFFERS_FILE TZ; do
    eval "is_set=\${$var+yes}"
    [ "$is_set" = yes ] || continue
    eval "value=\$$var"
    escaped=$(printf '%s' "$value" | sed "s/'/'\\\\''/g")
    printf "export %s='%s'\n" "$var" "$escaped" >> "$ENV_FILE"
done

# Plik w /etc/cron.d wymaga pola "user" i pelnej sciezki do interpretera,
# bo crond uruchamia zadania z minimalnym PATH.
# Uwaga: w crontabie znak '%' ma znaczenie specjalne (nowa linia), dlatego
# zadne dane uzytkownika nie moga trafic do tej linii - stad plik z env.
printf '%s root . %s; cd /app && %s scraper.py >> /proc/1/fd/1 2>> /proc/1/fd/2\n' \
    "$CRON_SCHEDULE" "$ENV_FILE" "$PYTHON_BIN" > /etc/cron.d/otodom_scraper
chmod 0644 /etc/cron.d/otodom_scraper

echo "Harmonogram crona: $CRON_SCHEDULE"
echo "Katalog danych:    $DATA_DIR"
echo "Wykonuje pierwsze sprawdzenie ofert..."
"$PYTHON_BIN" scraper.py || true

exec cron -f
