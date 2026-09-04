# Role a oprávnění

## Princip

Aplikace používá kombinaci:

- Django autentizace (uživatelé),
- per-model oprávnění (`view`, `add`, `change`, `delete`),
- vlastnictví dat (owner),
- sdílení přes M2M vazby (uživatel ↔ čísla/skupiny/pravidla).

## Doporučené role

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
- (jako superuser) zálohuje/obnovuje data, maže data, upravuje bezpečnostní prahy v Django Adminu.

## Mapa oprávnění podle modulů

- **Čísla**: `view_phonenumber`, `add_phonenumber`, `change_phonenumber`, `delete_phonenumber`
- **Skupiny**: `view_group`, `add_group`, `change_group`, `delete_group`
- **Pravidla**: `view_automationrule`, `add_automationrule`, `change_automationrule`, `delete_automationrule`
- **Události**: `view_incomingeventlog`, `add_incomingeventlog`
- **Odchozí akce**: `view_outgoingaction`
- **Gateway settings**: `view_gatewaysettings`, `change_gatewaysettings`
- **Objekty zařízení**: `view_deviceobject`, `add_deviceobject`, `change_deviceobject`, `delete_deviceobject`. Sdílení (pole `users` na `DeviceObject`, stejně jako u čísel/skupin) se nastavuje jen přes Django Admin (`filter_horizontal`), ne v appce – sdílený uživatel pak objekt vidí v dropdownu "Zdrojové objekty" u pravidel, i když ho nevlastní.
- **Blokovaná čísla**: `view_blockednumber`, `add_blockednumber`, `delete_blockednumber` (role `Blokovaná čísla - správa`, přidáno i do `Operátor` a `Jen čtení` – viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md))
- **Bezpečnostní pravidlo** (prahy pro automatickou ochranu proti zahlcení): úprava/zapnutí/vypnutí jen přes Django Admin, výhradně superuser – nejde o standardní roli s běžnými oprávněními, záměrně mimo systém rolí popsaný výše.
- **Telemetrie**: sdílí oprávnění s Odchozími akcemi (`view_outgoingaction`) – žádné samostatné oprávnění.
- **Sebediagnostika**, **Zálohování** (export/import/reset dat): žádné standardní oprávnění, výhradně `request.user.is_superuser` kontrola přímo ve view – stejný vzor jako u Bezpečnostního pravidla výše.

## Důležité chování v UI

- tlačítka CRUD se renderují pouze když má uživatel odpovídající oprávnění,
- u sdílených dat se zobrazení řídí viditelností dat + permission checkem,
- vlastník je zvýrazněn v tabulkách i kartách.
