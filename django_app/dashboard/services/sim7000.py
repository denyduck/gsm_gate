import re
import time
from dataclasses import dataclass
from typing import List, Optional

import serial


class ModemError(Exception):
    pass


@dataclass
class IncomingSms:
    index: int
    sender: str
    message: str


def _to_pdu(phone_number: str, text: str):
    """Build SMS-SUBMIT PDU with UCS-2 encoding. Returns (pdu_hex, tpdu_byte_count)."""
    smsc = '00'     # use SIM default SMSC
    pdu_type = '11' # SMS-SUBMIT, relative VP
    mr = '00'       # message reference

    number = phone_number.strip()
    if number.startswith('+'):
        ton_npi = '91'
        digits = number[1:]
    else:
        ton_npi = '81'
        digits = number

    digit_count = len(digits)
    if len(digits) % 2:
        digits += 'F'
    swapped = ''.join(digits[i + 1] + digits[i] for i in range(0, len(digits), 2))
    da = f'{digit_count:02X}{ton_npi}{swapped}'

    pid = '00'
    dcs = '08'  # UCS-2
    vp = 'AA'   # relative VP, 4 days

    ud_bytes = text.encode('utf-16-be')
    udl = f'{len(ud_bytes):02X}'
    ud = ud_bytes.hex().upper()

    tpdu = pdu_type + mr + da + pid + dcs + vp + udl + ud
    return smsc + tpdu, len(tpdu) // 2


_UNSOLICITED_PREFIXES = ('RING', '+CLIP:', '+CREG:', '+CPIN:', '+CMTI:')


def _is_unsolicited(line: str) -> bool:
    return line.startswith(_UNSOLICITED_PREFIXES)


def _ucs2_decode(value: str) -> str:
    clean = value.strip()
    if len(clean) >= 4 and len(clean) % 4 == 0:
        try:
            return bytes.fromhex(clean).decode('utf-16-be')
        except (ValueError, UnicodeDecodeError):
            pass
    return value


class Sim7000Client:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 3.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection: Optional[serial.Serial] = None

    def connect(self):
        if self.serial_connection and self.serial_connection.is_open:
            return
        try:
            self.serial_connection = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout,
                rtscts=False, dsrdtr=False,
            )
        except (serial.SerialException, OSError) as e:
            raise ModemError(f'Nepodařilo se otevřít sériový port: {e}') from e

        last_error = None
        for _ in range(5):
            time.sleep(2.0)
            try:
                self.initialize_modem()
                return
            except ModemError as e:
                last_error = e
                try:
                    self.serial_connection.reset_input_buffer()
                except (serial.SerialException, OSError):
                    pass
        raise last_error

    def close(self):
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()

    def initialize_modem(self):
        self.send_at('AT')
        self.send_at('ATE0')
        self.send_at('AT+CMGF=1')
        self.send_at('AT+CSCS="GSM"')
        self.send_at('AT+CPMS="SM","SM","SM"')

    def send_at(self, command: str, timeout: Optional[float] = None) -> str:
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ModemError('Modem není připojen.')

        effective_timeout = timeout if timeout is not None else self.timeout

        try:
            self.serial_connection.reset_input_buffer()
            self.serial_connection.write(f'{command}\r'.encode('ascii'))

            started = time.time()
            output_lines = []
            while time.time() - started < effective_timeout:
                raw = self.serial_connection.readline()
                if not raw:
                    continue
                line = raw.decode(errors='ignore').strip()
                if not line or _is_unsolicited(line):
                    continue
                output_lines.append(line)
                if line == 'OK':
                    return '\n'.join(output_lines)
                if line.startswith('ERROR'):
                    raise ModemError(f'AT chyba ({command}): {line}')
        except (serial.SerialException, OSError) as e:
            raise ModemError(f'Chyba sériové komunikace ({command}): {e}') from e

        raise ModemError(f'AT timeout ({command})')

    def send_sms(self, phone_number: str, text: str):
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ModemError('Modem není připojen.')

        pdu_hex, pdu_length = _to_pdu(phone_number, text)

        self.send_at('AT+CMGF=0')
        try:
            try:
                self.serial_connection.reset_input_buffer()
                self.serial_connection.write(f'AT+CMGS={pdu_length}\r'.encode('ascii'))

                prompt_found = False
                started = time.time()
                while time.time() - started < 5.0:
                    ch = self.serial_connection.read(1)
                    if ch == b'>':
                        prompt_found = True
                        break

                if not prompt_found:
                    self.serial_connection.write(bytes([27]))  # ESC - zruší AT+CMGS
                    raise ModemError('Timeout čekání na prompt AT+CMGS (modem nepřipravený)')

                time.sleep(0.1)
                self.serial_connection.write(pdu_hex.encode('ascii'))
                self.serial_connection.write(bytes([26]))  # Ctrl+Z

                started = time.time()
                while time.time() - started < 30.0:
                    raw = self.serial_connection.readline()
                    if not raw:
                        continue
                    line = raw.decode(errors='ignore').strip()
                    if not line or _is_unsolicited(line):
                        continue
                    if line == 'OK':
                        return
                    if '+CMGS:' in line:
                        continue
                    if line.startswith('ERROR') or '+CMS ERROR:' in line:
                        raise ModemError(f'Chyba odeslání SMS: {line}')
                raise ModemError('Timeout při odesílání SMS')
            except (serial.SerialException, OSError) as e:
                raise ModemError(f'Chyba sériové komunikace při odesílání SMS: {e}') from e
        finally:
            self.send_at('AT+CMGF=1')

    def read_unread_sms(self) -> List[IncomingSms]:
        self.send_at('AT+CSCS="UCS2"')
        try:
            output = self.send_at('AT+CMGL="REC UNREAD"', timeout=6)
        finally:
            self.send_at('AT+CSCS="GSM"')
        lines = [line for line in output.splitlines() if line and line != 'OK']

        messages: List[IncomingSms] = []
        current_index = None
        current_sender = None

        for line in lines:
            if line.startswith('+CMGL:'):
                match = re.match(r'\+CMGL:\s*(\d+),"[^"]*","([^"]*)"', line)
                if match:
                    current_index = int(match.group(1))
                    current_sender = _ucs2_decode(match.group(2))
                else:
                    current_index = None
                    current_sender = None
            else:
                if current_index is not None and current_sender is not None:
                    messages.append(IncomingSms(
                        index=current_index,
                        sender=current_sender,
                        message=_ucs2_decode(line),
                    ))
                    current_index = None
                    current_sender = None

        return messages

    def delete_sms(self, index: int):
        self.send_at(f'AT+CMGD={index}')

    def get_signal_quality(self) -> Optional[int]:
        response = self.send_at('AT+CSQ')
        match = re.search(r'\+CSQ:\s*(\d+),\d+', response)
        if not match:
            return None
        return int(match.group(1))
