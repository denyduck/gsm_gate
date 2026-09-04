# GSM Gate

Webová aplikace pro správu GSM brány běžící na Raspberry Pi 4/5 s modemem **Teltonika Calyx 4G (EBD021)**, napojeným přes **ModemManager**.

## Aktuální stav

Implementováno:
- uživatelské účty (registrace, přihlášení, odhlášení),
- dashboard pro správu telefonních čísel,
- skupiny příjemců,
- sdílení přístupu přes uživatele ve skupinách a číslech,
- automatizační pravidla pro příchozí SMS/volání,
- log příchozích událostí,
- fronta odchozích akcí,
- worker pro zpracování modemu přes ModemManager/`mmcli` (D-Bus),
- sledování síly signálu (live na dashboardu i ve frontě),
- watchdog pro automatické zotavení zaseknutého modemu.

Poznámka:
- plné HW napojení vyžaduje spuštění `gsm_worker` služby s profilem `rpi` a běžící `ModemManager` na hostu (viz níže).

## Spuštění v Dockeru

Nejdřív nastav `.env` (viz [krok 3 níže](#3-konfigurace-prostředí-env) – hlavně `DJANGO_SECRET_KEY` a `ALLOWED_HOSTS`), pak:

```bash
cp .env.example .env   # jen poprvé
docker compose up -d --build
```

Aplikace:
- Django: http://localhost:8000
- pgAdmin: http://localhost:8080

## Spuštění workeru pro RPi + modem

Worker běží v samostatném kontejneru `gsm_worker` (profil `rpi`). Modem řídí `ModemManager` na hostu, kontejner s ním mluví přes D-Bus (mount `/run/dbus`), ne přes přímé mapování sériového portu.

```bash
docker compose --profile rpi up -d --build gsm_worker
```

Klíčové proměnné prostředí:
- `GSM_ENABLED` (musí být `true`),
- `GSM_WORKER_INTERVAL` (interval smyčky workeru),
- `GSM_MAX_ACTIONS_PER_CYCLE` (limit odeslání za cyklus).

Rychlý smoke test worker commandu:

```bash
docker compose --profile rpi run --rm gsm_worker python manage.py gsm_gateway_worker --once
```

Podrobná diagnostika hardwaru/softwaru modemu: [`docs/modem-diagnostika.md`](docs/modem-diagnostika.md).

## Kompletní nasazení na novou RPi / obnova po havárii

**Důležité:** `git clone`/`git pull` stáhne jen kód. Systémové služby (Docker, ModemManager) a jednorázová registrace modemu se musí nastavit ručně — git je nespravuje. Bez těchto kroků aplikace po čerstvém nasazení nebo výměně SD karty nenaběhne sama.

### 1) Systémové závislosti (jednorázově, host)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin modemmanager
sudo systemctl enable --now docker
sudo systemctl enable --now ModemManager
```

### 2) Stažení repozitáře

```bash
git clone https://github.com/denyduck/gsm_gate.git
cd gsm_gate
```

### 3) Konfigurace prostředí (.env)

```bash
cp .env.example .env
```

V `.env` uprav (viz komentáře v souboru):
- `DJANGO_SECRET_KEY` – vygeneruj vlastní: `docker compose run --rm web python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`, výsledek vlož do `.env`. Bez vlastního klíče appka běží na nebezpečném vývojovém fallbacku.
- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` – IP/hostname, přes které bránu otvíráš v prohlížeči (výchozí je `10.10.10.234` – uprav, pokud je jiná nebo se změnila).
- `DJANGO_DEBUG` – nech `False`; `True` jen dočasně při ladění (odhaluje tracebacky).

`.env` se necommituje (viz `.gitignore`) – po výměně SD karty/RPi tenhle krok udělej znovu.

### 4) Instalace systemd služeb (jednorázově, host)

Tři služby ve `scripts/` zajišťují automatický běh po restartu/havárii:

| Soubor | Účel |
|---|---|
| `calyx-usb-serial.service` | Zaregistruje Calyx modem u kernel USB driveru po každém bootu (bez tohohle `/dev/ttyUSB*` po restartu nevznikne). |
| `gsm-gate-compose.service` | Po startu Dockeru spustí celý compose stack **včetně** `gsm_worker` (ten je v profilu `rpi`, běžný auto-start by ho vynechal). |
| `gsm-watchdog.service` + `.timer` | Každé 2 minuty kontroluje stav modemu, při zaseknutí restartuje `ModemManager`, při přetrvávajícím problému restartuje RPi. |
| `gsm-backup.service` + `.timer` (volitelné) | Jednou denně vyexportuje data brány do `django_app/backups/` a smaže zálohy starší 14 dní. Slouží jako doplněk k ručnímu exportu v appce (`Zálohování` v menu, jen pro superusera) - viz [Nasazení a obnova](docs/nasazeni-a-obnova.md). |
| `gsm-prune.service` + `.timer` (volitelné) | Jednou denně smaže staré `IncomingEventLog`/`OutgoingAction`/`SignalReading` podle retenční politiky (`RETENTION_DAYS_LOGS`/`RETENTION_DAYS_SIGNAL_HISTORY` v `.env`, výchozí 90/30 dní). Doplněk k ručnímu "Reset dat" na stránce Zálohování. |

```bash
sudo cp scripts/calyx-usb-serial.service /etc/systemd/system/
sudo cp scripts/gsm-gate-compose.service /etc/systemd/system/
sudo cp scripts/gsm-watchdog.service scripts/gsm-watchdog.timer /etc/systemd/system/
sudo cp scripts/gsm_watchdog.sh /usr/local/bin/gsm_watchdog.sh
sudo chmod +x /usr/local/bin/gsm_watchdog.sh

sudo systemctl daemon-reload
sudo systemctl enable --now calyx-usb-serial.service
sudo systemctl enable --now gsm-gate-compose.service
sudo systemctl enable --now gsm-watchdog.timer
```

Volitelně, pravidelné zálohy dat:

```bash
sudo cp scripts/gsm-backup.service scripts/gsm-backup.timer /etc/systemd/system/
sudo cp scripts/gsm_backup.sh /usr/local/bin/gsm_backup.sh
sudo chmod +x /usr/local/bin/gsm_backup.sh

sudo systemctl daemon-reload
sudo systemctl enable --now gsm-backup.timer
```

Volitelně, pravidelné mazání starých dat:

```bash
sudo cp scripts/gsm-prune.service scripts/gsm-prune.timer /etc/systemd/system/
sudo cp scripts/gsm_prune.sh /usr/local/bin/gsm_prune.sh
sudo chmod +x /usr/local/bin/gsm_prune.sh

sudo systemctl daemon-reload
sudo systemctl enable --now gsm-prune.timer
```

### 5) Ověření

```bash
mmcli -m 0                              # modem by měl mít state: registered
docker compose --profile rpi ps         # web, db, pgadmin, gsm_worker běží
docker compose --profile rpi logs --tail=20 gsm_worker
systemctl list-timers gsm-watchdog.timer
```

Po tomhle kompletním nastavení stačí při běžných aktualizacích kódu (ne po výměně SD karty/RPi) jen:

```bash
git pull
docker compose up -d --build
docker compose --profile rpi up -d --build gsm_worker
```

Systémové služby (krok 3) se instalují jen jednou na dané fyzické zařízení — nejsou to soubory, které by se aplikovaly samy při `git pull`.

## Cíl projektu

Tento projekt je administrační a automatizační vrstva GSM brány. Web část řeší správu, pravidla a audit, zatímco oddělený worker zajišťuje komunikaci s modemem.

## Dokumentace v MkDocs

Projekt obsahuje samostatný compose soubor pro dokumentaci:

```bash
docker compose -f docker-compose.mkdocs.yml up -d --build
```

Dokumentace poběží na:
- http://localhost:8010

Hlavní soubory dokumentace:
- `mkdocs.yml`
- `docs/index.md`
- `docs/architektura.md`
- `docs/funkcionalita.md`
- `docs/role-a-opravneni.md`
- `docs/api-objekty-zarizeni.md`
- `docs/provozni-scenare.md`
- `docs/modem-diagnostika.md`
- `docs/troubleshooting.md`

## Autor a verze

Aktuální verze: **1.0.0** (viz `APP_VERSION` v `django_app/gsm_gate/settings.py`, zobrazuje se i v patičce appky).

Autor: _doplnit_ (`APP_AUTHOR` v `django_app/gsm_gate/settings.py` – jedno místo, ze kterého se jméno/přezdívka propíše i do patičky appky).
