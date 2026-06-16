#!/bin/sh

# Launch wrapper for Orochi Infograph bot.
# This shell wrapper ensures the virtual environment Python symlink is executed
# correctly under launchd.

cd "$(dirname "$0")"

VIRTUAL_ENV="$(pwd)/.venv"
export VIRTUAL_ENV
export PATH="$VIRTUAL_ENV/bin:$PATH"

exec "$VIRTUAL_ENV/bin/python" "$(pwd)/bot/main.py"
