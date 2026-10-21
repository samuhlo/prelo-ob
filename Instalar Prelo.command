#!/bin/sh
set -eu
PRELO_PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v uv >/dev/null 2>&1; then
  echo 'Instala uv primero: brew install uv'
  echo 'También necesitas Docker Desktop o Colima ya iniciado.'
  echo 'Guía: https://github.com/samuhlo/prelo-ob/blob/main/docs/instalacion.md'
  exit 1
fi
exec uv run --no-project --python 3.13 python "$PRELO_PACKAGE_DIR/scripts/install.py" "$@"
