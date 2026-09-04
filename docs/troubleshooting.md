# Troubleshooting

## 1) Mizející tlačítka CRUD

### Příznak

Na dashboardu nebo v seznamech nevidíte `Editovat`/`Smazat`.

### Kontrola

- má uživatel potřebná oprávnění?
- je objekt viditelný v jeho datovém rozsahu?
- předává view všechny context proměnné pro podmínky v šablonách?

### Řešení

- ověřit oprávnění v DB,
- ověřit vazby owner/users,
- zkontrolovat context klíče (`can_change_*`, `editable_*_ids`, `deletable_*_ids`).

## 2) `DisallowedHost: testserver`

### Příčina

Django test client používá host `testserver`, který nemusí být v `ALLOWED_HOSTS`.

### Řešení

- pro smoke test použít `Client(HTTP_HOST='localhost')`,
- případně přidat test host do `ALLOWED_HOSTS` pro testovací prostředí.

## 3) `DisallowedHost` při otevření brány v prohlížeči

### Příčina

Od zavedení `.env` (`ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`, viz [Nasazení a obnova](nasazeni-a-obnova.md#3-konfigurace-prostředí-env)) appka odmítne požadavek na jakoukoliv IP/hostname, který v `ALLOWED_HOSTS` není – typicky po změně IP adresy RPi (DHCP) nebo po čerstvém nasazení bez `.env`.

### Řešení

```bash
grep ALLOWED_HOSTS .env
```

Uprav `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` v `.env` na aktuální IP/hostname a restartuj:

```bash
docker compose up -d --build web
```

## 4) `Server Error (500)` a `docker compose logs` neukazuje nic

### Příčina

Django defaultně posílá chyby do konzole **jen když `DEBUG=True`** (vestavěný `console` handler má filtr `require_debug_true`). Appka má `DEBUG=False` jako bezpečný default, takže bez explicitní `LOGGING` konfigurace (`gsm_gate/settings.py`) by tracebacky mizely do prázdna – appka to má už vyřešené, ale je dobré vědět proč to funguje.

### Řešení

```bash
docker compose logs web --tail=80          # 500 chyby z requestů (django.request logger)
docker compose --profile rpi logs gsm_worker --tail=80   # chyby z workeru
```

Hledej `Traceback (most recent call last):` – přesný řádek a výjimka jsou tam vždycky, i s `DEBUG=False`.

## 5) `429 Too Many Requests` / "Příliš mnoho neúspěšných pokusů"

### Příčina

Vestavěný rate limit (viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md#4-rate-limit-na-api-ingest-a-zámek-proti-brute-force-na-přihlášení)):

- **API ingest** (`api/device-events/ingest/`) – 20 neplatných pokusů (chybějící/špatný token) z jedné IP za 60 s.
- **Přihlášení** – 10 neúspěšných pokusů ze stejné dvojice IP+uživatelské jméno za 5 minut.

### Řešení

Počkej na vypršení okna (60 s / 5 min), nebo u API ingestu ověř token na detailu objektu (klidně přes tlačítko "Testovací volání" – validní token vrátí `200`/`201` a počítadlo se vynuluje).

## 6) Chybějící DB sloupce po update

### Příznak

`ProgrammingError` typu „column ... does not exist“.

### Řešení

```bash
docker compose exec web python manage.py showmigrations dashboard
docker compose exec web python manage.py migrate
```

## 7) Worker neodesílá SMS

### Kontrola

- běží container `gsm_worker`?
- je nastaveno `GSM_ENABLED=true`?
- vidí modem `ModemManager` na hostu (`mmcli -m 0`)?
- vidí kontejner `ModemManager` přes D-Bus (mount `/run/dbus`)?

### Diagnostika

```bash
docker compose --profile rpi run --rm gsm_worker python manage.py gsm_gateway_worker --once
```

Podrobný diagnostický postup krok za krokem (včetně `mmcli` příkazů a watchdogu) viz [Modem – hardware a diagnostika](modem-diagnostika.md).

## 8) Objekt API neposílá události

### Kontrola

- platný token a aktivní credential,
- správný endpoint,
- správný JSON payload – `event_type`/`source_number`/`message_body`, viz [API objektů zařízení](api-objekty-zarizeni.md#skutečný-formát-payloadu),
- appka to neodmítá s `429` (viz bod 5 výše),
- dostupnost serveru ze sítě zařízení.

Nejrychlejší ověření: tlačítko **Testovací volání** na detailu objektu – pokud tohle funguje a reálné zařízení ne, problém je na straně zařízení/sítě, ne appky.

## 9) Build dokumentace

Spuštění lokálně přes samostatný compose:

```bash
docker compose -f docker-compose.mkdocs.yml up -d
```

Pokud build selže, zkontrolovat syntax nav v `mkdocs.yml` a existenci všech markdown souborů.
