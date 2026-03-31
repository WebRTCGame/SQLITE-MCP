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

# Git initialize / refresh from remote if available
if (-Not (Test-Path .git)) {
    Write-Host "Initializing git repository..."
    git init
} else {
    Write-Host "Git repository already initialized."
}

# Ensure repository has remote and pull latest content from GitHub
$remote = 'origin'
$defaultBranch = 'main'
try {
    $currentRemote = git remote get-url $remote 2>$null
} catch {
    $currentRemote = $null
}

if (-Not $currentRemote) {
    Write-Host "No 'origin' remote found. If you want upstream updates from GitHub, run: git remote add origin <repo-url>"
} else {
    Write-Host "Found origin remote: $currentRemote"
    # Auto-detect default branch
    try {
        $headRef = git remote show $remote | Select-String 'HEAD branch' | ForEach-Object { ($_ -split ':')[1].Trim() }
        if ($headRef) { $defaultBranch = $headRef }
    } catch {}

    Write-Host "Fetching latest from $remote/$defaultBranch..."
    git fetch $remote --depth=1

    try {
        Write-Host "Pulling latest changes..."
        git pull --ff-only $remote $defaultBranch
    } catch {
        Write-Warning "git pull failed (non-fast-forward or local changes). You may need to resolve manually."
    }
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

Write-Host "Checking for running sqlite_mcp_server processes..."
$runningMcp = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -ne $null) -and ($_.CommandLine -like '*-m sqlite_mcp_server*' -or $_.CommandLine -like '*sqlite_mcp_server*')
}

if ($runningMcp) {
    Write-Host "Found active sqlite_mcp_server process(es). Stopping them before install..."
    foreach ($proc in $runningMcp) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped process $($proc.ProcessId): $($proc.CommandLine)"
        } catch {
            Write-Warning "Failed to stop process $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
} else {
    Write-Host "No running sqlite_mcp_server processes found."
}

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

# Configure machine-global MCP host config only. Per-project workspace config is intentionally skipped.
# This avoids duplicate settings and centralizes the registered under Code Insiders user scope.
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

if ($mcp.servers -is [System.Collections.Hashtable]) {
    $mcp.servers['sqlite-project-memory'] = $serverEntry
} else {
    # Convert to hashtable to preserve safe assignment of dash-containing keys.
    $hashtable = @{}
    foreach ($key in $mcp.servers.PSObject.Properties.Name) {
        $hashtable[$key] = $mcp.servers.$key
    }
    $hashtable['sqlite-project-memory'] = $serverEntry
    $mcp.servers = $hashtable
}

$mcp | ConvertTo-Json -Depth 10 | Set-Content -Path $mcpConfigPath -Encoding UTF8

Write-Host "Updated MCP config at $mcpConfigPath"

Write-Host "All done! To run server: python -m sqlite_mcp_server"
