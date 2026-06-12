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
3. Nasadit token do zařízení.
4. Odeslat testovací API událost.
5. Ověřit vznik logu a navazující akce.

## 4) Incident: neodesílají se akce

1. Otevřít odchozí akce a zkontrolovat status.
2. Ověřit dostupnost modemu (`GSM_ENABLED`, port, baud).
3. Ověřit běh workeru (`gsm_worker` container).
4. Zkontrolovat `execution_detail` u neúspěšných akcí.
5. Otestovat jednorázové spuštění workeru.

## 5) Změna pravidel bez výpadku

- pravidla měnit ve stavu aktivní aplikace,
- změny ověřit simulací,
- u kritických pravidel držet audit změn (kdo/ kdy / co).

## 6) Doporučení pro produkci

- pravidelné DB zálohy,
- monitoring kontejnerů,
- oddělené prostředí DEV/UAT/PROD,
- TLS terminace na reverse proxy,
- rotace API tokenů a hesel.
