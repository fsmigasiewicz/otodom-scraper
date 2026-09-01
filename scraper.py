"""
Prosty scraper ofert z otodom.pl.

Po każdym wywołaniu:
1. Pobiera stronę wyników wyszukiwania (SEARCH_URL).
2. Wyciąga listę ofert z wbudowanych danych strony (__NEXT_DATA__).
3. Porównuje z poprzednio zapisanymi ofertami (seen_offers.json w DATA_DIR).
4. Dla każdej nowej oferty wysyła powiadomienie na Discorda (DISCORD_WEBHOOK_URL).
5. Zapisuje zaktualizowaną listę widzianych ofert.

Konfiguracja jest czytana w kolejności: zmienna środowiskowa -> config.json
-> wartość domyślna. Zmienne środowiskowe są zalecane; config.json jest
opcjonalny i istnieje głównie dla zgodności ze starszymi instalacjami.
Pełna lista ustawień: README.md.
"""

import json
import logging
import os
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
# Katalog na dane wytwarzane przez aplikacje (seen_offers.json). W kontenerze
# montowany jako wolumen, zeby stan przetrwal restart i aktualizacje obrazu.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).resolve()
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", DATA_DIR / "config.json"))

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("otodom_scraper")

ROOMS_LABELS = {
    "STUDIO": "kawalerka",
    "ONE": "1",
    "TWO": "2",
    "THREE": "3",
    "FOUR": "4",
    "FIVE": "5",
    "SIX": "6",
    "SIX_OR_MORE": "6+",
    "MORE": "więcej",
}

FLOOR_LABELS = {
    "CELLAR": "piwnica",
    "GROUND": "parter",
    "FIRST": "1",
    "SECOND": "2",
    "THIRD": "3",
    "FOURTH": "4",
    "FIFTH": "5",
    "SIXTH": "6",
    "SEVENTH": "7",
    "EIGHTH": "8",
    "NINTH": "9",
    "TENTH": "10",
    "ABOVE_TENTH": "powyżej 10",
    "GARRET": "poddasze",
}


def load_config() -> dict:
    """Wczytuje config.json, jesli istnieje. Brak pliku nie jest bledem -
    konfiguracja moze pochodzic wylacznie ze zmiennych srodowiskowych."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def setting(config: dict, env_name: str, config_key: str, default=None):
    """Zmienna srodowiskowa (o ile niepusta) wygrywa z config.json,
    a config.json z wartoscia domyslna."""
    value = os.environ.get(env_name)
    if value not in (None, ""):
        return value
    return config.get(config_key, default)


def bool_setting(config: dict, env_name: str, config_key: str, default: bool) -> bool:
    value = setting(config, env_name, config_key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "tak"}


def int_setting(config: dict, env_name: str, config_key: str, default: int) -> int:
    value = setting(config, env_name, config_key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        log.warning("Nieprawidlowa wartosc %s=%r - uzywam %d.", env_name, value, default)
        return default


def build_headers(config: dict) -> dict:
    headers = dict(config.get("request_headers") or DEFAULT_HEADERS)
    if os.environ.get("USER_AGENT"):
        headers["User-Agent"] = os.environ["USER_AGENT"]
    if os.environ.get("ACCEPT_LANGUAGE"):
        headers["Accept-Language"] = os.environ["ACCEPT_LANGUAGE"]
    return headers


def fetch_page(url: str, headers: dict, timeout: int) -> str:
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def find_first(data, key):
    """Rekurencyjnie szuka pierwszego wystąpienia klucza `key` w zagnieżdżonej strukturze."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            result = find_first(value, key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_first(item, key)
            if result is not None:
                return result
    return None


def extract_offers(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        raise RuntimeError(
            "Nie znaleziono danych __NEXT_DATA__ na stronie - struktura strony otodom.pl mogła się zmienić."
        )

    data = json.loads(script_tag.string)
    search_ads = find_first(data, "searchAds")
    if not search_ads or "items" not in search_ads:
        raise RuntimeError("Nie znaleziono listy ofert (searchAds.items) w danych strony.")

    offers = []
    seen_slugs = set()
    for item in search_ads["items"]:
        slug = item.get("slug")
        # Otodom czasem powtarza tę samą ofertę jako wpis promowany z innym ID,
        # więc deduplikujemy po slugu (jest unikalny i stabilny dla danej oferty).
        offer_id = slug or str(item.get("id"))
        if offer_id in seen_slugs:
            continue
        seen_slugs.add(offer_id)
        title = item.get("title") or "Brak tytułu"
        url = f"https://www.otodom.pl/pl/oferta/{slug}" if slug else None

        price_info = item.get("totalPrice") or {}
        price = price_info.get("value")
        currency = price_info.get("currency", "PLN")

        area = item.get("areaInSquareMeters")
        rooms = item.get("roomsNumber")
        floor = item.get("floorNumber")

        price_per_sqm_info = item.get("pricePerSquareMeter") or {}
        price_per_sqm = price_per_sqm_info.get("value")

        short_description = (item.get("shortDescription") or "").strip()

        image_url = None
        images = item.get("images") or []
        if images:
            image_url = images[0].get("large") or images[0].get("medium")

        location_label = ""
        location = (item.get("location") or {}).get("reverseGeocoding") or {}
        locations_list = location.get("locations") or []
        if locations_list:
            location_label = locations_list[-1].get("fullName", "")

        offers.append(
            {
                "id": offer_id,
                "title": title,
                "url": url,
                "price": price,
                "currency": currency,
                "price_per_sqm": price_per_sqm,
                "area": area,
                "rooms": rooms,
                "floor": floor,
                "location": location_label,
                "short_description": short_description,
                "image_url": image_url,
            }
        )

    return offers


def load_seen_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen_ids(path: Path, ids: set[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=2)


def format_price(price, currency) -> str:
    if price is None:
        return "brak ceny"
    return f"{price:,.0f} {currency}".replace(",", " ")


def format_floor(floor) -> str | None:
    if not floor:
        return None
    return FLOOR_LABELS.get(floor, floor)


def format_rooms(rooms) -> str | None:
    if not rooms:
        return None
    return ROOMS_LABELS.get(rooms, rooms)


def send_discord_notification(webhook_url: str, offer: dict) -> None:
    description_lines = []
    if offer["short_description"]:
        text = offer["short_description"]
        if len(text) > 350:
            text = text[:350].rsplit(" ", 1)[0] + "..."
        description_lines.append(text)
        description_lines.append("")

    rooms_label = format_rooms(offer["rooms"])
    if rooms_label:
        description_lines.append(f"**Pokoje:** {rooms_label}")
    if offer["area"]:
        description_lines.append(f"**Powierzchnia:** {offer['area']} m²")
    floor_label = format_floor(offer["floor"])
    if floor_label:
        description_lines.append(f"**Piętro:** {floor_label}")
    if offer["location"]:
        description_lines.append(f"**Lokalizacja:** {offer['location']}")
    description_lines.append(f"**Cena:** {format_price(offer['price'], offer['currency'])}")
    if offer["price_per_sqm"]:
        description_lines.append(f"**Cena za m²:** {format_price(offer['price_per_sqm'], offer['currency'])}")

    embed = {
        "title": offer["title"][:256],
        "url": offer["url"],
        "description": "\n".join(description_lines),
        "color": 0x2ECC71,
    }

    if offer["image_url"]:
        embed["thumbnail"] = {"url": offer["image_url"]}

    resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=15)
    resp.raise_for_status()


def main() -> None:
    config = load_config()

    search_url = setting(config, "SEARCH_URL", "search_url")
    if not search_url:
        raise SystemExit(
            "Brak adresu wyszukiwania. Ustaw zmienna SEARCH_URL "
            f"albo klucz search_url w {CONFIG_PATH}."
        )

    webhook_url = setting(config, "DISCORD_WEBHOOK_URL", "discord_webhook_url", "") or ""
    notify_on_first_run = bool_setting(config, "NOTIFY_ON_FIRST_RUN", "notify_on_first_run", False)
    timeout = int_setting(config, "REQUEST_TIMEOUT", "request_timeout", 30)
    headers = build_headers(config)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seen_path = DATA_DIR / setting(config, "SEEN_OFFERS_FILE", "seen_offers_file", "seen_offers.json")

    webhook_configured = bool(webhook_url) and "WSTAW_TUTAJ" not in webhook_url

    log.info("Pobieranie strony wyników wyszukiwania...")
    html = fetch_page(search_url, headers, timeout)
    offers = extract_offers(html)
    log.info("Znaleziono %d ofert na stronie.", len(offers))

    seen_ids = load_seen_ids(seen_path)
    is_first_run = not seen_ids and (not seen_path.exists() or seen_path.stat().st_size == 0)

    new_offers = [o for o in offers if o["id"] not in seen_ids]

    if new_offers:
        log.info("Nowe oferty: %d", len(new_offers))
        should_notify = webhook_configured and (not is_first_run or notify_on_first_run)

        for offer in new_offers:
            log.info("Nowa oferta: %s (%s)", offer["title"], offer["url"])
            if should_notify:
                try:
                    send_discord_notification(webhook_url, offer)
                    log.info("Wysłano powiadomienie na Discorda.")
                except Exception:
                    log.exception("Błąd przy wysyłaniu powiadomienia dla %s", offer["url"])

        if not webhook_configured:
            log.warning("Webhook Discorda nie jest skonfigurowany (DISCORD_WEBHOOK_URL) - powiadomienia nie zostały wysłane.")
        elif is_first_run and not notify_on_first_run:
            log.info("Pierwsze uruchomienie - oferty zapisane bez wysyłania powiadomień.")
    else:
        log.info("Brak nowych ofert.")

    all_ids = seen_ids | {o["id"] for o in offers}
    save_seen_ids(seen_path, all_ids)


if __name__ == "__main__":
    main()
