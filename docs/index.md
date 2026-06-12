# GSM Gate – kompletní dokumentace

Tato dokumentace popisuje kompletní funkcionalitu systému **GSM Gate**: webovou správu, pravidla automatizace, auditní logování i napojení na modem **SIM7000** přes oddělený worker.

## Co systém řeší

- správu telefonních čísel a skupin příjemců,
- řízení přístupů a sdílení dat mezi uživateli,
- automatické reakce na příchozí události (SMS/volání/API),
- tvorbu a odbavení odchozích akcí (SMS/notifikace/předání),
- správu objektů zařízení s API tokeny,
- centrální konfiguraci GSM brány,
- provoz přes Docker Compose.

## Rychlé spuštění dokumentace

```bash
docker compose -f docker-compose.mkdocs.yml up -d
```

Dokumentace poběží na adrese: <http://localhost:8010>

## Rychlé spuštění aplikace

```bash
docker compose up -d --build
```

Volitelně worker profil pro RPi/SIM7000:

```bash
docker compose --profile rpi up -d --build
```

## Obsah

- **Architektura** – komponenty a datové toky.
- **Funkcionalita** – detailní popis všech modulů UI.
- **Role a oprávnění** – kdo co může dělat.
- **API objektů zařízení** – ingest endpoint a autentizace tokenem.
- **Provozní scénáře** – denní provoz, onboarding, incidenty.
- **Troubleshooting** – nejčastější problémy a řešení.
