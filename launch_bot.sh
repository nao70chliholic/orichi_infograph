#!/bin/sh

# Launch wrapper for Orochi Infograph bot.
# This shell wrapper ensures the virtual environment Python symlink is executed
# correctly under launchd.

cd "$(dirname "$0")"

VIRTUAL_ENV="$(pwd)/.venv"
export VIRTUAL_ENV
export PATH="$VIRTUAL_ENV/bin:$PATH"

# Use python3 explicitly to ensure correct Python version
exec "$VIRTUAL_ENV/bin/python3" "$(pwd)/bot/main.py"
