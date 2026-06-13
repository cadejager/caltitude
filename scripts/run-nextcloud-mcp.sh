#!/bin/sh
# Launch the bundled Nextcloud MCP server (stdio).
#
# The plugin's .mcp.json points its `command` at this script and supplies
# NEXTCLOUD_HOST / NEXTCLOUD_USERNAME / NEXTCLOUD_PASSWORD from the plugin's
# userConfig (the password is stored in the OS keychain). This script just has to
# find `uvx` and exec the server — locating uvx explicitly because a scheduled /
# headless run often does NOT have ~/.local/bin on PATH.

# Try the common install locations first, then fall back to PATH.
for candidate in \
    "$HOME/.local/bin/uvx" \
    "/opt/homebrew/bin/uvx" \
    "/usr/local/bin/uvx" \
    "/home/linuxbrew/.linuxbrew/bin/uvx"; do
    if [ -x "$candidate" ]; then
        exec "$candidate" nextcloud-mcp-server run --transport stdio
    fi
done

if command -v uvx > /dev/null 2>&1; then
    exec uvx nextcloud-mcp-server run --transport stdio
fi

# uvx not found — actionable error, non-zero exit so the failure is visible.
echo "caltitude: 'uvx' was not found, so the bundled Nextcloud server can't start." >&2
echo "Install uv (which provides uvx) and re-run:" >&2
echo "  curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux" >&2
echo "  brew install uv                                   # Homebrew" >&2
echo "See https://docs.astral.sh/uv/getting-started/installation/" >&2
exit 1
