#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
(cd frontend && npm run check)
(cd backend && make check)
