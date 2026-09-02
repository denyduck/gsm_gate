#!/bin/bash
# GSM modem watchdog.
#
# Kontroluje stav modemu přes ModemManager (mmcli). Pokud modem není
# registrovaný v síti déle než RESTART_THRESHOLD sekund, restartuje se
# služba ModemManager. Pokud to nepomůže a stav zůstane špatný déle než
# REBOOT_THRESHOLD sekund, restartuje se celá RPi.
#
# Nasazení: viz scripts/gsm-watchdog.service + scripts/gsm-watchdog.timer

set -euo pipefail

MODEM_INDEX=0
STATE_FILE="/var/tmp/gsm_watchdog_unhealthy_since"
RESTART_THRESHOLD=300   # 5 min nezdravého stavu -> restart ModemManager
REBOOT_THRESHOLD=900    # 15 min nezdravého stavu -> reboot RPi

now=$(date +%s)

state=$(mmcli -m "$MODEM_INDEX" -J 2>/dev/null \
    | python3 -c "import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get('modem', {}).get('generic', {}).get('state', ''))
except Exception:
    print('')" 2>/dev/null || echo "")

if [ "$state" = "registered" ] || [ "$state" = "connected" ]; then
    rm -f "$STATE_FILE"
    exit 0
fi

logger -t gsm_watchdog "Modem nezdravý (stav: '${state:-neznámý}')"

if [ ! -f "$STATE_FILE" ]; then
    echo "$now" > "$STATE_FILE"
    exit 0
fi

unhealthy_since=$(cat "$STATE_FILE")
duration=$((now - unhealthy_since))

if [ "$duration" -ge "$REBOOT_THRESHOLD" ]; then
    logger -t gsm_watchdog "Modem nezdravý $duration s, restartuji RPi"
    rm -f "$STATE_FILE"
    /sbin/reboot
elif [ "$duration" -ge "$RESTART_THRESHOLD" ]; then
    logger -t gsm_watchdog "Modem nezdravý $duration s, restartuji ModemManager"
    systemctl restart ModemManager
fi
