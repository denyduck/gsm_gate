# Role a oprávnění

## Princip

Aplikace používá kombinaci:

- Django autentizace (uživatelé),
- per-model oprávnění (`view`, `add`, `change`, `delete`),
- vlastnictví dat (owner),
- sdílení přes M2M vazby (uživatel ↔ čísla/skupiny/pravidla),
- tří úrovní práv nad tímhle vším – super admin / admin / user, viz níže.

## Tři úrovně práv: super admin / admin / user

| Úroveň | Co to je | Co to umožňuje |
|---|---|---|
| **super admin** | `User.is_superuser = True` | Úplně všechno – stejné jako admin níže, jen přes vestavěný Django flag. |
| **admin** | členství v Django auth skupině **„Admin“** (`django.contrib.auth.models.Group` – pozor, nejde o appkovou `dashboard.Group` pro telefonní skupiny) | Zjednodušeně úplně všechno: vidí a upravuje/maže data všech uživatelů (čísla, skupiny, pravidla, objekty), má přístup na Zálohování/Export/Import/Reset dat, Sebediagnostiku, může smazat i chráněná systémová pravidla a jiné uživatele. Skupina „Admin" se vytvoří automaticky migrací (`0054_seed_admin_role.py`) se všemi oprávněními pro `dashboard` i `auth` app – nic se nevybírá ručně. |
| **user** | běžný účet, bez superuser flagu a bez skupiny „Admin" | Vidí a upravuje jen svoje vlastní data (plus to, co je mu explicitně sdílené – viz "Vlastnictví vs. sdílení" níže). |

**Jak povýšit uživatele na admina:** Django Admin → *Users* → daný účet → sekce *Permissions* → do pole *Groups* přidat **Admin**. Pro přístup do samotného `/admin/` navíc potřebuje zaškrtnuté **„Staff status“** (to je vlastnost konkrétního účtu, ne role – skupina sama o sobě přístup do Django Adminu nedává).

Mimochodem – každý admin/superuser dostává i automatická upozornění na provozní stav brány (restart RPi, přihlášení jiného admina, útok na přihlášení, zdraví brány), pokud si k nim založí pravidlo – viz [Systémové a provozní události](systemove-udalosti.md).

Kontrola v kódu je vždy přes jednu funkci – `dashboard.access.is_admin(user)` (`user.is_superuser or user.groups.filter(name='Admin').exists()`) – a používá se místo přímého `user.is_superuser` ve `views.py`, `gsm_gate/admin.py` i v šablonách (přes `is_admin` v globálním kontextu, `dashboard/context_processors.py`). `is_superuser` se v celém kódu objevuje jen uvnitř týhle jedné funkce – nikde jinde se na něj appka nedívá přímo.

**Jediný reálný rozdíl mezi superuserem a skupinou „Admin“:** superuser je vestavěný Django flag, který automaticky obchází *úplně jakoukoliv* kontrolu oprávnění, i budoucí/neznámou (např. nový model přidaný později do appky). Skupina „Admin“ dostává svoje oprávnění explicitně vyjmenovaná migrací `0054_seed_admin_role.py` (`content_type__app_label__in=['dashboard', 'auth']`) – pro cokoliv mimo tyhle dvě aplikace (nebo pro budoucí novou aplikaci) by bylo potřeba seedovací migraci doplnit/spustit znovu, superuser by to ale měl automaticky bez zásahu. V praxi jsou obě úrovně prakticky zaměnitelné – „Admin“ skupina existuje především proto, aby šlo přidat víc lidí na nejvyšší úroveň práv bez nutnosti dávat jim vestavěný `is_superuser` flag.

## Vlastnictví vs. sdílení (user úroveň)

Mít Django oprávnění (např. `change_phonenumber`) umožňuje *používat* danou funkci appky vůbec – ale samo o sobě nestačí k zásahu do **cizí konkrétní položky**. U čísel a skupin appka navíc kontroluje vlastnictví:

- **Upravit/smazat** číslo nebo skupinu smí jen jeho **vlastník** (`owner`), nebo admin/superuser – sdílený přístup (`PhoneNumber.users`/`Group.users`) sám o sobě k editaci/mazání nestačí, dává jen zobrazení a možnost dané číslo/skupinu vybírat (např. v pravidlech, při sdílení SMS).
- To platí i v Django Adminu (`AutomationRuleAdmin`, `OwnerRestrictedAdminMixin` pro objekty/logy/odchozí akce) – ne jen v běžné appce.

Prakticky to znamená: Django oprávnění `change_phonenumber`/`delete_phonenumber` apod. je bezpečné nechat udělené všem běžným uživatelům, kteří mají správu svých vlastních čísel – appka sama zablokuje zásah do cizích položek bez nutnosti cokoliv dalšího nastavovat.

## Doporučené role (Django auth skupiny s konkrétním výběrem oprávnění)

### 1) Viewer (read-only)

- vidí dashboard, čísla, skupiny, pravidla, logy,
- nemůže vytvářet ani měnit data.

### 2) Operátor

- správa čísel a skupin,
- práce s hromadnými úpravami,
- čtení logů.

### 3) Rule manager

- vytváří/upravuje pravidla,
- používá simulátor,
- vyhodnocuje dopad v auditu.

### 4) Gateway admin

- nastavuje parametry brány,
- spravuje objekty zařízení a API tokeny,
- řeší provozní incidenty (Telemetrie, Sebediagnostika),
- (jako admin/superuser) zálohuje/obnovuje data, maže data, upravuje bezpečnostní prahy v Django Adminu.

## Mapa oprávnění podle modulů

- **Čísla**: `view_phonenumber`, `add_phonenumber`, `change_phonenumber`, `delete_phonenumber`
- **Skupiny**: `view_group`, `add_group`, `change_group`, `delete_group`
- **Pravidla**: `view_automationrule`, `add_automationrule`, `change_automationrule`, `delete_automationrule`
- **Události**: `view_incomingeventlog`, `add_incomingeventlog`
- **Odchozí akce**: `view_outgoingaction`
- **Gateway settings**: `view_gatewaysettings`, `change_gatewaysettings`
- **Objekty zařízení**: `view_deviceobject`, `add_deviceobject`, `change_deviceobject`, `delete_deviceobject`. Sdílení (pole `users` na `DeviceObject`, stejně jako u čísel/skupin) se nastavuje jen přes Django Admin (`filter_horizontal`), ne v appce – sdílený uživatel pak objekt vidí v dropdownu "Zdrojové objekty" u pravidel, i když ho nevlastní.
- **Blokovaná čísla**: `view_blockednumber`, `add_blockednumber`, `delete_blockednumber` (role `Blokovaná čísla - správa`, přidáno i do `Operátor` a `Jen čtení` – viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md))
- **Bezpečnostní pravidlo** (prahy pro automatickou ochranu proti zahlcení): úprava/zapnutí/vypnutí jen přes Django Admin, jen admin/superuser (`access.is_admin()`) – nejde o standardní roli s běžnými oprávněními, záměrně mimo systém rolí popsaný výše. Smazat (jen kaskádou přes mazaného vlastníka, samostatně ne) ho taky může jen admin/superuser.
- **Automatizační pravidlo s `is_protected=True`** (vzorové/systémové, např. "Výchozí: Upozornění na bezpečnostní blokaci"): v běžné appce (`rule_edit`/`rule_delete`) ho nesmí upravit/smazat NIKDO, bez výjimky – tam ta ochrana reálně žije. V Django Adminu ho smazat může admin/superuser (`AutomationRuleAdmin.has_delete_permission`), jinak by nešlo kaskádou smazat žádného uživatele, kterému se toto pravidlo založilo (téměř každému) – viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md).
- **Telemetrie**: sdílí oprávnění s Odchozími akcemi (`view_outgoingaction`) – žádné samostatné oprávnění.
- **Sebediagnostika**, **Zálohování** (export/import/reset dat): žádné standardní oprávnění, výhradně `access.is_admin(request.user)` kontrola přímo ve view – stejný vzor jako u Bezpečnostního pravidla výše.

## Důležité chování v UI

- tlačítka CRUD se renderují pouze když má uživatel odpovídající oprávnění,
- u sdílených dat se zobrazení řídí viditelností dat + permission checkem,
- vlastník je zvýrazněn v tabulkách i kartách.
