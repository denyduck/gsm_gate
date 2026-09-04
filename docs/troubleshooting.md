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

## 4) Chybějící DB sloupce po update

### Příznak

`ProgrammingError` typu „column ... does not exist“.

### Řešení

```bash
docker compose exec web python manage.py showmigrations dashboard
docker compose exec web python manage.py migrate
```

## 5) Worker neodesílá SMS

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

## 6) Objekt API neposílá události

### Kontrola

- platný token a aktivní credential,
- správný endpoint,
- správný JSON payload,
- dostupnost serveru ze sítě zařízení.

## 7) Build dokumentace

Spuštění lokálně přes samostatný compose:

```bash
docker compose -f docker-compose.mkdocs.yml up -d
```

Pokud build selže, zkontrolovat syntax nav v `mkdocs.yml` a existenci všech markdown souborů.
