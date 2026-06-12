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

## 3) Chybějící DB sloupce po update

### Příznak

`ProgrammingError` typu „column ... does not exist“.

### Řešení

```bash
docker compose exec web python manage.py showmigrations dashboard
docker compose exec web python manage.py migrate
```

## 4) Worker neodesílá SMS

### Kontrola

- běží container `gsm_worker`?
- je nastaveno `GSM_ENABLED=true`?
- je správně mapovaný modem port?
- odpovídá `GSM_MODEM_BAUD` hardware konfiguraci?

### Diagnostika

```bash
docker compose run --rm web python manage.py gsm_gateway_worker --once
```

## 5) Objekt API neposílá události

### Kontrola

- platný token a aktivní credential,
- správný endpoint,
- správný JSON payload,
- dostupnost serveru ze sítě zařízení.

## 6) Build dokumentace

Spuštění lokálně přes samostatný compose:

```bash
docker compose -f docker-compose.mkdocs.yml up -d
```

Pokud build selže, zkontrolovat syntax nav v `mkdocs.yml` a existenci všech markdown souborů.
