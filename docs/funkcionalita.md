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
- typ události – `SMS`, `API`, `SMS_API` (kombinace obou) nebo `SECURITY` (bezpečnostní událost, viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md)). Dřív existovala i hodnota `ANY` se stejným popiskem jako `SMS_API` a identickým chováním – čistá duplicita v rozbalovacím seznamu. Migrace `0046` existující pravidla s `ANY` převedla na `SMS_API` a hodnotu `ANY` z voleb odstranila,
- podmínka (ANY/EXACT/GROUP),
- zdrojové číslo/skupiny/objekty,
- reakce (`IGNORE`, `NOTIFY_NUM`, `NOTIFY_GRP`, `FORWARD`),
- notifikační kanály a volitelný vlastní text,
- příznak zprávy (`message_flag`) pro jemné filtrování,
- **informační SMS při prvním kontaktu** (`notify_first_contact` + `first_contact_timing` + `first_contact_message`) – u akcí `NOTIFY_NUM`/`NOTIFY_GRP`/`FORWARD` zařadí navíc jednorázovou SMS s vysvětlením (např. „byl jsi zařazen do automatizace X, důvod: ...“) danému cílovému číslu. Jestli číslo už bylo tímto pravidlem někdy kontaktováno, se pozná podle historie `OutgoingAction` (`rule` + `target_number`) – bez vyplněného textu se použije výchozí zpráva s názvem pravidla. `first_contact_timing` určuje KDY se odešle:
    - `ON_TRIGGER` (výchozí) – až pravidlo poprvé reálně zareaguje na událost a osloví dané číslo.
    - `ON_SAVE` – hned po vytvoření/uložení pravidla, všem aktuálně nastaveným cílovým číslům najednou (bez čekání na skutečnou událost). Vytvoří se k tomu syntetický `IncomingEventLog` s `event_type='SYSTEM'`, protože `OutgoingAction.event_log` je povinné pole. Opakované uložení pravidla neobtěžuje už kontaktovaná čísla znovu – dedup je stejný jako u `ON_TRIGGER`, jen nově přidaná cílová čísla dostanou SMS.

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

## 9b) Telemetrie

Stránka „Telemetrie" (vyžaduje `dashboard.view_outgoingaction`, stejné oprávnění jako Odchozí akce) shrnuje provoz brány do grafů (Chart.js):

- souhrnné počty – celkem SMS akcí, odesláno/selhalo/čeká, celkem příchozích událostí,
- graf odeslaných SMS za posledních 30 dní,
- podle pravidla – které pravidlo odeslalo kolik SMS,
- podle skupiny – kolik SMS šlo číslům v dané skupině (číslo ve víc skupinách se počítá do každé z nich),
- top cílová čísla – kam se posílá nejvíc SMS,
- top zdrojová čísla – odkud přichází nejvíc událostí,
- **přístroj a modem** – aktuální volné místo na disku (host, přes bind mount), graf síly signálu za posledních 24 h a tabulka posledních výpadků.

Počítají se jen skutečně odeslané SMS (`status='SENT'`), ne čekající/selhané – to je vidět zvlášť v souhrnných počtech. Data jsou scoped na přihlášeného uživatele (`owner`), stejně jako zbytek appky.

### Historie síly signálu

`gsm_worker` zapisuje `SignalReading` při každém cyklu (`dashboard/services/gsm_worker.py`), ale s throttlingem – max. jeden záznam za 5 minut, kromě přechodů výpadek/obnovení, které se zaznamenají hned. Bez throttlingu by při výchozím 10s intervalu workeru tabulka rostla o tisíce řádků denně.

Graf síly signálu má přepínač období (podobně jako u cenových grafů) – 1 h / 10 h / 24 h / 3 dny / 7 dní / Max (celá dostupná historie). Přepnutí nedělá reload stránky – JS si data pro nové období natáhne přes `GET /dashboard/api/telemetrie/signal/?range=...` (`views.telemetry_signal_series_api`) a graf jen překreslí. Platné hodnoty `range` a výchozí období jsou v `telemetry_service.SIGNAL_RANGE_HOURS`/`SIGNAL_RANGE_DEFAULT` – jedno místo pro server i šablonu (tlačítka se generují z tohohle slovníku).

`quality=None` znamená výpadek (modem nebyl v daném cyklu dostupný, typicky když `connect()` selže dřív, než se stihne zpracovat fronta) – v grafu se zobrazí jako mezera, v tabulce výpadků jako souvislý úsek. Ruční smazání historie jde přes „Reset dat" na stránce Zálohování (kategorie „Historie síly signálu").

**Známé omezení:** teplota CPU a vytížení samotné Raspberry Pi tady nejsou – `web`/`gsm_worker` kontejnery nemají mount hostitelských `/proc`/`/sys` cest. Šlo by doplnit přidáním bind mountu do `docker-compose.yml`, ale je to vědomě mimo rozsah, dokud o to někdo nepožádá (další přístup kontejneru k hostiteli navíc).

## 10) Objekty zařízení

Objekty reprezentují zařízení/zdroje událostí.

### Co lze dělat

- založit objekt,
- upravit objekt,
- smazat objekt,
- otevřít detail objektu,
- vygenerovat/regenerovat API token,
- exportovat integrační konfiguraci,
- odeslat **testovací volání** – skutečný HTTP požadavek na `api/device-events/ingest/` se skutečným tokenem objektu, výsledek (HTTP stav + odpověď) se zobrazí přímo v administraci,
- vygenerovat **QR spouštěč** – QR kód s odkazem obsahujícím API token objektu; naskenování telefonem (bez přihlášení) odešle požadavek a vyhodnotí pravidla stejně jako API volání. Text zprávy lze přizpůsobit parametrem `?msg=`. Regenerace API klíče odkaz/QR kód zneplatní.

Odkaz/QR kód spouštěče funguje jako sdílené tajemství (token je součástí URL) – je potřeba s ním zacházet jako s heslem, protože kdokoliv s odkazem může objekt spustit.

### Sdílení objektů (od koho pravidlo může vybírat)

`DeviceObject` má (stejně jako `PhoneNumber`/`Group`) pole `users` pro sdílení – přidávat/odebírat sdílené uživatele jde jen přes Django Admin (`filter_horizontal`), stejně jako u čísel a skupin, ne přímo v appce.

Formulář pravidla (pole „Zdrojové objekty") dřív nabízel jen objekty, které uživatel **vlastní** (`owner`) – objekty sdílené (`users`) mu chyběly, i když je mohl reálně používat v jiných částech appky. Teď se v dropdownu zobrazují objekty vlastněné NEBO sdílené s přihlášeným uživatelem (`Q(owner=user) | Q(users=user)`), stejně jako už fungovalo pro cílová čísla a skupiny.

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

## 12) Zálohování

Stránka „Zálohování“ (jen pro superusera, viz menu) používá Django `dumpdata`/`loaddata` – žádnou vlastní serializaci.

### Export

- **Export všech dat** – čísla, skupiny, objekty, API klíče, pravidla, blokovaná čísla, bezpečnostní nastavení, gateway nastavení, historie událostí/akcí + uživatelské účty (kvůli vazbám vlastníků).
- **Export jen nastavení** – jen `GatewaySettings` + `SecurityRule`, bez historie a ostatních objektů.

Uživatelské účty se v exportu ukládají přes tzv. natural key (uživatelské jméno, ne interní ID) – import tak funguje i na instanci, kde má stejný admin jiné interní ID.

### Import (obnova)

- Nahrání JSON exportu zpět do databáze, transakčně (při chybě se nic nezmění).
- Určeno hlavně pro obnovu na čerstvě nasazené bráně (prázdná databáze) – na existující data může přepsat záznamy se stejným ID.

### Plánované zálohy

Management příkaz `python manage.py export_backup --kind data|settings --output-dir <cesta>` dělá to samé jako tlačítko v appce, ale zapisuje timestamped soubor na disk – vhodné pro systemd timer (`scripts/gsm-backup.service` + `.timer`, viz [Nasazení a obnova](nasazeni-a-obnova.md)). Výstupní adresář je uvnitř bind-mountovaného `django_app/`, takže soubory jsou vidět přímo na hostu.

Zálohy obsahují citlivá data (SIM PIN v čistém textu, API tokeny objektů) – je potřeba je ukládat jen na bezpečné místo.

### Reset dat

Na stejné stránce lze data i nevratně smazat, po kategoriích nebo najednou:

- **Po kategoriích** – telefonní čísla, skupiny, objekty zařízení (i s API klíči), automatizační pravidla (jen nechráněná – `is_protected` pravidla se nedají smazat, viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md)), blokovaná čísla, historie událostí a odchozích akcí.
- **Kompletní reset brány** – smaže všechno výše najednou a navíc vrátí `GatewaySettings` (PIN, doručenky, webhook) a `SecurityRule` (limity proti zahlcení) na výchozí hodnoty. Chráněná systémová pravidla zůstávají beze změny.

Každá akce vyžaduje potvrzení – napsat do pole přesně text `SMAZAT` – plus JS `confirm()` dialog. Mazání je omezené na data vlastněná přihlášeným uživatelem (stejně jako zbytek appky), ne globálně napříč všemi účty.

## 13) Sebediagnostika

Stránka „Sebediagnostika" (jen pro superusera) spustí sadu kontrol (`dashboard/services/selftest.py`) a u každé vrátí stav (OK/Varování/Chyba), zprávu a konkrétní doporučení k nápravě:

- **Zabezpečení** – DEBUG režim, SECRET_KEY, ALLOWED_HOSTS (stejná trojice co [Nasazení a obnova](nasazeni-a-obnova.md)), stav bezpečnostního pravidla proti zahlcení.
- **Provoz** – databáze, static soubory (WhiteNoise manifest), volné místo na disku, nastavení brány, worker/signál modemu, fronta odchozích akcí (zaseknuté `PENDING` > 10 min nebo nedávno selhané `FAILED` za 24 h).
- **Data a zálohy** – stáří posledního exportu v `backups/`.

Signál modemu se testuje nepřímo (přes stáří `last_signal_checked_at`, který zapisuje worker) – přímé volání `mmcli` z `web` kontejneru není možné, ten nemá mount `/run/dbus`.

### Výsledky a historie

- Výsledky jsou seskupené po kategoriích; kategorie, kde je vše OK, se zobrazí sbalená, kategorie s varováním/chybou zůstane rozbalená – ať je hned vidět, co potřebuje pozornost.
- Ke každé kontrole, kde existuje relevantní stránka v dokumentaci, je odkaz „📖 Dokumentace" (viz `MKDOCS_BASE_URL` níže).
- Každé spuštění se uloží jako `SelfTestRun` s počty OK/Varování/Chyba. Hlavní stránka ukazuje poslední běh v plném detailu + kompaktní historii (posledních 20 běhů); kliknutím na „Detail" se zobrazí libovolný starší běh ve stejném seskupeném formátu.
- Kontroly zapisují i do standardního Python logu (`docker compose logs web`) – varování/chyby na úrovni WARNING/ERROR, souhrn na INFO.

## 14) Odkazy na dokumentaci v appce

Proměnná `MKDOCS_BASE_URL` (`.env`, výchozí `http://10.10.10.234:8010`) nastavuje adresu běžícího MkDocs webu. Používá se:

- v hlavičce appky (odkaz „Dokumentace", vidí ho každý přihlášený uživatel),
- u doporučení v Sebediagnostice,
- na stránkách Zálohování, Stav brány a Pravidla (odkaz na relevantní stránku dokumentace).

Pokud proměnná není nastavená, odkazy se v appce jednoduše nezobrazí (žádná rozbitá URL).
