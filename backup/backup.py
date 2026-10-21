import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

discord_hook = os.environ["DISCORD_WEBHOOK"]
compose_dir = "/opt/code_arena/infra"
backup_dir = Path("/var/backups/codearena")
db_user = os.environ["POSTGRES_USER"]
db_name = os.environ["POSTGRES_DB"]
max_backups = 14

backup_cmd = [
    "docker", "compose", "exec", "-T", "db",
    "pg_dump", "-U", db_user, "-d", db_name,
]


def notify_discord(message: str) -> None:
    print(message)
    try:
        body = json.dumps({"content": message[:1900]}).encode()
        discord_req = urllib.request.Request(
            discord_hook,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "codearena-backup"},
        )
        urllib.request.urlopen(discord_req, timeout=10)
    except Exception as e:
        print(f"discord notification failed: {e}")


def remove_old_backups() -> None:
    backups = sorted(backup_dir.glob("codearena-*.sql"))
    for old in backups[:-max_backups]:
        old.unlink()


def main() -> None:
    os.umask(0o077)

    if shutil.disk_usage(backup_dir).free < 500 * 1024 * 1024:
        notify_discord("backup failed: less than 500 MB free on disk")
        sys.exit(1)

    backup_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_file_path = backup_dir / f"codearena-{backup_time}.sql"

    with open(backup_file_path, "wb") as backup_file:
        try:
            result = subprocess.run(backup_cmd, cwd=compose_dir, stdout=backup_file, stderr=subprocess.PIPE, check=False, timeout=300)
        except subprocess.TimeoutExpired:
            backup_file_path.unlink()
            notify_discord("backup failed: pg_dump timed out after 5 minutes")
            sys.exit(1)

    if result.returncode != 0:
        backup_file_path.unlink()  
        error = result.stderr.decode().strip()
        notify_discord(f"backup failed:\n{error[-500:]}")
        sys.exit(1)

    remove_old_backups()
    notify_discord(f"backup succeeded: {backup_file_path.name}")


if __name__ == "__main__":
    main()