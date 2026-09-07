# API objektů zařízení

## Účel

API endpoint umožňuje externím objektům/zařízením odeslat událost do systému, která se následně vyhodnotí pravidlovým enginem stejně jako SMS.

## Autentizace

- každý objekt má vlastní API token (`DeviceObjectApiCredential`, 1:1 k objektu),
- token se posílá v hlavičce `X-Device-Token`, ne v těle požadavku,
- token lze regenerovat z detailu objektu (starý přestane platit okamžitě – i vygenerovaný QR spouštěč/odkaz).

## Endpoint

- ingest endpoint: `/dashboard/api/device-events/ingest/`
- metoda: `POST`
- přenos: JSON payload
- **rate limit**: po 20 neplatných pokusech (chybějící/špatný token) z jedné IP za 60 s appka další pokusy z té IP na minutu odmítá s `429` – viz [Zabezpečení proti zahlcení SMS](zabezpeceni-sms.md#4-rate-limit-na-api-ingest-a-zámek-proti-brute-force-na-přihlášení).

## Skutečný formát payloadu

Appka čte přesně tahle pole (viz `views.device_event_ingest_api`) – všechna nepovinná, s výchozími hodnotami:

```json
{
  "event_type": "API",
  "source_number": "mraznicka-a1",
  "message_body": "Teplota překročila limit"
}
```

- `event_type` – `SMS`, `CALL` nebo `API`; cokoliv jiného (nebo chybějící) se vyhodnotí jako `API`.
- `source_number` – libovolný identifikátor události (nemusí být telefonní číslo); chybí-li, použije se ID objektu.
- `message_body` – volný text; chybí-li, je prázdný.

Přesný formát (curl příklad se skutečným tokenem objektu) je vidět přímo na detailu objektu v appce – bezpečnější ho odtud zkopírovat, než přepisovat ručně.

## Jak zavolat API – různé způsoby

Endpoint i token najdeš na detailu objektu v appce (adresa `/dashboard/api/device-events/ingest/` a hlavička `X-Device-Token`) – tady jsou stejné volání v různých nástrojích, jen doplň skutečný endpoint a token ze svého objektu.

### curl

```bash
curl -X POST "http://TVOJE-BRANA/dashboard/api/device-events/ingest/" \
  -H "Content-Type: application/json" \
  -H "X-Device-Token: TVUJ_TOKEN" \
  -d '{"event_type":"API","source_number":"mraznicka-a1","message_body":"Teplota překročila limit"}'
```

### PowerShell

```powershell
$headers = @{ "X-Device-Token" = "TVUJ_TOKEN" }
$body = @{
    event_type   = "API"
    source_number = "mraznicka-a1"
    message_body  = "Teplota překročila limit"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://TVOJE-BRANA/dashboard/api/device-events/ingest/" -Method Post -Headers $headers -Body $body -ContentType "application/json"
```

### Python (requests)

```python
import requests

response = requests.post(
    "http://TVOJE-BRANA/dashboard/api/device-events/ingest/",
    headers={"X-Device-Token": "TVUJ_TOKEN"},
    json={
        "event_type": "API",
        "source_number": "mraznicka-a1",
        "message_body": "Teplota překročila limit",
    },
    timeout=8,
)
print(response.status_code, response.json())
```

### Mikrokontrolér / embedded zařízení (ESP32, Arduino apod.)

Stačí libovolná knihovna, co umí HTTP POST s vlastní hlavičkou a JSON tělem (např. `HTTPClient` v Arduino frameworku pro ESP32) – požadavek je stejný jako u curl výše, jen ho posílá firmware místo terminálu. Žádné TLS certifikáty ani autentizační handshake navíc není potřeba, appka nemá TLS (viz [Bezpečnostní doporučení](#bezpečnostní-doporučení) níže).

### Odpověď

Úspěch (HTTP 201):

```json
{"ok": true, "event_log_id": 482, "matched_rules": 1, "queued_actions": 2}
```

- `event_log_id` – ID záznamu v [Logu událostí](funkcionalita.md#8-log-událostí), kde událost najdeš.
- `matched_rules` – kolik aktivních pravidel na událost zareagovalo.
- `queued_actions` – kolik [odchozích akcí](funkcionalita.md#9-odchozí-akce) se tím zafrontovalo (SMS, e-mail, Teams…).

Chyba (401/400/429) vrací `{"ok": false, "error": "..."}` – text v `error` přesně říká, co nesedí (chybějící/neplatný token, špatný JSON, nebo rate limit).

## Testování bez psaní vlastního HTTP klienta

Appka má dva vestavěné způsoby, jak volání objektu vyzkoušet bez curl/PowerShell/Postman:

- **Testovací volání** (tlačítko na detailu objektu) – appka sama odešle skutečný HTTP požadavek na ingest endpoint se skutečným tokenem a ukáže reálnou odpověď (HTTP stav + tělo). Podrobně níže.
- **QR spouštěč** – QR kód s odkazem obsahujícím token objektu; naskenování telefonem (bez přihlášení) vyvolá stejné vyhodnocení pravidel jako API volání. Token je v URL, takže s odkazem/QR kódem zacházej jako s heslem.

Obojí podrobně v [Funkcionalita – Objekty zařízení](funkcionalita.md#11-objekty-zařízení).

## Co přesně dělá testovací volání

Tlačítko "Odeslat testovací požadavek" na detailu objektu **není simulace** – appka (server) sama sestaví stejný požadavek, jaký by poslalo reálné zařízení, a odešle ho na svůj vlastní ingest endpoint přes běžné HTTP:

1. Vezme skutečný token objektu (`X-Device-Token`) a endpoint (stejná adresa, jakou appka právě běží).
2. Tělo požadavku je `event_type: "API"`, `source_number` = ID objektu, `message_body` = text z pole ve formuláři (nebo výchozí text, když necháš prázdné).
3. Požadavek fyzicky projde stejnou cestou jako od reálného zařízení – přes rate limit, ověření tokenu, vytvoření [události v logu](funkcionalita.md#8-log-událostí) a vyhodnocení pravidel.
4. Odpověď (HTTP stav + JSON tělo popsané výše) appka zobrazí jako zprávu nahoře na stránce – zelenou při úspěchu, červenou při chybě.

Proto tímhle tlačítkem ověříš **celou cestu** (síť, ALLOWED_HOSTS, token, rate limit, pravidla) – ne jen to, jestli by pravidlo teoreticky sedělo. Pokud testovací volání selže, ale [Simulátor příchozí události](funkcionalita.md#7-simulátor-příchozí-události) (který vyhodnocuje pravidla přímo, bez HTTP) projde v pořádku, problém je v síťové/HTTP vrstvě (ALLOWED_HOSTS, token, rate limit), ne v logice pravidla samotného.

## Zpracování na backendu

1. Rate limit check (viz výše) – při překročení `429` bez dotazu do DB.
2. Ověření tokenu (`X-Device-Token` proti `DeviceObjectApiCredential.token`, `active=True`).
3. Spárování na `DeviceObject` (přes `select_related`).
4. Vytvoření `IncomingEventLog` typu podle `event_type`.
5. Vyhodnocení aktivních pravidel vlastníka objektu.
6. Vytvoření odpovídajících `OutgoingAction`.
7. Aktualizace `last_used_at` na credentialu.

## Bezpečnostní doporučení

- tokeny pravidelně rotovat (tlačítko "Regenerovat API klíč" na detailu objektu),
- appka **nemá TLS** – běží přímo na gunicornu bez reverse proxy (vědomé rozhodnutí kvůli jednoduchosti, viz [Architektura](architektura.md#web-server)), takže token cestuje po síti nešifrovaný; drž bránu na důvěryhodné LAN, ne na veřejném internetu,
- neplatné pokusy o autentizaci appka sama loguje a rate-limituje (viz výše) – žádná reverzní proxy k tomu není potřeba.
