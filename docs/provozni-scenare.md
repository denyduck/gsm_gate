# Provozní scénáře

## 1) Onboarding nového zákazníka/provozu

1. Založení uživatelského účtu/role.
2. Nastavení `GatewaySettings`.
3. Založení skupin příjemců.
4. Import a validace telefonních čísel.
5. Vytvoření prvních pravidel.
6. Ověření přes simulátor.
7. Spuštění workeru a pilotní provoz.

## 2) Denní provoz

- sledování dashboardu,
- kontrola logů událostí,
- kontrola stavu odchozích akcí,
- jemné ladění pravidel podle reálných dat.

## 3) Přidání nového objektu zařízení

1. Vytvořit objekt zařízení.
2. Vygenerovat API token.
3. Nasadit token do zařízení (nebo vygenerovat QR spouštěč, pokud zařízení bude spouštěno naskenováním, ne vlastním HTTP klientem).
4. Ověřit volání ještě před nasazením do terénu – tlačítko **Testovací volání** na detailu objektu odešle skutečný požadavek se skutečným tokenem a rovnou ukáže odpověď, bez nutnosti psát curl/Postman.
5. Ověřit vznik logu a navazující akce (Log událostí / detail objektu).

Podrobně: [API objektů zařízení](api-objekty-zarizeni.md).

## 4) Incident: neodesílají se akce

1. Mrkni na **Telemetrii** – kolik akcí je `PENDING`/`FAILED`, graf síly signálu a tabulka výpadků za posledních pár hodin často rovnou ukážou příčinu (výpadek signálu = worker se nemohl připojit).
2. Spusť **Sebediagnostiku** – kategorie "Provoz" hlásí zaseknutou frontu (`PENDING` > 10 min) i stáří poslední kontroly signálu, s konkrétním doporučením.
3. Otevři odchozí akce a zkontroluj status a `execution_detail` u neúspěšných akcí.
4. Ověř dostupnost modemu (`GSM_ENABLED`, `mmcli -m 0` – stav `registered`).
5. Ověř běh workeru (`gsm_worker` container) – `docker ps` teď ukazuje i `healthy`/`unhealthy`, ne jen `Up`.
6. Otestuj jednorázové spuštění workeru.

Podrobný postup: [Modem – hardware a diagnostika](modem-diagnostika.md#postup-při-diagnostice-sms-nechodí-checklist).

## 5) Změna pravidel bez výpadku

- pravidla měnit ve stavu aktivní aplikace,
- změny ověřit simulací,
- u kritických pravidel držet audit změn (kdo/ kdy / co).

## 6) Doporučení pro produkci

Co už appka řeší sama (stačí zapnout/nastavit):

- **pravidelné zálohy** – volitelný `gsm-backup.timer` (denně), ruční export/import na stránce Zálohování,
- **retence starých dat** – volitelný `gsm-prune.timer` (denně), maže staré logy a historii signálu,
- **monitoring** – Docker healthchecky na `web`/`gsm_worker`, stránky Sebediagnostika a Telemetrie,
- **rate limiting a brute-force ochrana** – API ingest endpoint i přihlášení mají vestavěný limit, viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md),
- **rotace API tokenů** – tlačítko "Regenerovat API klíč" na detailu objektu.

Co zůstává na tobě:

- **TLS/HTTPS** – appka běží záměrně bez reverse proxy přímo na gunicornu (viz [Architektura](architektura.md#web-server)), tedy bez TLS. V pořádku na důvěryhodné LAN, ne pro vystavení na veřejný internet – tam by bylo potřeba přidat reverse proxy s TLS terminací (mimo současný rozsah projektu).
- **rotace hesel uživatelů** – appka nemá vynucenou expiraci hesel, jen zámek proti brute-force.
- oddělené prostředí DEV/UAT/PROD, pokud provoz roste za rámec jedné RPi.
