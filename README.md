# otodom-scraper

Monitoruje wyniki wyszukiwania na otodom.pl i wysyła powiadomienie na Discorda,
gdy pojawi się nowa oferta. Działa jako kontener z cronem — przy każdym
uruchomieniu pobiera stronę wyników, porównuje ją z listą już widzianych ofert
i zgłasza tylko różnicę.

Obraz: `ghcr.io/fsmigasiewicz/otodom-scraper:latest` (amd64 + arm64)

## Jak to działa

Otodom to aplikacja Next.js — pełna lista ofert siedzi w bloku JSON
`__NEXT_DATA__` osadzonym w HTML-u. Scraper czyta właśnie ten blok, zamiast
parsować wyrenderowany DOM, więc jest odporny na zmiany wyglądu strony.

Oferty są deduplikowane po `slug`, bo Otodom potrafi zwrócić to samo ogłoszenie
drugi raz jako wpis promowany, z innym ID.

> **Uwaga:** jeśli Otodom zmieni strukturę swoich danych, scraper przerwie
> działanie z komunikatem *„struktura strony otodom.pl mogła się zmienić"*.
> To zamierzone — lepiej głośno paść niż po cichu przestać powiadamiać.

## Uruchomienie

```bash
docker run -d --name otodom-scraper \
  -e SEARCH_URL='https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/warszawa?...' \
  -e DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/ID/TOKEN' \
  -e CRON_SCHEDULE='0 * * * *' \
  -v otodom-data:/app/data \
  ghcr.io/fsmigasiewicz/otodom-scraper:latest
```

`SEARCH_URL` weź prosto z paska adresu — ustaw filtry w przeglądarce
(lokalizacje, cena, liczba pokoi, `daysSinceCreated`) i skopiuj gotowy URL.

`DISCORD_WEBHOOK_URL` to adres w formacie HTTPS: Discord → Ustawienia kanału →
Integracje → Webhooki → Kopiuj URL.

## Konfiguracja

Kolejność: **zmienna środowiskowa → `config.json` → wartość domyślna**.

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `SEARCH_URL` | — | **wymagane.** URL wyników wyszukiwania |
| `DISCORD_WEBHOOK_URL` | — | webhook Discorda; bez niego scraper tylko loguje |
| `CRON_SCHEDULE` | `*/15 * * * *` | harmonogram, 5 pól |
| `NOTIFY_ON_FIRST_RUN` | `false` | `true` = powiadom o wszystkim już za pierwszym razem |
| `REQUEST_TIMEOUT` | `30` | timeout HTTP w sekundach |
| `USER_AGENT` | Chrome 124 | nadpisanie nagłówka `User-Agent` |
| `ACCEPT_LANGUAGE` | `pl-PL,pl;q=0.9,…` | nadpisanie `Accept-Language` |
| `DATA_DIR` | `/app/data` | katalog na stan aplikacji |
| `SEEN_OFFERS_FILE` | `seen_offers.json` | nazwa pliku stanu wewnątrz `DATA_DIR` |
| `CONFIG_PATH` | `$DATA_DIR/config.json` | opcjonalny plik konfiguracyjny |

`NOTIFY_ON_FIRST_RUN=false` istnieje po to, żeby pierwsze uruchomienie nie
wysypało na kanał kilkudziesięciu powiadomień naraz — stan zostaje zapisany po
cichu, a powiadomienia zaczynają się od kolejnego przebiegu.

### `config.json` (opcjonalny, dla zgodności wstecz)

Starsze instalacje trzymały ustawienia w `$DATA_DIR/config.json` z kluczami
`search_url`, `discord_webhook_url`, `notify_on_first_run`, `request_timeout`,
`seen_offers_file`, `request_headers`. Plik nadal działa, ale zmienne
środowiskowe mają nad nim pierwszeństwo. Nowe wdrożenia nie potrzebują go wcale.

## Dane

W `DATA_DIR` powstaje jeden plik — `seen_offers.json` z ID widzianych ofert.
Podmontuj ten katalog jako wolumen; bez tego po każdym restarcie kontener
uzna wszystkie oferty za nowe (albo, przy `NOTIFY_ON_FIRST_RUN=false`,
przemilczy jeden cykl).

## Development

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cp .env.example .env && $EDITOR .env
set -a && . ./.env && set +a
./venv/bin/python scraper.py
```

Albo w kontenerze, ze zbudowaniem obrazu ze źródeł:

```bash
cp .env.example .env && $EDITOR .env
docker compose up --build
```

## Publikowanie obrazu

`.github/workflows/build.yml` buduje i wypycha obraz do GHCR przy każdym pushu
na `main` oraz przy tagach `v*`. Tagi obrazu: `latest` (z `main`), `1.2.3`
i `1.2` (z tagów semver) oraz `sha-<commit>`.

Nie trzeba nic konfigurować — workflow korzysta z wbudowanego `GITHUB_TOKEN`.
Po pierwszym udanym buildzie pakiet pojawi się w zakładce *Packages*.

### Widoczność obrazu

Widoczność pakietu w GHCR jest **niezależna od widoczności repozytorium** —
ustawia się ją w *Package settings → Change visibility*. Po pierwszym buildzie
przełącz pakiet na **public**, wtedy `docker pull` działa bez logowania.

Gdybyś kiedyś chciał go schować: prywatny pakiet wymaga na serwerze
`docker login ghcr.io -u fsmigasiewicz --password-stdin` z classic PAT
o uprawnieniu `read:packages`, a Watchtower potrzebuje wtedy własnej kopii
`~/.docker/config.json` zamontowanej pod `/config.json`. Pamiętaj przy tym, że
publiczny obraz i tak ujawnia kod — `scraper.py` leży w jego warstwach.

## Licencja

[MIT](LICENSE)
# homelab
# otodom-scraper
