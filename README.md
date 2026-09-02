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

```bash
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

### 3) Instalace systemd služeb (jednorázově, host)

Tři služby ve `scripts/` zajišťují automatický běh po restartu/havárii:

| Soubor | Účel |
|---|---|
| `calyx-usb-serial.service` | Zaregistruje Calyx modem u kernel USB driveru po každém bootu (bez tohohle `/dev/ttyUSB*` po restartu nevznikne). |
| `gsm-gate-compose.service` | Po startu Dockeru spustí celý compose stack **včetně** `gsm_worker` (ten je v profilu `rpi`, běžný auto-start by ho vynechal). |
| `gsm-watchdog.service` + `.timer` | Každé 2 minuty kontroluje stav modemu, při zaseknutí restartuje `ModemManager`, při přetrvávajícím problému restartuje RPi. |

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

### 4) Ověření

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
