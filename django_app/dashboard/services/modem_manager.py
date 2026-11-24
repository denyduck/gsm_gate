import json
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional


class ModemError(Exception):
    pass


@dataclass
class IncomingSms:
    index: int
    sender: str
    message: str
    timestamp: str = ''


@dataclass
class ModemSms:
    """Libovolná SMS, kterou ModemManager drží (příchozí i odchozí, v
    jakémkoliv stavu) - pro úklid paměti modemu, viz list_sms()."""
    index: int
    state: str
    number: str = ''
    text: str = ''
    timestamp: str = ''
    storage: str = ''


@dataclass
class StorageInfo:
    """Obsazenost úložiště SMS podle modemu samotného (AT+CPMS?)."""
    storage: str
    used: int
    total: int


# Kontrola vstupu PŘED vytvořením SMS v modemu - chybná zpráva (neplatné
# číslo, apostrof, přehnaná délka) tak skončí chybou dřív, než by v paměti
# modemu založila objekt, který by po neúspěšném --send mohl zůstat viset
# (incident 2026-11: zbytky odchozích SMS zaplnily paměť modemu a brána
# přestala přijímat SMS - viz docs/modem-diagnostika.md).
_VALID_NUMBER_RE = re.compile(r'^\+?\d{3,15}$')
SMS_MAX_PARTS = 10


def parse_cpms(raw: str) -> Optional[StorageInfo]:
    """Z odpovědi `+CPMS: "ME",12,25,"ME",12,25,"ME",12,25` vrátí úložiště,
    kam modem ukládá PŘIJATÉ SMS (3. trojice, mem3) - právě jeho zaplnění
    zastaví příjem. Bez 3. trojice vezme první."""
    triples = re.findall(r'"(\w+)"\s*,\s*(\d+)\s*,\s*(\d+)', raw or '')
    if not triples:
        return None
    storage, used, total = triples[2] if len(triples) >= 3 else triples[0]
    total_int = int(total)
    if total_int <= 0:
        return None
    return StorageInfo(storage=storage.lower(), used=int(used), total=total_int)


def _run_mmcli(args: List[str], timeout: float = 20.0) -> dict:
    try:
        result = subprocess.run(
            ['mmcli', *args, '-J'],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise ModemError(f'Chyba spuštění mmcli ({" ".join(args)}): {e}') from e

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip()
        raise ModemError(f'mmcli chyba ({" ".join(args)}): {detail}')

    stdout = result.stdout.strip()
    if not stdout:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Akční příkazy (--send, --messaging-delete-sms) při úspěchu často
        # vypíšou jen lidsky čitelné potvrzení místo JSONu, i s -J. Návratový
        # kód 0 už jsme ověřili výše, takže to bereme jako úspěch bez dat.
        return {}


def _index_from_path(path: str) -> int:
    return int(path.rsplit('/', 1)[-1])


# Odhad počtu SMS částí pro dynamický timeout --send (viz send_sms) - delší
# zprávy (např. sdílení více čísel najednou) mají víc částí, modem je
# odesílá postupně přes AT příkazy a pevných 20s na celé odeslání nemusí
# stačit. Čeština běžně obsahuje znaky mimo základní GSM-7 abecedu (ř, ě, ů,
# ...), takže se musí počítat s horším případem - UCS-2 (70/67 znaků na
# část) - jednodušší a bezpečnější než přesně parsovat GSM-7 abecedu.
_GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)


def _estimate_sms_parts(text: str) -> int:
    length = len(text)
    if length == 0:
        return 1
    if all(ch in _GSM7_BASIC for ch in text):
        limit = 160 if length <= 160 else 153
    else:
        limit = 70 if length <= 70 else 67
    return max(1, -(-length // limit))  # ceil division


# Hodnoty MMModemLock, které znamenají "SIM není zamčená" - liší se podle
# verze ModemManager/mmcli (u našeho zařízení se ukázalo "--").
_NO_LOCK_VALUES = ('--', 'none', '')


class ModemManagerClient:
    """Klient pro modem řízený přes ModemManager/mmcli (Teltonika Calyx a další)."""

    def __init__(self, modem_index: Optional[int] = None, pin_code: Optional[str] = None):
        self._modem_index = modem_index
        self._pin_code = pin_code or None

    def connect(self):
        # Vždy zahodit případný zastaralý index - po USB re-enumeraci nebo
        # restartu ModemManageru může modem dostat jiné číslo (viděno v praxi:
        # 0 -> 1 po USB unbind/bind resetu), jinak by worker navždy zkoušel
        # mluvit s indexem, který už neexistuje.
        self._modem_index = None
        self._modem_index = self._resolve_modem_index()
        data = _run_mmcli(['-m', str(self._modem_index)])
        generic = data.get('modem', {}).get('generic', {})

        unlock_required = generic.get('unlock-required')
        if unlock_required not in _NO_LOCK_VALUES:
            if not self._pin_code:
                raise ModemError(
                    f'SIM vyžaduje odemčení ({unlock_required}), ale v nastavení brány není vyplněný PIN.'
                )
            self._unlock_sim(self._pin_code)
            data = _run_mmcli(['-m', str(self._modem_index)])
            generic = data.get('modem', {}).get('generic', {})

        state = generic.get('state')
        if state == 'disabled':
            # Po restartu ModemManageru/kontejneru zůstává modem v "disabled",
            # dokud ho něco explicitně nezapne - bez tohohle by tu zůstal
            # navždy (worker sám o sobě žádný enable nikdy nevolal).
            _run_mmcli(['-m', str(self._modem_index), '-e'])
            data = _run_mmcli(['-m', str(self._modem_index)])
            generic = data.get('modem', {}).get('generic', {})
            state = generic.get('state')

        if state not in ('registered', 'connected'):
            raise ModemError(f'Modem není registrovaný v síti (aktuální stav: {state}).')

    def _unlock_sim(self, pin_code: str):
        modem_idx = self._resolve_modem_index()
        detail = _run_mmcli(['-m', str(modem_idx)])
        sim_path = detail.get('modem', {}).get('generic', {}).get('sim')
        if not sim_path:
            raise ModemError('Nepodařilo se zjistit cestu k SIM kartě pro odemčení PIN.')
        sim_idx = _index_from_path(sim_path)
        _run_mmcli(['-i', str(sim_idx), f'--pin={pin_code}'])

    def close(self):
        # ModemManager běží nezávisle jako systémová služba, není co zavírat.
        pass

    def _resolve_modem_index(self) -> int:
        if self._modem_index is not None:
            return self._modem_index

        data = _run_mmcli(['-L'])
        modems = data.get('modem-list') or []
        if not modems:
            raise ModemError('ModemManager nevidí žádný modem (mmcli -L je prázdné).')

        self._modem_index = _index_from_path(modems[0])
        return self._modem_index

    @staticmethod
    def validate_sms(phone_number: str, text: str) -> None:
        """Vyhodí ModemError pro zprávu, kterou nemá smysl modemu vůbec
        předávat. Volá se před --messaging-create-sms, takže chybná zpráva
        v paměti modemu nic nezaloží."""
        if not _VALID_NUMBER_RE.match(phone_number or ''):
            raise ModemError(f'Neplatné cílové číslo "{phone_number}".')
        if not (text or '').strip():
            raise ModemError('Text zprávy je prázdný.')
        if "'" in text:
            raise ModemError('Text zprávy nesmí obsahovat apostrof (omezení mmcli parseru).')
        parts = _estimate_sms_parts(text)
        if parts > SMS_MAX_PARTS:
            raise ModemError(f'Zpráva je příliš dlouhá ({parts} částí SMS, maximum {SMS_MAX_PARTS}).')

    def send_sms(self, phone_number: str, text: str, request_delivery_report: bool = False) -> bool:
        """Odešle SMS. Vrací True, pokud se vytvořenou SMS podařilo z paměti
        modemu i smazat (False = zůstala tam a uklidí ji až další sweep ve
        workeru). Při chybě odeslání vyhodí ModemError - i tehdy se ale
        vytvořenou SMS napřed pokusí smazat."""
        self.validate_sms(phone_number, text)
        modem_idx = self._resolve_modem_index()

        create_arg = f"text='{text}',number='{phone_number}'"
        if request_delivery_report:
            create_arg += ',delivery-report-request=yes'
        data = _run_mmcli(['-m', str(modem_idx), f'--messaging-create-sms={create_arg}'])

        sms_path = data.get('modem', {}).get('messaging', {}).get('created-sms')
        if not sms_path:
            raise ModemError(f'mmcli nevrátil cestu k nově vytvořené SMS: {data}')

        sms_idx = _index_from_path(sms_path)
        # Smazat VŽDY - i po chybě/timeoutu --send. Dřív se mazalo jen po
        # úspěchu a každá neodeslaná zpráva zůstala v paměti modemu navždy
        # (read_unread_sms ji jako ne-"received" přeskakovalo). Výsledek
        # úklidu se při chybě předá v atributu výjimky `sms_cleaned`, ať
        # worker ví, jestli v paměti něco zůstalo.
        try:
            self._send_created_sms(sms_idx, text)
        except Exception as exc:
            exc.sms_cleaned = self._try_delete(sms_idx)
            raise
        return self._try_delete(sms_idx)

    def _try_delete(self, sms_idx: int) -> bool:
        try:
            self.delete_sms(sms_idx)
            return True
        except ModemError:
            return False

    def _send_created_sms(self, sms_idx: int, text: str) -> None:
        # Vícečásťové SMS (dlouhý text, např. sdílení víc čísel najednou)
        # odesílá modem po částech přes AT příkazy - pevných 20s nemusí na
        # celé odeslání stačit. 15s/část s rozumným stropem, ať jedna
        # obrovská zpráva nezablokuje worker cyklus na věčnost.
        send_timeout = min(180.0, max(20.0, 15.0 * _estimate_sms_parts(text)))
        send_result = _run_mmcli(['-s', str(sms_idx), '--send'], timeout=send_timeout)

        # --send při úspěchu často nevrátí žádný JSON (viz _run_mmcli) - v tom
        # případě je jediným signálem úspěchu nulový návratový kód a `state`
        # tu není k dispozici vůbec. Selhání hlásíme jen tehdy, když stav
        # skutečně známe a je jiný než "sent"/"sending".
        state = send_result.get('sms', {}).get('properties', {}).get('state')
        if state is not None and state not in ('sent', 'sending'):
            raise ModemError(f'SMS se nepodařilo odeslat, stav po odeslání: {state}')

    def list_sms(self) -> List[ModemSms]:
        """Všechny SMS, které ModemManager drží - v jakémkoliv stavu
        (received, receiving, sent, sending, stored, unknown). Na rozdíl od
        read_unread_sms slouží i k úklidu zbytků, které by jinak zaplnily
        paměť modemu."""
        modem_idx = self._resolve_modem_index()
        data = _run_mmcli(['-m', str(modem_idx), '--messaging-list-sms'])

        sms_paths = (
            data.get('modem.messaging.sms')
            or data.get('sms-list')
            or data.get('modem', {}).get('messaging', {}).get('sms')
            or []
        )

        messages: List[ModemSms] = []
        for path in sms_paths:
            # Pro jistotu odříznout případný stav v závorce ("…/SMS/12 (sent)").
            idx = _index_from_path(str(path).split(' ')[0])
            try:
                detail = _run_mmcli(['-s', str(idx)])
            except ModemError:
                # Detail nejde přečíst - SMS ale pořád zabírá místo, ať ji
                # sweep ve workeru vidí (stav "unknown") a zkusí smazat.
                messages.append(ModemSms(index=idx, state='unknown'))
                continue

            sms = detail.get('sms', {})
            props = sms.get('properties', {})
            content = sms.get('content', {})

            messages.append(ModemSms(
                index=idx,
                state=props.get('state') or 'unknown',
                number=content.get('number', '') or '',
                text=content.get('text', '') or '',
                timestamp=props.get('timestamp', '') or '',
                storage=props.get('storage', '') or '',
            ))

        return messages

    def read_unread_sms(self) -> List[IncomingSms]:
        return [
            IncomingSms(index=m.index, sender=m.number, message=m.text, timestamp=m.timestamp)
            for m in self.list_sms()
            if m.state == 'received'
        ]

    def get_storage_info(self) -> Optional[StorageInfo]:
        """Skutečná obsazenost úložiště SMS z modemu (AT+CPMS?). Funguje jen
        když ModemManager běží s --debug (jinak mmcli --command odmítne) -
        pak vrací None a worker použije počet SMS z list_sms() a kapacitu
        z GSM_MODEM_SMS_CAPACITY."""
        modem_idx = self._resolve_modem_index()
        try:
            result = subprocess.run(
                ['mmcli', '-m', str(modem_idx), '--command=AT+CPMS?'],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if result.returncode != 0:
            return None
        return parse_cpms(result.stdout)

    def delete_sms(self, index: int):
        modem_idx = self._resolve_modem_index()
        sms_path = f'/org/freedesktop/ModemManager1/SMS/{index}'
        _run_mmcli(['-m', str(modem_idx), f'--messaging-delete-sms={sms_path}'])

    def get_signal_quality(self) -> Optional[int]:
        """Vrací sílu signálu jako procento (0-100), na rozdíl od starého CSQ (0-31).

        ModemManager k hodnotě posílá i příznak "recent" - "no" znamená, že
        se mu signál dlouho nepodařilo čerstvě přeměřit a vrací starou/
        poslední známou hodnotu (reálně pozorováno: "0" po 4 dny, i když
        modem byl celou dobu registrovaný a SMS chodily - viz
        docs/modem-diagnostika.md). Takovou zastaralou hodnotu bereme jako
        neznámou, ne jako aktuální (a často zavádějící) nulu."""
        modem_idx = self._resolve_modem_index()
        data = _run_mmcli(['-m', str(modem_idx)])
        signal_quality = data.get('modem', {}).get('generic', {}).get('signal-quality', {})
        value = signal_quality.get('value')
        if value in (None, '--'):
            return None
        if signal_quality.get('recent') == 'no':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
