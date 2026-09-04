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

## Testování bez psaní vlastního HTTP klienta

Appka má dva vestavěné způsoby, jak volání objektu vyzkoušet bez curl/Postman:

- **Testovací volání** (tlačítko na detailu objektu) – appka sama odešle skutečný HTTP požadavek na ingest endpoint se skutečným tokenem a ukáže reálnou odpověď (HTTP stav + tělo).
- **QR spouštěč** – QR kód s odkazem obsahujícím token objektu; naskenování telefonem (bez přihlášení) vyvolá stejné vyhodnocení pravidel jako API volání. Token je v URL, takže s odkazem/QR kódem zacházej jako s heslem.

Obojí podrobně v [Funkcionalita – Objekty zařízení](funkcionalita.md#11-objekty-zařízení).

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
