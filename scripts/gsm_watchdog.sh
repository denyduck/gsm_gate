#!/bin/bash
# GSM modem watchdog.
#
# Kontroluje stav modemu přes ModemManager (mmcli). Eskalace podle toho,
# jak dlouho je modem nepřetržitě nezdravý (stav jiný než "registered"/
# "connected"), každá akce se spustí jen jednou za epizodu (ne při každém
# běhu timeru), ať se neopakuje zbytečně:
#
#   1) RESTART_THRESHOLD   -> restart ModemManageru
#   2) USB_RESET_THRESHOLD -> logický USB reset modemu (unbind/bind) - řeší
#      i zaseknutý firmware modemu, který samotný restart ModemManageru
#      nespraví (reálný incident 2026-09-11, viz docs/modem-diagnostika.md)
#   3) REBOOT_THRESHOLD    -> reboot celé RPi
#
# Nasazení: viz scripts/gsm-watchdog.service + scripts/gsm-watchdog.timer

set -euo pipefail

STATE_DIR="/var/tmp"
SINCE_FILE="$STATE_DIR/gsm_watchdog_unhealthy_since"
MM_RESTARTED_FILE="$STATE_DIR/gsm_watchdog_mm_restarted"
USB_RESET_FILE="$STATE_DIR/gsm_watchdog_usb_reset"

RESTART_THRESHOLD=300     # 5 min nezdravého stavu -> restart ModemManager
USB_RESET_THRESHOLD=600   # 10 min -> logický USB reset modemu
REBOOT_THRESHOLD=1200     # 20 min -> reboot RPi

now=$(date +%s)

# Modem index se zjišťuje dynamicky přes mmcli -L, ne hardcoded - po USB
# resetu nebo restartu ModemManageru se může změnit (viděno v praxi:
# 0 -> 1), natvrdo zadaný index by časem přestal fungovat.
modem_path=$(mmcli -L 2>/dev/null | grep -o '/org/freedesktop/ModemManager1/Modem/[0-9]\+' | head -n1 || echo "")

state=""
device_path=""
if [ -n "$modem_path" ]; then
    modem_index=$(basename "$modem_path")
    detail=$(mmcli -m "$modem_index" -J 2>/dev/null || echo "")
    state=$(echo "$detail" | python3 -c "import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get('modem', {}).get('generic', {}).get('state', ''))
except Exception:
    print('')" 2>/dev/null || echo "")
    device_path=$(echo "$detail" | python3 -c "import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get('modem', {}).get('generic', {}).get('device', ''))
except Exception:
    print('')" 2>/dev/null || echo "")
fi

if [ "$state" = "registered" ] || [ "$state" = "connected" ]; then
    rm -f "$SINCE_FILE" "$MM_RESTARTED_FILE" "$USB_RESET_FILE"
    exit 0
fi

logger -t gsm_watchdog "Modem nezdravý (stav: '${state:-neznámý}')"

if [ ! -f "$SINCE_FILE" ]; then
    echo "$now" > "$SINCE_FILE"
    exit 0
fi

unhealthy_since=$(cat "$SINCE_FILE")
duration=$((now - unhealthy_since))

if [ "$duration" -ge "$REBOOT_THRESHOLD" ]; then
    logger -t gsm_watchdog "Modem nezdravý $duration s, restartuji RPi"
    rm -f "$SINCE_FILE" "$MM_RESTARTED_FILE" "$USB_RESET_FILE"
    /sbin/reboot
    exit 0
fi

if [ "$duration" -ge "$USB_RESET_THRESHOLD" ] && [ ! -f "$USB_RESET_FILE" ]; then
    usb_port=$(basename "$device_path" 2>/dev/null || echo "")
    if [ -n "$usb_port" ] && [ -e "/sys/bus/usb/drivers/usb/$usb_port" ]; then
        logger -t gsm_watchdog "Modem nezdravý $duration s, zkouším logický USB reset ($usb_port)"
        echo "$usb_port" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
        sleep 3
        echo "$usb_port" > /sys/bus/usb/drivers/usb/bind 2>/dev/null || true
    else
        logger -t gsm_watchdog "Modem nezdravý $duration s, USB reset přeskočen - cesta zařízení se nepodařila zjistit"
    fi
    touch "$USB_RESET_FILE"
    exit 0
fi

if [ "$duration" -ge "$RESTART_THRESHOLD" ] && [ ! -f "$MM_RESTARTED_FILE" ]; then
    logger -t gsm_watchdog "Modem nezdravý $duration s, restartuji ModemManager"
    systemctl restart ModemManager
    touch "$MM_RESTARTED_FILE"
fi
