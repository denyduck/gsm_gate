#!/bin/bash
# Provede logický USB reset GSM modemu na vyžádání appky.
#
# Appka (dashboard.views.gateway_modem_reset_request) zapíše "sentinel"
# soubor FLAG_FILE (v bind-mountnutém django_app/tmp/, takže se objeví i
# na hostu). Tenhle skript se spouští přes gsm-modem-reset.path (systemd
# path-unit hlídající existenci FLAG_FILE), takže reaguje prakticky
# okamžitě, ne až při dalším běhu watchdogu.
#
# Recept na USB reset (unbind/bind) je stejný jako v gsm_watchdog.sh -
# viz docs/modem-diagnostika.md, incident 2026-09-11.
#
# Nasazení: viz scripts/gsm-modem-reset.service + scripts/gsm-modem-reset.path

set -euo pipefail

FLAG_FILE="/usr/src/app/gsm_gate/django_app/tmp/gsm_modem_reset_requested"

if [ ! -f "$FLAG_FILE" ]; then
    exit 0
fi

# Smazat hned na začátku - i kdyby reset selhal, ať appka může poslat
# nový požadavek a path-unit na něj zareaguje znovu (potřebuje přechod
# neexistuje -> existuje, ne jen zápis do už existujícího souboru).
rm -f "$FLAG_FILE"

logger -t gsm_modem_reset "Ruční reset modemu vyžádán z appky, hledám USB cestu..."

modem_path=$(mmcli -L 2>/dev/null | grep -o '/org/freedesktop/ModemManager1/Modem/[0-9]\+' | head -n1 || echo "")

if [ -z "$modem_path" ]; then
    logger -t gsm_modem_reset "ModemManager nevidí žádný modem, USB reset nelze provést."
    exit 0
fi

modem_index=$(basename "$modem_path")
device_path=$(mmcli -m "$modem_index" -J 2>/dev/null | python3 -c "import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get('modem', {}).get('generic', {}).get('device', ''))
except Exception:
    print('')" 2>/dev/null || echo "")

usb_port=$(basename "$device_path" 2>/dev/null || echo "")

if [ -z "$usb_port" ] || [ ! -e "/sys/bus/usb/drivers/usb/$usb_port" ]; then
    logger -t gsm_modem_reset "Nepodařilo se zjistit USB cestu modemu, reset přeskočen."
    exit 0
fi

logger -t gsm_modem_reset "Provádím logický USB reset ($usb_port)..."
echo "$usb_port" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
sleep 3
echo "$usb_port" > /sys/bus/usb/drivers/usb/bind 2>/dev/null || true
logger -t gsm_modem_reset "USB reset dokončen ($usb_port)."
