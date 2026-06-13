#!/bin/sh
# Load Nextcloud credentials.
# This is shipped as a *plugin*, which does NOT render the MCPB-style "userConfig"
# settings form, so the ${user_config.*} values wired into .mcp.json arrive empty.
# When NEXTCLOUD_HOST is empty, fall back to a local env file the user controls.
# This path also works for scheduled runs (no desktop UI is involved at launch).
# Override the location with CALTITUDE_ENV_FILE if desired.
CRED_FILE="${CALTITUDE_ENV_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/caltitude/nextcloud.env}"
if [ -z "$NEXTCLOUD_HOST" ] && [ -f "$CRED_FILE" ]; then
    # shellcheck disable=SC1090
    . "$CRED_FILE"
    export NEXTCLOUD_HOST NEXTCLOUD_USERNAME NEXTCLOUD_PASSWORD
fi

# Locate uvx — tries the official uv installer location first, then Homebrew, then PATH
for candidate in \
    "$HOME/.local/bin/uvx" \
    "/opt/homebrew/bin/uvx" \
    "/usr/local/bin/uvx" \
    "/home/linuxbrew/.linuxbrew/bin/uvx"; do
    if [ -x "$candidate" ]; then
        exec "$candidate" nextcloud-mcp-server run --transport stdio
    fi
done

# Fall back to uvx on PATH if found
if command -v uvx > /dev/null 2>&1; then
    exec uvx nextcloud-mcp-server run --transport stdio
fi

# uvx not found — print actionable error and exit
echo "Error: 'uvx' was not found in any expected location." >&2
echo "Install uv (which provides uvx) from: https://docs.astral.sh/uv/getting-started/installation/" >&2
echo "  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
echo "  Homebrew:    brew install uv" >&2
exit 1
