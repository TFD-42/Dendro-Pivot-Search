#!/bin/sh
# DendroPivot — lanceur POSIX (Linux, macOS, Android/Termux).
# Transmet tous les arguments à launcher.py (ex. : ./run.sh --check).
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            exec "$candidate" "$DIR/launcher.py" "$@"
        fi
    fi
done
echo "Python 3.10+ introuvable." >&2
if [ -n "${TERMUX_VERSION:-}" ]; then
    echo "Termux : pkg install python" >&2
elif [ "$(uname -s)" = "Darwin" ]; then
    echo "macOS : brew install python  (ou https://www.python.org/downloads/)" >&2
else
    echo "Linux : installez python3 via le gestionnaire de paquets de la distribution." >&2
fi
exit 1
