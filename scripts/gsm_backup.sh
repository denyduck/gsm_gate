#!/bin/bash
# Spustí export_backup uvnitř běžícího "web" kontejneru a smaže zálohy
# starší než RETENTION_DAYS. Výstup přistane v django_app/backups/ na
# hostu (bind mount ./django_app:/usr/src/app). Pokud je NAS_MOUNT_DIR
# připojený síťový disk (CIFS/SMB, viz docs/nasazeni-a-obnova.md), navíc
# se tam zálohy zkopírují - lokální kopie zůstává i když je NAS zrovna
# nedostupný, tohle je jen doplněk, ne náhrada.
#
# Nasazení: viz scripts/gsm-backup.service + scripts/gsm-backup.timer

set -euo pipefail

REPO_DIR="/usr/src/app/gsm_gate"
RETENTION_DAYS=14
NAS_MOUNT_DIR="/mnt/zaloha"

cd "$REPO_DIR"

/usr/bin/docker compose exec -T web python manage.py export_backup --kind data --output-dir /usr/src/app/backups

find "$REPO_DIR/django_app/backups" -name 'gsm_gate_*_backup_*.json' -mtime "+${RETENTION_DAYS}" -delete

if mountpoint -q "$NAS_MOUNT_DIR"; then
    rsync -a "$REPO_DIR/django_app/backups/" "$NAS_MOUNT_DIR/" \
        || echo "VAROVÁNÍ: rsync zálohy na $NAS_MOUNT_DIR selhal, lokální záloha je v pořádku." >&2
else
    echo "VAROVÁNÍ: $NAS_MOUNT_DIR není připojený, síťová kopie zálohy se přeskočila." >&2
fi
