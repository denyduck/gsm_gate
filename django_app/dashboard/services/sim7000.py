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


_TRANSLITERATE = str.maketrans({
    'á': 'a', 'č': 'c', 'ď': 'd', 'é': 'e', 'ě': 'e',
    'í': 'i', 'ň': 'n', 'ó': 'o', 'ř': 'r', 'š': 's',
    'ť': 't', 'ú': 'u', 'ů': 'u', 'ý': 'y', 'ž': 'z',
    'Á': 'A', 'Č': 'C', 'Ď': 'D', 'É': 'E', 'Ě': 'E',
    'Í': 'I', 'Ň': 'N', 'Ó': 'O', 'Ř': 'R', 'Š': 'S',
    'Ť': 'T', 'Ú': 'U', 'Ů': 'U', 'Ý': 'Y', 'Ž': 'Z',
})


def _to_gsm(text: str) -> bytes:
    return text.translate(_TRANSLITERATE).encode('ascii', errors='replace')


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
        self.serial_connection = serial.Serial(
            self.port, self.baudrate, timeout=self.timeout,
            rtscts=False, dsrdtr=False,
        )
        last_error = None
        for _ in range(5):
            time.sleep(2.0)
            try:
                self.initialize_modem()
                return
            except ModemError as e:
                last_error = e
                self.serial_connection.reset_input_buffer()
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
        self.serial_connection.reset_input_buffer()
        self.serial_connection.write(f'{command}\r'.encode('ascii'))

        started = time.time()
        output_lines = []
        while time.time() - started < effective_timeout:
            raw = self.serial_connection.readline()
            if not raw:
                continue
            line = raw.decode(errors='ignore').strip()
            if not line:
                continue
            output_lines.append(line)
            if line == 'OK':
                return '\n'.join(output_lines)
            if line.startswith('ERROR'):
                raise ModemError(f'AT chyba ({command}): {line}')

        raise ModemError(f'AT timeout ({command})')

    def send_sms(self, phone_number: str, text: str):
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ModemError('Modem není připojen.')

        self.serial_connection.reset_input_buffer()
        self.serial_connection.write(f'AT+CMGS="{phone_number}"\r'.encode('ascii'))

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
        self.serial_connection.write(_to_gsm(text))
        self.serial_connection.write(bytes([26]))  # Ctrl+Z

        started = time.time()
        while time.time() - started < 30.0:
            raw = self.serial_connection.readline()
            if not raw:
                continue
            line = raw.decode(errors='ignore').strip()
            if not line:
                continue
            if line == 'OK':
                return
            if '+CMGS:' in line:
                continue
            if line.startswith('ERROR') or '+CMS ERROR:' in line:
                raise ModemError(f'Chyba odeslání SMS: {line}')
        raise ModemError('Timeout při odesílání SMS')

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
