#!/bin/sh
# Root-owned non-writable forced command; no caller command evaluation.
exec /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/var/lib/peerly-release-ssh \
  SSH_ORIGINAL_COMMAND="${SSH_ORIGINAL_COMMAND-}" SSH_TTY="${SSH_TTY-}" \
  /usr/bin/python3 -I /opt/peerly-release-ssh/broker.py
