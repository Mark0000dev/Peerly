#!/bin/sh
# Only systemd's explicit credential files are opened. No values/paths are passed as argv.
set -eu
umask 077
: "${CREDENTIALS_DIRECTORY:?systemd credentials required}"
exec 3<"$CREDENTIALS_DIRECTORY/plan"
exec 4<"$CREDENTIALS_DIRECTORY/source-request"
exec 5<"$CREDENTIALS_DIRECTORY/pgpass"
exec 6<"$CREDENTIALS_DIRECTORY/rclone"
if [ -r "$CREDENTIALS_DIRECTORY/pg-ca" ]; then
  exec 7<"$CREDENTIALS_DIRECTORY/pg-ca"
  exec /usr/bin/python3 -B -m deployment.backup.run_backup \
    --plan-fd 3 --source-fd 4 --pgpass-fd 5 --rclone-fd 6 --ca-fd 7
fi
exec /usr/bin/python3 -B -m deployment.backup.run_backup \
  --plan-fd 3 --source-fd 4 --pgpass-fd 5 --rclone-fd 6
