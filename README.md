# GSM Gate

Webová aplikace pro správu GSM brány běžící na Raspberry Pi 4 se shieldem Waveshare SIM7000.

## Aktuální stav

Implementováno:
- uživatelské účty (registrace, přihlášení, odhlášení),
- dashboard pro správu telefonních čísel,
- skupiny příjemců,
- sdílení přístupu přes uživatele ve skupinách a číslech,
- automatizační pravidla pro příchozí SMS/volání,
- log příchozích událostí,
- fronta odchozích akcí,
- worker pro zpracování modemu SIM7000 přes AT příkazy.

Poznámka:
- plné HW napojení vyžaduje spuštění `gsm_worker` služby s profilem `rpi` a dostupný modem port.

## Spuštění v Dockeru

```bash
docker-compose up -d --build
```

Aplikace:
- Django: http://localhost:8000
- pgAdmin: http://localhost:8080

## Spuštění workeru pro RPi4 + SIM7000

Worker běží v samostatném kontejneru `gsm_worker` (profil `rpi`) a používá device mapping na modem.

```bash
docker compose --profile rpi up -d --build
```

Klíčové proměnné prostředí:
- `GSM_ENABLED` (musí být `true`),
- `GSM_MODEM_PORT` (např. `/dev/ttyUSB0`),
- `GSM_MODEM_BAUD` (výchozí `115200`),
- `GSM_MODEM_TIMEOUT` (výchozí `3.0`),
- `GSM_WORKER_INTERVAL` (interval smyčky workeru),
- `GSM_MAX_ACTIONS_PER_CYCLE` (limit odeslání za cyklus).

Rychlý smoke test worker commandu:

```bash
docker compose run --rm web python manage.py gsm_gateway_worker --once
```

## Cíl projektu

Tento projekt je administrační a automatizační vrstva GSM brány. Web část řeší správu, pravidla a audit, zatímco oddělený worker zajišťuje komunikaci se SIM7000 modemem.

## Dokumentace v MkDocs

Projekt obsahuje samostatný compose soubor pro dokumentaci:

```bash
docker compose -f docker-compose.mkdocs.yml up -d
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
- `docs/troubleshooting.md`
