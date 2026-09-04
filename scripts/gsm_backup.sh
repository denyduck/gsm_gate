#!/bin/bash
# Spustí export_backup uvnitř běžícího "web" kontejneru a smaže zálohy
# starší než RETENTION_DAYS. Výstup přistane v django_app/backups/ na
# hostu (bind mount ./django_app:/usr/src/app), odtud si ho synchronizuj
# tam, kam potřebuješ (rsync/rclone/cloud sync).
#
# Nasazení: viz scripts/gsm-backup.service + scripts/gsm-backup.timer

set -euo pipefail

REPO_DIR="/usr/src/app/gsm_gate"
RETENTION_DAYS=14

cd "$REPO_DIR"

/usr/bin/docker compose exec -T web python manage.py export_backup --kind data --output-dir /usr/src/app/backups

find "$REPO_DIR/django_app/backups" -name 'gsm_gate_*_backup_*.json' -mtime "+${RETENTION_DAYS}" -delete
