# scripts/README

This folder contains helper scripts for the project.

## plex_metadata_extract.py

Purpose: Scan a directory of audio files (FLAC/MP3), group tracks by Album and Artist, and export a JSON file containing the album name, artist name, a unique list of genres found on the album, and the track count.

Dependencies:

- Python 3.8+
- mutagen — install with `pip install mutagen`

Usage:

```bash
pip install mutagen
python3 scripts/plex_metadata_extract.py --root /path/to/music --output albums.json
```

Output sample (each entry):

```json
[
  {
    "album": "Discovery",
    "artist": "Daft Punk",
    "current_genres": ["French House", "EDM", "Dance"],
    "tracks": 14,
    "suggested_group": null,
    "suggested_subgenre": null
  }
]
```

Notes:

- The script falls back to `Unknown Album` / `Unknown Artist` when tags are missing.
- Genre tags may be split on common separators (`,`, `;`, `/`, `|`).
# Backup script usage and scheduling

- **Script:** [scripts/backup.sh](scripts/backup.sh)
- **Purpose:** create timestamped tar.gz archives of critical non-git data (by default `db/` and `adb-keys/`) and optional external memories.

Usage examples:

1. Run once (default backup dir):

```bash
bash scripts/backup.sh
```

2. Back up a custom memories folder and change retention:

```bash
MEMORIES_PATH=/mnt/c/Users/you/memories BACKUP_DIR=/path/to/backups KEEP_LAST=30 bash scripts/backup.sh
```

Scheduling options (pick one):

- Cron (inside WSL or on a Linux host):

```
# daily at 02:30
30 2 * * * /home/youruser/plex_playlist/scripts/backup.sh >> /home/youruser/plex_playlist/scripts/backup.log 2>&1
```

To install the cron entry for the current user automatically, run:

```bash
# optionally override schedule, default is 30 2 * * * (02:30)
CRON_SCHEDULE="30 2 * * *" bash scripts/install_backup_cron.sh
```

There's also a sample cron file at [scripts/backup.cron](scripts/backup.cron).

Systemd user timer (preferred on Linux with systemd):

1. Copy the unit files to your user systemd directory:

```bash
mkdir -p ~/.config/systemd/user
cp scripts/systemd/backup.service scripts/systemd/backup.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now backup.timer
```

2. Check timer status and next run:

```bash
systemctl --user list-timers --all | grep backup
journalctl --user -u backup.service
```

Note: WSL without systemd cannot use `systemctl --user`; use the cron installer or Windows Task Scheduler instead.

- systemd user timer (preferred on systems with systemd): create a `backup.service` and `backup.timer` in your `~/.config/systemd/user/` and enable the timer. Note: WSL may not have systemd enabled.

- Windows Task Scheduler (when using WSL without systemd): create a task that runs `wsl -d <distro> -- /home/youruser/plex_playlist/scripts/backup.sh` on a daily schedule.

- GitHub Actions / remote backups: for off-host retention you can add a workflow to upload backups to S3 or another remote store. Avoid committing sensitive keys to the repo.

Security notes:

- The script stores backups locally by default. If you configure remote sync (S3, rsync, etc.), store credentials outside the repo (environment variables or secret manager).
- Review what you include in backups. `db/` and `adb-keys/` typically contain sensitive material that should be protected and encrypted if sent off-host.
