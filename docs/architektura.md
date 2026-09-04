# Architektura

## Přehled komponent

Systém je rozdělený na dvě hlavní části:

1. **Django web aplikace**
   - uživatelské účty,
   - administrační rozhraní (dashboard),
   - konfigurace pravidel,
   - logování a audit.
2. **GSM worker**
   - periodicky čte frontu odchozích akcí,
   - komunikuje s modemem přes `ModemManager`/`mmcli` (D-Bus),
   - vyhodnocuje úspěch/neúspěch a zapisuje výsledek.

   Detaily hardwaru, softwarového stacku a diagnostiky viz [Modem – hardware a diagnostika](modem-diagnostika.md).

Datové úložiště je **PostgreSQL**.

## Kontejnery

- `db` – PostgreSQL databáze,
- `web` – Django aplikace,
- `pgadmin` – DB administrace,
- `gsm_worker` – oddělený worker (profil `rpi`), mluví s modemem přes D-Bus socket namountovaný z hostu (`/run/dbus`), kde běží `ModemManager`,
- `mkdocs` – dokumentace (samostatný compose soubor).

## Web server

`web` kontejner běží pod **gunicorn** (víc workerů, `GUNICORN_WORKERS` env, výchozí 3), ne pod Django dev serverem. Statické soubory (CSS/JS) servíruje **WhiteNoise** middleware přímo z gunicorn procesu (komprimované, s hashem ve jméně pro cache busting) – žádný samostatný nginx kontejner není potřeba. Vědomé rozhodnutí kvůli jednoduchosti údržby (o kontejner/config vrstvu míň) na téhle velikosti nasazení; nginx by dával smysl hlavně kvůli TLS nebo víc službám za jedním vstupním bodem.

`manage.py collectstatic` běží při každém startu kontejneru (ne jen při buildu) – `STATIC_ROOT` je uvnitř bind-mountované `./django_app`, takže build-time výstup by byl přepsán bind mountem.

## Doménové entity

- **PhoneNumber** – telefonní číslo s příznakem aktivace, popisem a vazbou na uživatele/skupiny.
- **Group** – logická skupina čísel.
- **AutomationRule** – pravidlo pro reakci na příchozí události.
- **IncomingEventLog** – audit příchozích událostí.
- **OutgoingAction** – fronta akcí čekajících na zpracování nebo již zpracovaných.
- **DeviceObject** – model zařízení/objektu v terénu.
- **DeviceObjectApiCredential** – token pro API ingest dat objektů.
- **GatewaySettings** – konfigurace modemové brány a provozních parametrů.

## Datový tok události

1. Do systému přijde událost (SMS, volání nebo API).
2. Událost se uloží do `IncomingEventLog`.
3. Engine vyhodnotí aktivní `AutomationRule` podle priority.
4. Pro každé shodné pravidlo vytvoří `OutgoingAction`.
5. `gsm_worker` vezme akce z fronty a provede je přes modem.
6. Výsledek provedení se zapíše (stav, detail, čas zpracování).

## Odpovědnost vrstev

- **Forms/Views**: validace vstupu a business flow z UI.
- **Services**: pravidlový engine a worker logika.
- **Models**: datová konzistence a doménová pravidla.
- **Templates**: role-based zobrazení CRUD akcí.
