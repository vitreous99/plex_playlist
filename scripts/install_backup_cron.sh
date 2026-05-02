#!/usr/bin/env bash
set -euo pipefail

# Installs a cron entry for scripts/backup.sh for the current user.
# Usage: CRON_SCHEDULE="30 2 * * *" bash scripts/install_backup_cron.sh

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_SCRIPT="$REPO_ROOT/scripts/backup.sh"
LOG_FILE="$REPO_ROOT/scripts/backup.log"

CRON_SCHEDULE=${CRON_SCHEDULE:-"30 2 * * *"}

CRON_LINE="$CRON_SCHEDULE $BACKUP_SCRIPT >> $LOG_FILE 2>&1"

echo "Installing cron entry: $CRON_LINE"

# Read existing crontab
EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -F "$BACKUP_SCRIPT" >/dev/null; then
  echo "A cron entry for $BACKUP_SCRIPT already exists. No changes made."
  exit 0
fi

# Append the new line and install
{
  echo "$EXISTING"
  echo "# plex_playlist automated backup"
  echo "$CRON_LINE"
} | crontab -

echo "Cron entry installed. Use 'crontab -l' to verify."

exit 0
