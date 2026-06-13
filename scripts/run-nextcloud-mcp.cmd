@echo off
REM Launch the bundled Nextcloud MCP server (stdio) on Windows.
REM .mcp.json supplies NEXTCLOUD_HOST/USERNAME/PASSWORD from the plugin userConfig;
REM this script just locates uvx and execs the server.

where uvx >nul 2>nul
if %ERRORLEVEL%==0 (
    uvx nextcloud-mcp-server run --transport stdio
    exit /b %ERRORLEVEL%
)

if exist "%USERPROFILE%\.local\bin\uvx.exe" (
    "%USERPROFILE%\.local\bin\uvx.exe" nextcloud-mcp-server run --transport stdio
    exit /b %ERRORLEVEL%
)

echo caltitude: 'uvx' was not found, so the bundled Nextcloud server can't start. 1>&2
echo Install uv (which provides uvx): https://docs.astral.sh/uv/getting-started/installation/ 1>&2
exit /b 1
