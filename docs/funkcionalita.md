# Funkcionalita

## 1) Účty a přístup

- registrace, přihlášení, odhlášení,
- práce v uživatelském kontextu,
- řízení viditelnosti a CRUD akcí přes oprávnění.

## 2) Dashboard

Dashboard je centrální pracovní plocha. Obsahuje:

- souhrn metrik (počty čísel, skupin, pravidel, logů, objektů),
- rychlé akce na klíčové moduly,
- tabulky čísel a skupin s CRUD tlačítky,
- přehled objektů zařízení.

## 3) Telefonní čísla

### Co lze dělat

- založit číslo,
- upravit číslo,
- smazat číslo,
- otevřít detail čísla,
- přiřadit číslo do jedné či více skupin,
- aktivovat/deaktivovat číslo.

### Detail čísla

Detail typicky zahrnuje:

- metadata čísla,
- přiřazené skupiny,
- související pravidla,
- související příchozí/odchozí záznamy.

## 4) Skupiny

### Co lze dělat

- založit skupinu,
- upravit skupinu,
- smazat skupinu,
- otevřít detail skupiny,
- spravovat členy skupiny (telefonní čísla).

### Vlastnictví a sdílení

- každá skupina má vlastníka,
- skupina může být sdílená více uživatelům,
- vlastník je zároveň udržován i ve vazbě uživatelů skupiny.

## 5) Hromadné úpravy čísel

Hromadná stránka podporuje kombinaci vstupů:

- ručně zadaný seznam,
- CSV import,
- výběr existujících čísel.

### Operace

- přidat čísla do skupin,
- odebrat čísla ze skupin,
- nahradit skupiny,
- nastavit čísla jako aktivní,
- nastavit čísla jako neaktivní.

Výstupem je souhrn zpracování (kolik položek změněno, přeskočeno, vytvořeno).

## 6) Automatizační pravidla

### Parametry pravidla

- název, popis, aktivita,
- priorita (pořadí vyhodnocování),
- typ události (SMS/CALL/API/kombinace/bezpečnostní událost – viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md)),
- podmínka (ANY/EXACT/GROUP),
- zdrojové číslo/skupiny/objekty,
- reakce (`IGNORE`, `NOTIFY_NUM`, `NOTIFY_GRP`, `FORWARD`),
- notifikační kanály a volitelný vlastní text,
- příznak zprávy (`message_flag`) pro jemné filtrování.

### Životní cyklus

1. vytvoření pravidla,
2. úprava parametrů,
3. simulace vstupní události,
4. audit přes logy událostí a odchozí akce,
5. případné smazání.

## 7) Simulátor příchozí události

Simulátor slouží k bezpečnému testování pravidel bez reálného provozu.

Umožňuje:

- zadat typ události,
- zadat zdrojové číslo,
- zadat text zprávy,
- okamžitě vidět, kolik pravidel se matchnulo,
- zkontrolovat vygenerované odchozí akce.

## 8) Log událostí

- seznam příchozích událostí,
- detail události,
- vazba na pravidla/akce,
- auditní stopa pro troubleshooting.

## 9) Odchozí akce

- fronta akcí čekajících na zpracování,
- stavové informace (`PENDING`, `DONE`, `FAILED` apod.),
- čas zpracování a diagnostický detail.

## 10) Objekty zařízení

Objekty reprezentují zařízení/zdroje událostí.

### Co lze dělat

- založit objekt,
- upravit objekt,
- smazat objekt,
- otevřít detail objektu,
- vygenerovat/regenerovat API token,
- exportovat integrační konfiguraci.

## 11) Gateway status a konfigurace

### Stav

- technický přehled zdraví brány a návazných částí,
- **síla signálu** (v procentech, 0–100 %) – zapisuje ji worker při každém cyklu, na stránce se sama aktualizuje bez nutnosti obnovit stránku (live polling přes JS každých 20 s), stejný badge je vidět i v hlavičce webu.

### Konfigurace

Zúženo jen na to, co appka reálně používá (ModemManager/mmcli si port, rychlost, APN i síťový režim spravuje sám – viz [Modem – hardware a diagnostika](modem-diagnostika.md)):

- **SIM PIN** – vyplní se, jen pokud SIM kartu chrání PIN; worker ho použije k automatickému odemčení modemu při připojení.
- **Vyžadovat doručenky** – při odeslání SMS požádá síť o potvrzení doručení příjemci (`delivery-report-request` v PDU).
- **Povolit příchozí SMS** – řídí, jestli se pro uživatele vůbec vyhodnocují pravidla na příchozí SMS.
- **Webhook URL** – cíl pro Teams notifikace.
