#!/bin/sh
# Launch the bundled caltitude overflow-reader MCP server (stdio, pure stdlib).
# Locate a Python 3 interpreter, then exec the server.
for candidate in python3 python; do
    if command -v "$candidate" > /dev/null 2>&1; then
        exec "$candidate" "$(dirname "$0")/overflow_reader.py"
    fi
done
echo "caltitude: no python3 found to run the overflow reader." >&2
exit 1
