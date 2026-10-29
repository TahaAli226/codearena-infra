# How Backups Work In This Project
- `backup.py` is triggered daily by a systemd timer and backs up the project's DB with `pg_dump` to `/var/backups/codearena`.
  Directory and file permissions are 700/600 because the backups contain sensitive data.

- Backups are named after the time they were created. Only the 14 newest are kept; the oldest is deleted when a new one is made.
  Do not add backup files manually: the cleanup relies on the file names.

- Discord notifications are sent for both successful and failed backups. A backup fails on:
  a timeout, less than 500 MB of free disk space (so the dump can't fill the disk and take Postgres down), or a non-zero return code.

- Off-site copy: pulled manually to the admin's PC over SSH.
  Future work: encrypted off-site backups, with the key kept in a secret manager.


# How To Restore From a Backup
- Do a test restore of the chosen backup before restoring in production.
- Anything written after the last backup is lost on restore.
- Backup files are on lab07 in `/var/backups/codearena/` (owned by `student`, mode 700).

## Test Restore
```bash
# start a throwaway postgres container, same version as prod
docker run -d --name restore-test --network none -e POSTGRES_PASSWORD=x postgres:17-alpine

# wait for postgres to finish starting
sleep 5

# create the db user (same name as prod, so the ownership lines in the dump match)
docker exec restore-test createuser -U postgres codearena

# create an empty database owned by that user
docker exec restore-test createdb -U postgres -O codearena restoretest

# load the backup, stopping at the first error (replace with the actual file name)
docker exec -i restore-test psql -v ON_ERROR_STOP=1 -U postgres -d restoretest < codearena-YYYYMMDDTHHMMSSZ.sql

# check the main table counts
docker exec restore-test psql -U postgres -d restoretest -c \
  "select (select count(*) from users) as users,
          (select count(*) from problems) as problems,
          (select count(*) from test_cases) as test_cases,
          (select count(*) from submissions) as submissions;"

# delete the test container
docker rm -f restore-test
```

## Production Restore
Run from `/opt/code_arena/infra` as `student`.
```bash
# pause auto deploys
sudo systemctl stop codearena-deploy.timer

# stop the api so nothing writes to the db during the restore
docker compose stop api

# if the db still works, take a safety dump first (outside the backup dir)
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > ~/pre-restore-$(date -u +%Y%m%dT%H%M%SZ).sql

# drop the database and create it again, empty
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"'

# load the backup, stopping at the first error (replace with the actual file name)
# if this fails: drop/create again and load ~/pre-restore-*.sql the same way
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < /var/backups/codearena/codearena-YYYYMMDDTHHMMSSZ.sql

# start the api again
# on start it runs `alembic upgrade head`, bringing an older backup up to the current schema.
# if it won't start, the backup is probably from a newer image than the one running: deploy the matching image.
docker compose start api

# check the main table counts
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
  select (select count(*) from users) as users,
         (select count(*) from problems) as problems,
         (select count(*) from test_cases) as test_cases,
         (select count(*) from submissions) as submissions;"'

# resume auto deploys
sudo systemctl start codearena-deploy.timer
```