#!/usr/bin/env bash
set -euo pipefail

# Simple backup script for critical non-git data in this repository.
# - Creates timestamped tar.gz archives in BACKUP_DIR (default: $HOME/plex_playlist_backups)
# - Backs up repository `db/` and `adb-keys/` by default. Add MEMORIES_PATH to include external memories.
# - Keeps at most KEEP_LAST backups (default 14).

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR=${BACKUP_DIR:-"$HOME/plex_playlist_backups"}
KEEP_LAST=${KEEP_LAST:-14}
MEMORIES_PATH=${MEMORIES_PATH:-""}

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
OUT_FILE="$BACKUP_DIR/plex_playlist-backup-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "Creating backup: $OUT_FILE"

declare -a PATHS_TO_BACKUP
PATHS_TO_BACKUP=("$REPO_ROOT/db" "$REPO_ROOT/adb-keys")

if [[ -n "$MEMORIES_PATH" ]]; then
  PATHS_TO_BACKUP+=("$MEMORIES_PATH")
fi

# Verify paths exist and build tar args
TAR_ARGS=()
for p in "${PATHS_TO_BACKUP[@]}"; do
  if [[ -e "$p" ]]; then
    TAR_ARGS+=("-C" "$(dirname "$p")" "$(basename "$p")")
  else
    echo "Warning: path does not exist, skipping: $p"
  fi
done

if [[ ${#TAR_ARGS[@]} -eq 0 ]]; then
  echo "No files to back up. Exiting." >&2
  exit 2
fi

tar -czf "$OUT_FILE" "${TAR_ARGS[@]}"

echo "Backup written to $OUT_FILE"

# Update 'latest' symlink
ln -sfn "$(basename "$OUT_FILE")" "$BACKUP_DIR/latest"

# Rotate old backups
cd "$BACKUP_DIR"
ls -1t plex_playlist-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_LAST+1)) | xargs -r rm -f --

echo "Rotation: kept last $KEEP_LAST backups in $BACKUP_DIR"

exit 0
