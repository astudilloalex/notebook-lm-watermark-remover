#!/bin/sh
HERE="$(CDPATH= cd -- "${0%/*}/../Resources" && pwd)" || exit 1
exec "$HERE/runtime/bin/python3" -I "$HERE/app/desktop_entry.py" "$@"
