#!/bin/sh
# Runtime and import path come only from the root-owned installed unit.
set -eu
umask 077
: "${CREDENTIALS_DIRECTORY:?systemd credentials required}"
: "${PEERLY_BACKUP_PYTHON:?root-owned Python runtime required}"
exec 3<"$CREDENTIALS_DIRECTORY/plan"
exec 4<"$CREDENTIALS_DIRECTORY/source-request"
exec 5<"$CREDENTIALS_DIRECTORY/pgpass"
exec 6<"$CREDENTIALS_DIRECTORY/rclone"
if [ -r "$CREDENTIALS_DIRECTORY/pg-ca" ]; then
  exec 7<"$CREDENTIALS_DIRECTORY/pg-ca"
  exec "$PEERLY_BACKUP_PYTHON" -s -B -m deployment.backup.run_backup \
    --plan-fd 3 --source-fd 4 --pgpass-fd 5 --rclone-fd 6 --ca-fd 7
fi
exec "$PEERLY_BACKUP_PYTHON" -s -B -m deployment.backup.run_backup \
  --plan-fd 3 --source-fd 4 --pgpass-fd 5 --rclone-fd 6
