<#
install.ps1
PowerShell install script for SQLite MCP from clean VS Code Insiders + git repo state.
Usage (from repo root):
  .\install.ps1
#>

$ErrorActionPreference = 'Stop'
Write-Host "=== SQLite MCP install script started ==="

# Ensure we are in repo root (containing pyproject.toml)
$scriptPath = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
Set-Location $scriptPath

if (-Not (Test-Path pyproject.toml)) {
    Write-Error "pyproject.toml not found. Run this script from project root."
    exit 1
}

# Git initialize if needed
if (-Not (Test-Path .git)) {
    Write-Host "Initializing git repository..."
    git init
} else {
    Write-Host "Git repository already initialized."
}

# Create virtual environment
if (-Not (Test-Path .venv)) {
    Write-Host "Creating Python virtual environment in .venv..."
    python -m venv .venv
} else {
    Write-Host ".venv already exists, skipping creation."
}

# Activate
$activateScript = Join-Path $PWD '.venv\Scripts\Activate.ps1'
if (-Not (Test-Path $activateScript)) {
    Write-Error "Activation script not found at $activateScript"
    exit 1
}

Write-Host "Activating virtual environment..."
. $activateScript

Write-Host "Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -e .

Write-Host "Bootstrapping project memory..."
sqlite-project-memory-admin bootstrap-self --repo-root .

Write-Host "Running health checks..."
sqlite-project-memory-admin project-state
$sqliteProjectMemoryAdmin = Get-Command sqlite-project-memory-admin -ErrorAction SilentlyContinue
if ($null -eq $sqliteProjectMemoryAdmin) {
    Write-Error "sqlite-project-memory-admin command not found after install."
    exit 1
}

sqlite-project-memory-admin health

# Add or update MCP user config entry in mcp.json (Code Insiders)
$mcpConfigPath = Join-Path $env:APPDATA 'Code - Insiders\User\mcp.json'
if (-Not (Test-Path $mcpConfigPath)) {
    Write-Host "mcp.json not found at $mcpConfigPath; creating new file."
    $mcp = [pscustomobject]@{ servers = @{}; inputs = @(); } | ConvertTo-Json -Depth 10 | ConvertFrom-Json
} else {
    $mcp = Get-Content -Path $mcpConfigPath -Raw | ConvertFrom-Json
    if (-Not $mcp.servers) { $mcp | Add-Member -NotePropertyName 'servers' -NotePropertyValue @{} -Force }
    if (-Not $mcp.inputs) { $mcp | Add-Member -NotePropertyName 'inputs' -NotePropertyValue @() -Force }
    if (-Not $mcp.inputs) { $mcp.inputs = @() }
    if (-Not $mcp.servers) { $mcp.servers = @{} }
}

$projectRoot = Get-Location
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$dbPath = Join-Path $projectRoot 'data\project_memory.db'
$exportDir = Join-Path $projectRoot 'exports'

# Create project-local workspace MCP config in .vscode/mcp.json to keep settings scoped
$workspaceMcpDir = Join-Path $projectRoot '.vscode'
if (-Not (Test-Path $workspaceMcpDir)) {
    New-Item -ItemType Directory -Path $workspaceMcpDir | Out-Null
}
$workspaceMcpConfig = Join-Path $workspaceMcpDir 'mcp.json'
$workspaceEntry = [pscustomobject]@{
    servers = [pscustomobject]@{
        'sqlite-project-memory' = [pscustomobject]@{
            type = 'stdio'
            command = $venvPython
            args = @('-m', 'sqlite_mcp_server')
            env = [ordered]@{
                SQLITE_MCP_TRANSPORT = 'stdio'
                SQLITE_MCP_DB_PATH = 'data/project_memory.db'
                SQLITE_MCP_EXPORT_DIR = 'exports'
            }
        }
    }
    inputs = @()
}
$workspaceEntry | ConvertTo-Json -Depth 10 | Set-Content -Path $workspaceMcpConfig -Encoding UTF8
Write-Host "Created workspace MCP config at $workspaceMcpConfig"

$serverEntry = [pscustomobject]@{
    type = 'stdio'
    command = $venvPython
    args = @('-m', 'sqlite_mcp_server')
    env = [ordered]@{
        SQLITE_MCP_TRANSPORT = 'stdio'
        SQLITE_MCP_DB_PATH = $dbPath
        SQLITE_MCP_EXPORT_DIR = $exportDir
    }
}

$mcp.servers.'sqlite-project-memory' = $serverEntry

$mcp | ConvertTo-Json -Depth 10 | Set-Content -Path $mcpConfigPath -Encoding UTF8

Write-Host "Updated MCP config at $mcpConfigPath"

Write-Host "All done! To run server: python -m sqlite_mcp_server"
