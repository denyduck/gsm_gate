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

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ModemError(f'Nepodařilo se rozparsovat výstup mmcli ({" ".join(args)}): {e}') from e


def _sms_index_from_path(path: str) -> int:
    return int(path.rsplit('/', 1)[-1])


class ModemManagerClient:
    """Klient pro modem řízený přes ModemManager/mmcli (Teltonika Calyx a další)."""

    def __init__(self, modem_index: Optional[int] = None):
        self._modem_index = modem_index

    def connect(self):
        self._modem_index = self._resolve_modem_index()
        data = _run_mmcli(['-m', str(self._modem_index)])
        state = data.get('modem', {}).get('generic', {}).get('state')
        if state not in ('registered', 'connected'):
            raise ModemError(f'Modem není registrovaný v síti (aktuální stav: {state}).')

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

        self._modem_index = _sms_index_from_path(modems[0])
        return self._modem_index

    def send_sms(self, phone_number: str, text: str):
        modem_idx = self._resolve_modem_index()

        if "'" in text or "'" in phone_number:
            raise ModemError('Text zprávy ani číslo nesmí obsahovat apostrof (omezení mmcli parseru).')

        create_arg = f"text='{text}',number='{phone_number}'"
        data = _run_mmcli(['-m', str(modem_idx), f'--messaging-create-sms={create_arg}'])

        sms_path = data.get('sms', {}).get('dbus-path') or data.get('modem.messaging.create-sms')
        if not sms_path:
            raise ModemError(f'mmcli nevrátil cestu k nově vytvořené SMS: {data}')

        sms_idx = _sms_index_from_path(sms_path)
        send_result = _run_mmcli(['-s', str(sms_idx), '--send'])

        state = send_result.get('sms', {}).get('properties', {}).get('state')
        if state not in ('sent', 'sending'):
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
            idx = _sms_index_from_path(path)
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
