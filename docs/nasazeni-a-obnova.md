# Nasazení a obnova po havárii

Tato stránka popisuje kompletní postup nasazení na novou Raspberry Pi (nová SD karta, nová deska, obnova po havárii) – tedy vše, co `git pull` sám o sobě nezajistí.

**Důležité:** `git clone`/`git pull` stáhne jen kód. Systémové služby (Docker, ModemManager) a jednorázová registrace modemu u kernelu se musí nastavit ručně na hostitelském systému – git systémové služby nespravuje. Bez těchto kroků aplikace po čerstvém nasazení nebo výměně SD karty nenaběhne sama.

## 1) Systémové závislosti (jednorázově, host)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin modemmanager
sudo systemctl enable --now docker
sudo systemctl enable --now ModemManager
```

## 2) Stažení repozitáře

```bash
git clone https://github.com/denyduck/gsm_gate.git
cd gsm_gate
```

## 3) Konfigurace prostředí (.env)

```bash
cp .env.example .env
```

V `.env` uprav:
- `DJANGO_SECRET_KEY` – vygeneruj vlastní (`docker compose run --rm web python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) a vlož do `.env`. Bez vlastního klíče appka běží na nebezpečném vývojovém fallbacku (rozpoznatelný podle prefixu `django-insecure-`, `manage.py check --deploy` na něj upozorní).
- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` – IP/hostname, přes které bránu otvíráš (výchozí v `docker-compose.yml` je `10.10.10.234` – uprav, pokud se změnila).
- `DJANGO_DEBUG` – nech `False` (produkce). `True` jen dočasně při ladění – odhaluje tracebacky/cesty/SQL komukoliv.
- `MKDOCS_BASE_URL` – adresa běžícího MkDocs webu (výchozí `http://10.10.10.234:8010`); appka na ni odkazuje v menu a v doporučeních Sebediagnostiky.

`.env` je v `.gitignore` (obsahuje tajný klíč) – po výměně SD karty/RPi ho je potřeba znovu vytvořit, `git pull` ho nepřinese.

## 4) Instalace systemd služeb (jednorázově, host)

Tři služby ve `scripts/` zajišťují, že po restartu/havárii naběhne vše samo, bez ručního zásahu:

| Soubor | Účel |
|---|---|
| `calyx-usb-serial.service` | Zaregistruje Calyx modem u kernel `option` driveru po každém bootu. Runtime stav kernelu se resetuje při každém restartu – bez téhle služby `/dev/ttyUSB*` po rebootu nevznikne a `ModemManager` modem neuvidí. |
| `gsm-gate-compose.service` | Po startu Dockeru spustí celý compose stack **včetně** `gsm_worker` (ten je v profilu `rpi`, běžný auto-start bez příznaku by ho vynechal). |
| `gsm-watchdog.service` + `gsm-watchdog.timer` | Každé 2 minuty kontroluje stav modemu; při zaseknutí restartuje `ModemManager`, při přetrvávajícím problému restartuje RPi. Podrobně viz [Modem – hardware a diagnostika](modem-diagnostika.md#watchdog). |

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

## 5) Ověření

```bash
mmcli -m 0                              # modem by měl mít state: registered
docker compose --profile rpi ps         # web, db, pgadmin, gsm_worker běží
docker compose --profile rpi logs --tail=20 gsm_worker
systemctl list-timers gsm-watchdog.timer
systemctl is-enabled calyx-usb-serial.service gsm-gate-compose.service gsm-watchdog.timer
```

### Volitelně: pravidelné zálohování dat

Systémové služby výše zajistí, že brána po havárii sama naběhne s **prázdnou databází** (kód je z gitu, data ne). Pro obnovu dat (čísla, skupiny, pravidla, objekty, nastavení) po výměně SD karty/havárii disku je potřeba záloha dat – viz [Funkcionalita – Zálohování](funkcionalita.md#13-zálohování) a stránka „Zálohování“ v appce (jen pro superusera).

Automatické denní zálohy do `django_app/backups/` (odtud si je synchronizuj tam, kam potřebuješ – rsync/rclone/cloud sync):

```bash
sudo cp scripts/gsm-backup.service scripts/gsm-backup.timer /etc/systemd/system/
sudo cp scripts/gsm_backup.sh /usr/local/bin/gsm_backup.sh
sudo chmod +x /usr/local/bin/gsm_backup.sh

sudo systemctl daemon-reload
sudo systemctl enable --now gsm-backup.timer
```

### Volitelně: automatická retence starých dat

Doplněk k zálohám výše – maže staré `IncomingEventLog`/`OutgoingAction`/`SignalReading` podle stáří (`RETENTION_DAYS_LOGS`/`RETENTION_DAYS_SIGNAL_HISTORY` v `.env`, výchozí 90/30 dní), ne podle kategorie. Viz [Funkcionalita – Zálohování](funkcionalita.md#13-zálohování).

```bash
sudo cp scripts/gsm-prune.service scripts/gsm-prune.timer /etc/systemd/system/
sudo cp scripts/gsm_prune.sh /usr/local/bin/gsm_prune.sh
sudo chmod +x /usr/local/bin/gsm_prune.sh

sudo systemctl daemon-reload
sudo systemctl enable --now gsm-prune.timer
```

### Obnova dat ze zálohy

Po čerstvém nasazení (kroky 1–4 výše, prázdná databáze):

1. Přihlas se jako superuser.
2. V menu „Zálohování“ nahraj poslední JSON export (tlačítko „Importovat zálohu“).
3. Import běží v transakci – pokud selže, žádná data se nezmění.

Import je bezpečný jen na prázdnou/čerstvou databázi. Na databázi s existujícími daty může přepsat záznamy se stejným ID – před importem na běžící bránu radši ověř obsah souboru.

## Běžná aktualizace kódu (ne po výměně SD karty/RPi)

Systémové služby z kroku 3 se instalují **jen jednou** na dané fyzické zařízení – nejsou to soubory, které by se aplikovaly samy při `git pull`. Pro běžný update kódu na už nastaveném zařízení stačí:

```bash
git pull
docker compose up -d --build
docker compose --profile rpi up -d --build gsm_worker
```

Pokud update mění i `scripts/*.service`/`*.timer`, je potřeba je znovu zkopírovat a `daemon-reload` (viz krok 3).

## Co dělat, když něco spadne

- **Kontejner spadne** (`web`, `db`, `pgadmin`, `gsm_worker`) → Docker ho sám restartuje (`restart: unless-stopped`/`always` v `docker-compose.yml`), bez zásahu.
- **RPi se restartuje** (výpadek proudu, watchdog reboot, ruční restart) → `gsm-gate-compose.service` po startu Dockeru postaví celý stack znovu, `calyx-usb-serial.service` znovu zaregistruje modem.
- **Modem se zasekne, ale RPi běží dál** → `gsm-watchdog.timer` to detekuje do 2 minut a eskaluje (restart ModemManageru → restart RPi).
- **Někdo omylem udělá `docker compose down`** → při dalším startu (nebo příštím rebootu) `gsm-gate-compose.service` stack znovu postaví.
- **Kontejner se zasekne, ale nespadne** (proces běží, ale nic neděje) → `docker ps`/`docker compose ps` u `web`/`gsm_worker` ukáže `unhealthy` (Docker healthcheck, viz [Architektura](architektura.md#docker-healthchecky)). Restart ručně: `docker compose restart web` / `docker compose --profile rpi restart gsm_worker`.

Podrobnou diagnostiku konkrétních chybových stavů (SMS nechodí, modem neodpovídá, `mmcli` chyby) řeší [Modem – hardware a diagnostika](modem-diagnostika.md).
