<#
install.ps1
PowerShell install script for SQLite MCP from clean VS Code Insiders + git repo state.
Usage (from repo root):
  .\install.ps1
#>

param(
    [switch]$MigrateExisting,
    [switch]$UseProjectConfig,
    [switch]$UseGlobalConfig,
    [string]$McpConfigPath,
    [switch]$CiMode,
    [switch]$FetchOnly,
    [string]$Branch,
    [switch]$NonInteractive,
    [string]$LogFile
)

if ($NonInteractive) {
    $ConfirmPreference = 'None'
}

if ($CiMode) {
    $UseProjectConfig = $true
    $NonInteractive = $true
    $ConfirmPreference = 'None'
}

if ($LogFile) {
    Write-Host "Logging to $LogFile"
    Start-Transcript -Path $LogFile -Append -Force
}

$ErrorActionPreference = 'Stop'
Write-Host "=== SQLite MCP install script started ==="

# Ensure we are in repo root (containing pyproject.toml)
$repoRoot = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
Set-Location $repoRoot

if (-Not (Test-Path pyproject.toml)) {
    Write-Error "pyproject.toml not found. Run this script from project root."
    exit 1
}

# Create a self-contained project memory folder
$projectMemoryFolder = Join-Path $repoRoot 'Project Memory'
if (-Not (Test-Path $projectMemoryFolder)) {
    Write-Host "Creating self-contained folder: $projectMemoryFolder"
    New-Item -ItemType Directory -Path $projectMemoryFolder | Out-Null
}

# Determine install status with marker
$installationMarker = Join-Path $projectMemoryFolder '.install-complete'
$alreadyInstalled = Test-Path $installationMarker
if ($alreadyInstalled) {
    Write-Host "Install marker found at $installationMarker. Re-running install; migration will only occur with -MigrateExisting."
}

# Optionally migrate existing project artifacts into Project Memory folder
$moveMappings = @(
    @{ Source = Join-Path $repoRoot '.venv'; Destination = Join-Path $projectMemoryFolder '.venv'; Label = '.venv' },
    @{ Source = Join-Path $repoRoot 'data'; Destination = Join-Path $projectMemoryFolder 'pm_data'; Label = 'data' },
    @{ Source = Join-Path $repoRoot 'exports'; Destination = Join-Path $projectMemoryFolder 'pm_exports'; Label = 'exports' }
)
foreach ($mapping in $moveMappings) {
    if (-Not (Test-Path $mapping.Source)) { continue }
    if (Test-Path $mapping.Destination) {
        Write-Host "Destination already exists for $($mapping.Label), leaving both in place:"
        Write-Host "  source: $($mapping.Source)"
        Write-Host "  destination: $($mapping.Destination)"
        continue
    }

    if ($alreadyInstalled -and -Not $MigrateExisting) {
        Write-Host "Already installed; not migrating $($mapping.Label). Use -MigrateExisting to force move."
        continue
    }

    if ($MigrateExisting) {
        Write-Host "Migrating existing $($mapping.Label) from $($mapping.Source) to $($mapping.Destination)"
        Move-Item -Path $mapping.Source -Destination $mapping.Destination -Force
    } else {
        Write-Host "Found existing '$($mapping.Label)' at $($mapping.Source). To move it into Project Memory, rerun with -MigrateExisting."
    }
}

# Git initialize / refresh from remote if available (still in repo root)
if (-Not (Test-Path "$repoRoot\.git")) {
    Write-Host "Initializing git repository..."
    git init
} else {
    Write-Host "Git repository already initialized."
}

# Ensure repository has remote and pull latest content from GitHub
$remote = 'origin'
$defaultBranch = 'main'
if ($Branch) { $defaultBranch = $Branch }

try {
    $currentRemote = git remote get-url $remote 2>$null
} catch {
    $currentRemote = $null
}

if (-Not $currentRemote) {
    Write-Host "No 'origin' remote found. If you want upstream updates from GitHub, run: git remote add origin <repo-url>"
} else {
    Write-Host "Found origin remote: $currentRemote"
    # Auto-detect default branch unless explicitly set
    if (-Not $Branch) {
        try {
            $headRef = git remote show $remote | Select-String 'HEAD branch' | ForEach-Object { ($_ -split ':')[1].Trim() }
            if ($headRef) { $defaultBranch = $headRef }
        } catch {}
    }

    Write-Host "Fetching latest from $remote/$defaultBranch..."
    git fetch $remote --depth=1

    if ($Branch) {
        Write-Host "Checking out branch $Branch..."
        try {
            git checkout $Branch
        } catch {
            Write-Host "Branch $Branch not found locally; trying to track origin/$Branch..."
            git checkout -b $Branch $remote/$Branch
        }
    }

    if ($FetchOnly) {
        Write-Host "Fetch only requested, exiting now.";
        return
    }

    try {
        Write-Host "Pulling latest changes..."
        git pull --ff-only $remote $defaultBranch
    } catch {
        Write-Warning "git pull failed (non-fast-forward or local changes). You may need to resolve manually."
    }
}

# Create virtual environment in Project Memory path if not exists
$venvPath = Join-Path $projectMemoryFolder '.venv'
if (-Not (Test-Path $venvPath)) {
    Write-Host "Creating Python virtual environment in $venvPath..."
    python -m venv $venvPath
} else {
    Write-Host ".venv already exists at $venvPath, skipping creation."
}

# Activate virtual environment
$activateScript = Join-Path $venvPath 'Scripts\Activate.ps1'
if (-Not (Test-Path $activateScript)) {
    Write-Error "Activation script not found at $activateScript"
    exit 1
}

Write-Host "Activating virtual environment..."
. $activateScript

Write-Host "Installing dependencies..."
Set-Location $repoRoot
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $repoRoot

Write-Host "Bootstrapping project memory..."
sqlite-project-memory-admin bootstrap-self --repo-root $repoRoot

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

# Determine MCP config path in a friendly way
function Get-McpConfigPath {
    param(
        [switch]$useProject,
        [switch]$useGlobal,
        [string]$explicitPath
    )

    if ($explicitPath) {
        return (Resolve-Path -Path $explicitPath).Path
    }

    if ($useProject) {
        $projectVscode = Join-Path $repoRoot '.vscode'
        if (-Not (Test-Path $projectVscode)) { New-Item -ItemType Directory -Path $projectVscode | Out-Null }
        return Join-Path $projectVscode 'mcp.json'
    }

    if ($useGlobal) {
        $candidates = @(
            Join-Path $env:APPDATA 'Code - Insiders\User\mcp.json',
            Join-Path $env:APPDATA 'Code\User\mcp.json'
        )
        foreach ($candidate in $candidates) {
            $folder = Split-Path $candidate -Parent
            if (Test-Path $folder) { return $candidate }
        }
        # fallback to stable path if none exist
        return Join-Path $env:APPDATA 'Code\User\mcp.json'
    }

    # default to project config
    $projectVscode = Join-Path $repoRoot '.vscode'
    if (-Not (Test-Path $projectVscode)) { New-Item -ItemType Directory -Path $projectVscode | Out-Null }
    return Join-Path $projectVscode 'mcp.json'
}

if ($UseProjectConfig -and $UseGlobalConfig) {
    Write-Error "Cannot use both -UseProjectConfig and -UseGlobalConfig. Choose one."
    exit 1
}

$projectConfigMode = $UseProjectConfig -or (-Not $UseGlobalConfig)
$mcpConfigPath = Get-McpConfigPath -useProject:$projectConfigMode -useGlobal:$UseGlobalConfig -explicitPath:$McpConfigPath
Write-Host "Using mcp.json config at: $mcpConfigPath"
if (-Not (Test-Path $mcpConfigPath)) {
    Write-Host "Creating new mcp.json at $mcpConfigPath"
    $mcp = [pscustomobject]@{ servers = @{}; inputs = @(); } | ConvertTo-Json -Depth 10 | ConvertFrom-Json
} else {
    $mcp = Get-Content -Path $mcpConfigPath -Raw | ConvertFrom-Json
    if (-Not $mcp.servers) { $mcp | Add-Member -NotePropertyName 'servers' -NotePropertyValue @{} -Force }
    if (-Not $mcp.inputs) { $mcp | Add-Member -NotePropertyName 'inputs' -NotePropertyValue @() -Force }
    if (-Not $mcp.inputs) { $mcp.inputs = @() }
    if (-Not $mcp.servers) { $mcp.servers = @{} }
}

$projectRoot = $projectMemoryFolder
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$dbPath = Join-Path $projectRoot 'pm_data\project_memory.db'
$exportDir = Join-Path $projectRoot 'pm_exports'

# Ensure consistent substructure in Project Memory folder
if (-Not (Test-Path (Split-Path $dbPath))) { New-Item -ItemType Directory -Path (Split-Path $dbPath) -Force | Out-Null }
if (-Not (Test-Path $exportDir)) { New-Item -ItemType Directory -Path $exportDir -Force | Out-Null }

# Configure MCP host config in selected path (project or global as requested).
# Per-project workspace config is default except when -UseGlobalConfig is provided.
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

# Execute optional post-install hook script if present
$postInstallHook = Join-Path $repoRoot '.scripts\post_install.ps1'
if (Test-Path $postInstallHook) {
    Write-Host "Running post-install hook: $postInstallHook"
    try {
        & $postInstallHook -CI:$CiMode -NonInteractive:$NonInteractive
    } catch {
        Write-Warning "Post-install hook failed: $_"
    }
}

# Write install completion marker for idempotence
if (-Not $alreadyInstalled) {
    New-Item -ItemType File -Path $installationMarker -Force | Out-Null
    Write-Host "Created install marker: $installationMarker"
} else {
    Write-Host "Install marker already present: $installationMarker"
}

Write-Host "All done! To run server: python -m sqlite_mcp_server"

if ($LogFile) {
    Stop-Transcript
    Write-Host "Transcript saved to $LogFile"
}

