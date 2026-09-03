# Zabezpečení proti zahlcení SMS

Ochrana proti zneužití brány: zahlcení velkým počtem SMS/API událostí z jednoho čísla (spam, DoS, vyčerpání fronty/nákladů na odchozí SMS) a možnost ručně zablokovat konkrétní číslo.

## Jak to funguje

Ochrana je zabudovaná přímo v `dashboard/services/rules_engine.py`, ve funkci `process_incoming_event()` – běží při **každé** příchozí události (SMS i API), dřív než se vyhodnotí jakékoliv automatizační pravidlo.

### 1) Ruční blokace

Číslo na seznamu blokovaných čísel se u příchozí události rovnou zahodí – `IncomingEventLog` se pro audit vytvoří vždy, ale žádné pravidlo se nevyhodnotí a nevznikne žádná odchozí akce. **Platí vždy**, nezávisle na tom, jestli je níže popsané automatické pravidlo zapnuté – je to explicitní rozhodnutí administrátora.

Správa přes web: **Blokovaná čísla** v hlavním menu (vyžaduje oprávnění `dashboard.view_blockednumber`).

### 2) Automatická ochrana proti zahlcení (rate limiting) – pevné bezpečnostní pravidlo

Pokud jedno číslo (`source_number`) pošle za nastavené časové okno víc než povolený počet událostí, brána ho automaticky přidá na blokovaný seznam na dobu podle nastaveného "cooldownu". Po jeho uplynutí se číslo samo odblokuje (žádný manuální zásah není potřeba).

Toto je reprezentované modelem `SecurityRule` (`dashboard/models.py`) – **singleton na uživatele** (vytvoří se sám při první potřebě), zobrazený na stránce **Pravidla** jako pevná karta na začátku seznamu:

| Pole | Výchozí hodnota | Význam |
|---|---|---|
| `active` | zapnuto | Vypnutím se automatická detekce/blokace úplně zastaví (ruční blokace tím není dotčená) |
| `rate_limit_window_minutes` | 10 | Časové okno |
| `rate_limit_max_events` | 20 | Max. povolených událostí v okně |
| `auto_block_cooldown_minutes` | 30 | Jak dlouho trvá automatická blokace |

**Pravidlo nejde smazat** ani přidat další – v Django Adminu (`dashboard/admin.py`, `SecurityRuleAdmin`) je `has_add_permission`/`has_delete_permission` natvrdo `False`. Jde jen **zapnout/vypnout a upravit prahy**, a to výhradně přes Django Admin (`/admin/dashboard/securityrule/`), tedy jen jako **superuser** – v běžné appce se pravidlo pouze zobrazuje (stránka Pravidla), needá se odtud editovat.

### 3) Navázání vlastního pravidla na bezpečnostní událost

Když automatická ochrana číslo zablokuje, vygeneruje se navíc **samostatná událost typu `SECURITY`** (`IncomingEventLog.event_type = 'SECURITY'`) – nezávislá na původní zablokované události. Na tenhle typ události lze navázat běžné `AutomationRule` stejně jako na SMS/API (např. poslat e-mail/Teams notifikaci administrátorovi).

**Důležité:** `SECURITY` se **nezahrnuje** do `event_type='ANY'` (to zůstává jen SMS+API, jako doteď) – pravidlo musí mít `event_type` nastavený explicitně na `Bezpečnostní událost`, jinak se nespustí. Zabraňuje to tomu, aby se stávající "ANY" pravidla nečekaně spustila i na bezpečnostní události.

Vzorové pravidlo **"Výchozí: Upozornění na bezpečnostní blokaci"** (`event_type=SECURITY`, akce `NOTIFY_NUM`) se zakládá **líně** – funkcí `get_or_create_default_security_notification_rule()` v `rules_engine.py`, volanou z `rules_list_view()` při každé návštěvě stránky Pravidla. Není spoléháno jen na datovou migraci (`0039_...py`), protože ta prochází pouze uživatele existující v okamžiku spuštění migrace – na čerstvém nasazení, kde `migrate` proběhne dřív než `createsuperuser`, by tak pro jediný (první) účet pravidlo nikdy nevzniklo. Díky lazy `get_or_create` vznikne pravidlo pro **kohokoliv**, bez ohledu na to, kdy byl jeho účet založený. Nově vzniklé pravidlo je **vypnuté**, dokud si v jeho detailu nenastavíš cílová čísla/skupiny nebo e-mail/Teams kanál a ručně ho nezaktivuješ.

**Tohle pravidlo je chráněné** (`AutomationRule.is_protected = True`) – stejná logika jako u `SecurityRule`: na stránce Pravidla/v detailu se u něj místo tlačítek "Upravit"/"Smazat" zobrazí jen badge "Chráněné" a (pro superusera) odkaz do Django Adminu. `rule_edit`/`rule_delete` views navíc chráněné pravidlo odmítnou i při přímém volání URL (server-side kontrola, ne jen skryté tlačítko).

**Admin registrace:** `AutomationRule` je registrovaný v `gsm_gate/admin.py` (`AutomationRuleAdmin`), ne v `dashboard/admin.py` – tam je jen `SecurityRuleAdmin`. Ochrana `is_protected` proti smazání je doplněná přímo do existující `has_delete_permission()` v `gsm_gate/admin.py`. **Nezakládat druhou `@admin.register(AutomationRule)`** nikde jinde – Django admin dovolí zaregistrovat model jen jednou, jinak appka spadne hned při startu (`AlreadyRegistered`).

## Datový model

`SecurityRule` (`dashboard/models.py`) – viz tabulka výše.

`BlockedNumber` (`dashboard/models.py`):

| Pole | Význam |
|---|---|
| `owner` | Vlastník (brána je multi-tenant per uživatel) |
| `number` | Normalizované telefonní číslo |
| `reason` | Důvod blokace (ruční text, nebo automaticky vygenerovaný popis) |
| `created_at` | Kdy bylo číslo zablokované |
| `expires_at` | `null` = trvalá blokace (ruční), vyplněné = dočasná (automatická) |

## Testování

**Ruční blokace:**
1. Přidej testovací číslo na stránce "Blokovaná čísla".
2. Pošli SMS z tohoto čísla na bránu.
3. V logu událostí (`event_logs`) zkontroluj, že `result_summary` obsahuje "je blokované – událost ignorována" a že nevznikla žádná odchozí akce.

**Automatická ochrana proti zahlcení:**
1. Zkontroluj aktuální práh na stránce Pravidla (karta "Bezpečnostní pravidlo") – výchozí je 20 událostí / 10 min.
2. Pošli rychle za sebou víc událostí, než je nastavený práh, ze stejného čísla (např. simulátorem příchozích událostí, aby se nemuselo reálně poslat tolik SMS).
3. Ověř, že se číslo objevilo na stránce "Blokovaná čísla" s `expires_at` podle nastaveného cooldownu a důvodem "Automaticky zablokováno...".
4. Ověř v logu, že další události mají `result_summary` s hláškou o překročení limitu.

**Reakce na bezpečnostní událost:**
1. Na stránce Pravidla otevři "Výchozí: Upozornění na bezpečnostní blokaci", nastav cílová čísla/skupiny nebo zapni e-mail/Teams kanál, ulož a aktivuj.
2. Vyvolej automatickou blokaci (viz krok výše).
3. Ověř, že vznikla odchozí akce (notifikace) navázaná na tohle pravidlo – v logu událostí by měla přibýt **další, samostatná** položka s typem "Bezpečnost" (`event_type=SECURITY`), odlišná od původní zablokované SMS/API události.

**Vypnutí/úprava pravidla (jen superuser):**
1. Přihlas se do `/admin/dashboard/securityrule/`.
2. Uprav `active` (zapnuto/vypnuto) nebo prahy – buď přímo v seznamu (`list_editable`), nebo spolehlivěji v detailu záznamu (klikni na řádek, ne jen na checkbox).
3. **Nezapomeň kliknout na tlačítko "Uložit"/"Save"** – u editace přímo v seznamu (`list_editable`) samotné zaškrtnutí checkboxu nic neuloží, dokud se pod tabulkou neklikne na Uložit. Tohle je nejčastější příčina, proč se zapnutí/vypnutí "neprojeví" – změna se ve skutečnosti vůbec neuložila do databáze (dá se ověřit přes shell: `AutomationRule.objects.get(name='...').active`).
4. Přidat nový řádek ani smazat existující nejde – tlačítka pro to admin nenabízí.

## Omezení a co tahle ochrana neřeší

- **Spoofing čísla odesílatele** – ověření identity volajícího/odesílatele SMS řeší mobilní síť/operátor, ne aplikace. Pokud útočník dokáže podvrhnout číslo, které je zrovna odblokované/důvěryhodné, ochrana ho nezachytí.
- **Obsah zprávy (XSS/injection)** – Django šablony ve výchozím stavu automaticky escapují HTML (`{{ }}`), takže obsah SMS zobrazený v dashboardu není přímo nebezpečný. Databázové dotazy jdou přes Django ORM (parametrizované), takže SQL injection přes obsah SMS není reálná hrozba.
- **Náklady na SIM/operátora** – rate limit brání extrémnímu zahlcení, ale nerozlišuje legitimní vysoký provoz od útoku dokonale; při ostrém provozu s vyšším objemem SMS zvaž úpravu prahů podle reálného provozu.
