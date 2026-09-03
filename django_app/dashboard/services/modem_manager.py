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


# Hodnoty MMModemLock, které znamenají "SIM není zamčená" - liší se podle
# verze ModemManager/mmcli (u našeho zařízení se ukázalo "--").
_NO_LOCK_VALUES = ('--', 'none', '')


class ModemManagerClient:
    """Klient pro modem řízený přes ModemManager/mmcli (Teltonika Calyx a další)."""

    def __init__(self, modem_index: Optional[int] = None, pin_code: Optional[str] = None):
        self._modem_index = modem_index
        self._pin_code = pin_code or None

    def connect(self):
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

    def send_sms(self, phone_number: str, text: str, request_delivery_report: bool = False):
        modem_idx = self._resolve_modem_index()

        if "'" in text or "'" in phone_number:
            raise ModemError('Text zprávy ani číslo nesmí obsahovat apostrof (omezení mmcli parseru).')

        create_arg = f"text='{text}',number='{phone_number}'"
        if request_delivery_report:
            create_arg += ',delivery-report-request=yes'
        data = _run_mmcli(['-m', str(modem_idx), f'--messaging-create-sms={create_arg}'])

        sms_path = data.get('modem', {}).get('messaging', {}).get('created-sms')
        if not sms_path:
            raise ModemError(f'mmcli nevrátil cestu k nově vytvořené SMS: {data}')

        sms_idx = _index_from_path(sms_path)
        send_result = _run_mmcli(['-s', str(sms_idx), '--send'])

        # --send při úspěchu často nevrátí žádný JSON (viz _run_mmcli) - v tom
        # případě je jediným signálem úspěchu nulový návratový kód a `state`
        # tu není k dispozici vůbec. Selhání hlásíme jen tehdy, když stav
        # skutečně známe a je jiný než "sent"/"sending".
        state = send_result.get('sms', {}).get('properties', {}).get('state')
        if state is not None and state not in ('sent', 'sending'):
            raise ModemError(f'SMS se nepodařilo odeslat, stav po odeslání: {state}')

        # Uklidíme si po sobě, ať se odchozí zprávy nehromadí ve výpisu.
        try:
            self.delete_sms(sms_idx)
        except ModemError:
            pass

    def read_unread_sms(self) -> List[IncomingSms]:
        modem_idx = self._resolve_modem_index()
        data = _run_mmcli(['-m', str(modem_idx), '--messaging-list-sms'])

        sms_paths = (
            data.get('modem.messaging.sms')
            or data.get('sms-list')
            or data.get('modem', {}).get('messaging', {}).get('sms')
            or []
        )

        messages: List[IncomingSms] = []
        for path in sms_paths:
            idx = _index_from_path(path)
            try:
                detail = _run_mmcli(['-s', str(idx)])
            except ModemError:
                continue

            sms = detail.get('sms', {})
            props = sms.get('properties', {})
            content = sms.get('content', {})

            if props.get('state') != 'received':
                continue

            messages.append(IncomingSms(
                index=idx,
                sender=content.get('number', ''),
                message=content.get('text', ''),
            ))

        return messages

    def delete_sms(self, index: int):
        modem_idx = self._resolve_modem_index()
        sms_path = f'/org/freedesktop/ModemManager1/SMS/{index}'
        _run_mmcli(['-m', str(modem_idx), f'--messaging-delete-sms={sms_path}'])

    def get_signal_quality(self) -> Optional[int]:
        """Vrací sílu signálu jako procento (0-100), na rozdíl od starého CSQ (0-31)."""
        modem_idx = self._resolve_modem_index()
        data = _run_mmcli(['-m', str(modem_idx)])
        value = data.get('modem', {}).get('generic', {}).get('signal-quality', {}).get('value')
        if value in (None, '--'):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
