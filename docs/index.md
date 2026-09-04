# GSM Gate – kompletní dokumentace

Tato dokumentace popisuje kompletní funkcionalitu systému **GSM Gate**: webovou správu, pravidla automatizace, auditní logování i napojení na GSM modem (aktuálně **Teltonika Calyx**, přes **ModemManager**) přes oddělený worker.

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

Volitelně worker profil pro RPi/modem:

```bash
docker compose --profile rpi up -d --build
```

## Obsah

- **Architektura** – komponenty a datové toky.
- **Funkcionalita** – detailní popis všech modulů UI.
- **Role a oprávnění** – kdo co může dělat.
- **Zabezpečení proti zahlcení SMS** – rate limiting, blokovaná čísla, testování.
- **API objektů zařízení** – ingest endpoint a autentizace tokenem.
- **Provozní scénáře** – denní provoz, onboarding, incidenty.
- **Modem – hardware a diagnostika** – aktuální hardware, softwarový stack (ModemManager/mmcli), diagnostické příkazy, watchdog.
- **Nasazení a obnova po havárii** – kompletní checklist pro novou RPi/výměnu SD karty, co `git pull` sám nezajistí.
- **Troubleshooting** – nejčastější problémy a řešení.

## Autor a verze

Aktuální verze: **1.0.0** (`APP_VERSION` v `django_app/gsm_gate/settings.py`, zobrazuje se i v patičce appky).

Autor: _doplnit_ (`APP_AUTHOR` v `django_app/gsm_gate/settings.py`).
