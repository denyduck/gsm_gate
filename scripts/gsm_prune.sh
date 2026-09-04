#!/bin/bash
# Spustí prune_old_data uvnitř běžícího "web" kontejneru - maže staré
# IncomingEventLog/OutgoingAction/SignalReading podle retenční politiky
# (RETENTION_DAYS_LOGS/RETENTION_DAYS_SIGNAL_HISTORY v .env, výchozí 90/30 dní).
#
# Nasazení: viz scripts/gsm-prune.service + scripts/gsm-prune.timer

set -euo pipefail

REPO_DIR="/usr/src/app/gsm_gate"

cd "$REPO_DIR"

/usr/bin/docker compose exec -T web python manage.py prune_old_data
