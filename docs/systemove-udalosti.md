# Systémové a provozní události brány

!!! info "Co to je"
    Běžná pravidla reagují na SMS/volání/API z telefonních čísel. **Systémová událost** je jiný druh spouštěče – reaguje na stav samotné brány (Raspberry Pi a aplikace), ne na to, co přišlo z nějakého čísla. Typické použití: *„pošli mi SMS, když se RPi restartuje"* nebo *„upozorni mě, když dochází místo na disku"*.

Žádná nová notifikační cesta se kvůli tomu nestavěla – appka jen přidala nový **zdroj** událostí do existujícího systému pravidel ([Automatizační pravidla](funkcionalita.md#6-automatizační-pravidla)). Vznikne `IncomingEventLog` s typem `SYSTEM` a vyhodnotí se běžná pravidla úplně stejně, jako by šlo o SMS.

## Kdo dostává upozornění

!!! warning "Důležitý rozdíl od ostatních pravidel"
    Systémové události se netýkají dat jednoho uživatele, ale provozu **celé brány**. Appka proto vytvoří jednu kopii události pro **každého admina/superusera** zvlášť (viz [Role a oprávnění](role-a-opravneni.md#tři-úrovně-práv-super-admin-admin-user)) – ne jen pro vlastníka pravidla, jako je to u SMS/API pravidel. Běžní uživatelé (role *Jen čtení*/*Operátor*) tyhle notifikace nedostávají, i kdyby si pravidlo sami založili.

## Jak si nastavit upozornění

1. **Pravidla → Nové pravidlo.**
2. **Typ události** = *Systémová/provozní událost brány*.
3. V nabídce, která se objeví, **zaškrtni jeden nebo víc příznaků** z katalogu níže – objeví se jako checkboxy, appka si je sama doplní do pole „Příznak v SMS" oddělené čárkou a zapne „Filtrovat podle příznaku v SMS".
4. **Podmínku na zdroj** nastav na *Jakékoliv číslo* – u systémových událostí zdroj není telefonní číslo, filtrace jde čistě přes zaškrtnuté příznaky.
5. Vyber reakci (typicky *Poslat informaci na cílová čísla/skupiny*), kanál (SMS/e-mail/Teams) a případně vlastní text zprávy.

!!! tip "Víc příznaků v jednom pravidle"
    Zaškrtnutí víc checkboxů znamená shodu **ANY** – pravidlo se spustí, nastane-li **kterýkoliv** ze zvolených příznaků. Nemusíš tedy vytvářet samostatné pravidlo pro každý příznak zvlášť, pokud má reagovat stejně (stejný kanál, stejná cílová čísla).

## Katalog příznaků

### Hardware a restart

| Příznak | Kdy se vyšle |
|---|---|
| `#REBOOT` | Raspberry Pi se restartovalo – nejde o pouhý restart kontejneru, appka pozná reálný restart hostitele podle jeho `/proc/uptime`. |

### Přihlášení a bezpečnost

| Příznak | Kdy se vyšle |
|---|---|
| `#LOGIN_ADMIN` | Přihlásil se uživatel s rolí admin/superuser. |
| `#LOGIN_ATTACK` | Překročen limit neúspěšných pokusů o přihlášení (10 za 5 minut, sledováno podle IP+jména) – stejný zámek jako v [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md#4-rate-limit-na-api-ingest-a-zámek-proti-brute-force-na-přihlášení), teď navíc pošle notifikaci. |

### Zdraví brány (sebediagnostika)

Tahle čtveřice přímo vychází z kontrol na stránce [Sebediagnostika](funkcionalita.md#14-sebediagnostika) – appka jen tytéž kontroly spouští automaticky na pozadí a při změně stavu pošle notifikaci, abys nemusel stránku sám chodit kontrolovat.

| Příznak | Kdy se vyšle |
|---|---|
| `#DISK_LOW` | Volné místo na disku kleslo pod práh (Varování < 1000 MB, Chyba < 300 MB) – nebo se zase uvolnilo. |
| `#BACKUP_OLD` | Poslední záloha v `backups/` je starší než 7 dní (nebo žádná neexistuje) – nebo se objevila nová čerstvá. |
| `#CONFIG_WARN` | Některá z bezpečnostních kontrol konfigurace selhala nebo se zotavila – `DEBUG=True` v produkci, slabý/výchozí `SECRET_KEY`, nebo `ALLOWED_HOSTS` obsahuje `*`. |
| `#QUEUE_PROBLEM` | Fronta odchozích akcí má zaseknuté čekající položky (déle než 10 min) nebo hodně selhání za posledních 24 h (přes všechny účty najednou) – nebo se fronta zase vyčistila. |

## Zhoršení vs. obnovení

U čtveřice v sekci **Zdraví brány** appka vyšle notifikaci oběma směry – nejen když problém nastane, ale i když zmizí. V textu zprávy je proto vždy napsáno **„Zhoršení"** nebo **„Obnoveno"**, aby bylo hned jasné, o který případ jde (hodí se to ocenit zejména ve vlastním textu pravidla, kde si můžeš podle toho rozlišit formulaci).

Notifikace se posílá jen při **změně** stavu – pokud problém jen dál trvá (např. disk je stále málo volný i druhý den), appka to nehlásí znovu při každém cyklu, jen jednou při první detekci.

## Mimo rozsah (zatím)

Upozornění na podpětí/napájení (`vcgencmd`/hwmon) ve výčtu záměrně chybí – vyžaduje nejdřív ověřit, co je z `gsm_worker` kontejneru reálně dostupné bez úprav `docker-compose.yml`.

## Technické pozadí

!!! note "Pro vývojáře/údržbu – není potřeba pro běžné používání appky"

    - Vstupní bod je `dashboard/services/rules_engine.py` → `fire_system_health_event(flag, message, source_number='')` – vytvoří `IncomingEventLog(event_type='SYSTEM')` pro každého admina/superusera a zavolá `_evaluate_rules()` úplně stejně jako u SMS.
    - `check_reboot()` a `check_periodic_health()` (`dashboard/services/system_health.py`) běží jednou za cyklus `gsm_worker`, mimo try/except na modem – ať detekce funguje i při výpadku modemu.
    - Poslední známý stav restartu i jednotlivých kontrol zdraví appka pamatuje v modelu `SystemState` (jeden globální řádek, ne per uživatel) – jen proto, aby šlo poznat **změnu** stavu a při prvním běhu po nasazení nevznikla falešná notifikace.
    - `#CONFIG_WARN` je sdílený příznak pro tři různé kontroly (`selftest.check_debug_mode`/`check_secret_key`/`check_allowed_hosts`) – nejde o duplicitu, jde o společnou kategorii "problém s bezpečnostní konfigurací".
    - V pravidle (`AutomationRule.message_flag`) jde zadat víc příznaků oddělených čárkou – `rule_matches_event()` je porovná jako shodu ANY (stačí, aby text zprávy obsahoval alespoň jeden z nich).
