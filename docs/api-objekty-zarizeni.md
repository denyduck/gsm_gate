# API objektů zařízení

## Účel

API endpoint umožňuje externím objektům/zařízením odeslat událost do systému, která se následně vyhodnotí pravidlovým enginem stejně jako SMS/volání.

## Autentizace

- každý objekt má vlastní API token,
- token je spravovaný přes `DeviceObjectApiCredential`,
- token lze regenerovat z detailu objektu.

## Endpoint

- ingest endpoint: `/dashboard/api/device-events/ingest/`
- metoda: typicky `POST`
- přenos: JSON payload

## Doporučený payload

Příklad minimálního payloadu:

```json
{
  "object_name": "Mrazak A1",
  "event_type": "API",
  "message": "Teplota prekrocila limit",
  "status": "ALERT"
}
```

Rozšířený payload může nést i interní identifikátor, timestamp, severity a další metadata.

## Zpracování na backendu

1. Ověření tokenu.
2. Spárování na `DeviceObject`.
3. Vytvoření `IncomingEventLog` typu `API`.
4. Vyhodnocení aktivních pravidel.
5. Vytvoření odpovídajících `OutgoingAction`.

## Bezpečnostní doporučení

- tokeny pravidelně rotovat,
- používat HTTPS/TLS v produkci,
- logovat neúspěšné autentizace,
- limitovat frekvenci požadavků (rate limiting) na reverzní proxy.
