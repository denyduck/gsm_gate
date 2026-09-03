# Zabezpečení proti zahlcení SMS

Ochrana proti zneužití brány: zahlcení velkým počtem SMS/API událostí z jednoho čísla (spam, DoS, vyčerpání fronty/nákladů na odchozí SMS) a možnost ručně zablokovat konkrétní číslo.

## Jak to funguje

Ochrana je zabudovaná přímo v `dashboard/services/rules_engine.py`, ve funkci `process_incoming_event()` – běží při **každé** příchozí události (SMS i API), dřív než se vyhodnotí jakékoliv automatizační pravidlo.

### 1) Ruční blokace

Číslo na seznamu blokovaných čísel se u příchozí události rovnou zahodí – `IncomingEventLog` se pro audit vytvoří vždy, ale žádné pravidlo se nevyhodnotí a nevznikne žádná odchozí akce.

Správa přes web: **Blokovaná čísla** v hlavním menu (vyžaduje oprávnění `dashboard.view_blockednumber`).

### 2) Automatická ochrana proti zahlcení (rate limiting)

Pokud jedno číslo (`source_number`) pošle za posledních **10 minut** víc než **20 událostí**, brána ho automaticky přidá na blokovaný seznam s vypršením za **30 minut**. Po uplynutí této doby se číslo samo odblokuje (žádný manuální zásah není potřeba).

Konstanty (v `rules_engine.py`):

```python
RATE_LIMIT_WINDOW_MINUTES = 10   # časové okno
RATE_LIMIT_MAX_EVENTS = 20       # max. povolených událostí v okně
AUTO_BLOCK_COOLDOWN_MINUTES = 30 # jak dlouho trvá automatická blokace
```

Změna prahu vyžaduje úpravu kódu (žádné UI pro konfiguraci prahu zatím není) – po změně nezapomeň redeploy (`docker compose up -d --build web`).

## Datový model

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
1. Pošli rychle za sebou > 20 testovacích SMS/API událostí ze stejného čísla (např. simulátorem příchozích událostí, aby se nemuselo reálně poslat 21 SMS).
2. Ověř, že se číslo objevilo na stránce "Blokovaná čísla" s `expires_at` cca 30 minut od teď a důvodem "Automaticky zablokováno...".
3. Ověř v logu, že (21.) a další události mají `result_summary` s hláškou o překročení limitu.

## Omezení a co tahle ochrana neřeší

- **Spoofing čísla odesílatele** – ověření identity volajícího/odesílatele SMS řeší mobilní síť/operátor, ne aplikace. Pokud útočník dokáže podvrhnout číslo, které je zrovna odblokované/důvěryhodné, ochrana ho nezachytí.
- **Obsah zprávy (XSS/injection)** – Django šablony ve výchozím stavu automaticky escapují HTML (`{{ }}`), takže obsah SMS zobrazený v dashboardu není přímo nebezpečný. Databázové dotazy jdou přes Django ORM (parametrizované), takže SQL injection přes obsah SMS není reálná hrozba.
- **Náklady na SIM/operátora** – rate limit brání extrémnímu zahlcení, ale nerozlišuje legitimní vysoký provoz od útoku dokonale; při ostrém provozu s vyšším objemem SMS zvaž úpravu prahů podle reálného provozu.
