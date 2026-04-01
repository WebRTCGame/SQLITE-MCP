<#
install.ps1
PowerShell install script for SQLite MCP from clean VS Code Insiders + git repo state.
Usage (from repo root):
  .\install.ps1
#>

# install.ps1
# SQLite MCP installer script
#
# Description:
#   Bootstraps the SQLite MCP project by preparing project directories, repository state,
#   Python virtual environment, dependency installation, and MCP host config.
#   Supports migration of existing artifacts, optional non-interactive/CI mode, and
#   automatic `.vscode/mcp.json` setup for the sqlite-project-memory server.
#
# Usage (from repo root):
#   .\install.ps1
#
# Date modified: 2026-04-01
#
param(
    [switch]$MigrateExisting,
    [switch]$UseProjectConfig,
    [switch]$UseGlobalConfig,
    [string]$McpConfigPath,
    [switch]$CiMode,
    [switch]$FetchOnly,
    [string]$Branch,
    [switch]$NonInteractive,
    [string]$LogFile,
    [string]$ProjectRoot,
    [string]$ProjectMemoryRoot
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

# Determine project root (explicit override or nearest parent)
$scriptRoot = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
if ($ProjectRoot) {
    $projectRoot = (Resolve-Path -Path $ProjectRoot).Path
} else {
    if ([System.IO.Path]::GetFileName($scriptRoot) -ieq 'sqlite-mcp') {
        $projectRoot = Split-Path $scriptRoot -Parent
    } else {
        $projectRoot = $scriptRoot
    }
}

# repository root alias for backwards compatibility in this script
$repoRoot = $projectRoot

Write-Host "Using project root: $projectRoot"
$projectRootOriginal = $projectRoot
Set-Location $projectRoot

function Flatten-NestedCheckout {
    param(
        [string]$ScriptRoot,
        [string]$ProjectRoot,
        [string]$ProjectMemoryFolder,
        [string]$InstallScriptPath
    )

    if ($ScriptRoot -eq $ProjectRoot) { return }

    if (-Not (Test-Path (Join-Path $ScriptRoot 'pyproject.toml'))) {
        Write-Host "No nested checkout pyproject.toml found in $ScriptRoot. Skipping flattening."
        return
    }

    Write-Host "Flattening nested repository content from $ScriptRoot to $ProjectRoot"
    foreach ($item in Get-ChildItem -Path $ScriptRoot -Force) {
        $src = $item.FullName

        # Skip current ps script while running
        if ($InstallScriptPath -and (Resolve-Path -Path $InstallScriptPath -ErrorAction SilentlyContinue).Path -eq $src) {
            Write-Host "Skipping running install script file from move: $src"
            continue
        }

        # Skip relocation of the project memory folder itself
        if ($ProjectMemoryFolder -and (Resolve-Path -Path $src -ErrorAction SilentlyContinue).Path -eq (Resolve-Path -Path $ProjectMemoryFolder -ErrorAction SilentlyContinue).Path) {
            continue
        }

        $dst = Join-Path $ProjectRoot $item.Name
        if (Test-Path $dst) {
            Write-Host "Destination already exists, not overwriting: $dst"
            continue
        }

        try {
            Move-Item -Path $src -Destination $dst -Force
            Write-Host "Moved $src -> $dst"
        } catch {
            Write-Warning ("Unable to move {0} -> {1}: {2}" -f $src, $dst, $_)
        }
    }

    # Remove empty original folder if appropriate
    if (-Not (Get-ChildItem -Path $ScriptRoot -Force | Where-Object { $_.Name -notin '.','..' })) {
        try {
            Remove-Item -Path $ScriptRoot -Force
            Write-Host "Removed empty nested checkout folder $ScriptRoot"
        } catch {
            Write-Warning ("Could not remove folder {0}: {1}" -f $ScriptRoot, $_)
        }
    }
}


if (-Not (Test-Path (Join-Path $projectRoot 'pyproject.toml'))) {
    Write-Warning "pyproject.toml not found in $projectRoot. Proceeding anyway (assumed external host project)."
}

# Source root is the Python project used for pip install; prefer current script checkout when host is external
$sourceRoot = $projectRoot
if (-Not (Test-Path (Join-Path $sourceRoot 'pyproject.toml'))) {
    if (Test-Path (Join-Path $scriptRoot 'pyproject.toml')) {
        $sourceRoot = $scriptRoot
        Write-Host "Using script location as source root for pip install: $sourceRoot"
    }
}

# Create a self-contained project memory folder (configurable via parameter or env var)
if ($ProjectMemoryRoot) {
    if ([System.IO.Path]::IsPathRooted($ProjectMemoryRoot)) {
        $projectMemoryFolder = (Resolve-Path -Path $ProjectMemoryRoot).Path
    } else {
        $projectMemoryFolder = (Resolve-Path -Path (Join-Path $projectRoot $ProjectMemoryRoot)).Path
    }
} elseif ($env:SQLITE_MCP_PROJECT_MEMORY_ROOT) {
    $projectMemoryFolder = (Resolve-Path -Path $env:SQLITE_MCP_PROJECT_MEMORY_ROOT).Path
} else {
    $projectMemoryFolder = Join-Path $projectRoot 'Project Memory'
}

if (-Not (Test-Path $projectMemoryFolder)) {
    Write-Host "Creating self-contained folder: $projectMemoryFolder"
    New-Item -ItemType Directory -Path $projectMemoryFolder | Out-Null
}

# If the repository was initially checked out in a nested path, move repo contents to project root.
if ($scriptRoot -ne $projectRoot) {
    Flatten-NestedCheckout -ScriptRoot $scriptRoot -ProjectRoot $projectRoot -ProjectMemoryFolder $projectMemoryFolder -InstallScriptPath $MyInvocation.MyCommand.Path
    # Keep path references consistent after flatten
    $scriptRoot = $projectRoot
}

# Determine install status with marker
$installationMarker = Join-Path $projectMemoryFolder '.install-complete'
$alreadyInstalled = Test-Path $installationMarker
if ($alreadyInstalled) {
    Write-Host "Install marker found at $installationMarker. Re-running install; migration will only occur with -MigrateExisting."
}

# Optionally migrate existing project artifacts into Project Memory folder
$moveMappings = @(
    @{ Source = Join-Path $projectRoot '.venv'; Destination = Join-Path $projectMemoryFolder '.venv'; Label = '.venv' },
    @{ Source = Join-Path $projectRoot 'data'; Destination = Join-Path $projectMemoryFolder 'pm_data'; Label = 'data' },
    @{ Source = Join-Path $projectRoot 'exports'; Destination = Join-Path $projectMemoryFolder 'pm_exports'; Label = 'exports' }
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

# Git initialize / refresh from remote if available (still in project root)
if (-Not (Test-Path "$projectRoot\.git")) {
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
function New-VenvWithTimeout {
    param(
        [string]$Target,
        [int]$TimeoutSec = 300
    )

    $job = Start-Job -ScriptBlock {
        param($t)
        python -m venv $t
    } -ArgumentList $Target

    if (-not (Wait-Job $job -Timeout $TimeoutSec)) {
        Stop-Job $job -Force | Out-Null
        Remove-Job $job | Out-Null
        throw "venv creation timed out after $TimeoutSec seconds"
    }

    $result = Receive-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job | Out-Null
    return $result
}

if (-Not (Test-Path $venvPath)) {
    Write-Host "Creating Python virtual environment in $venvPath..."
    try {
        New-VenvWithTimeout -Target $venvPath -TimeoutSec 300
    } catch {
        Write-Warning "Python venv creation failed or timed out, trying with --without-pip fallback. Error: $_"
        python -m venv $venvPath --without-pip
        $fallbackPython = Join-Path $venvPath 'Scripts\python.exe'
        Write-Host "Bootstrapping pip in fallback venv..."
        & $fallbackPython -m ensurepip --default-pip
        & $fallbackPython -m pip install --upgrade pip
    }
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
Set-Location $sourceRoot
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $sourceRoot

Write-Host "Bootstrapping project memory..."
$env:SQLITE_MCP_DB_PATH = $dbPath
$env:SQLITE_MCP_EXPORT_DIR = $exportDir

sqlite-project-memory-admin --db-path $dbPath bootstrap-self --repo-root $projectRoot

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
$sqliteProjectMemoryAdmin = Get-Command sqlite-project-memory-admin -ErrorAction SilentlyContinue
if ($null -eq $sqliteProjectMemoryAdmin) {
    Write-Error "sqlite-project-memory-admin command not found after install."
    exit 1
}

sqlite-project-memory-admin --db-path $dbPath project-state
sqlite-project-memory-admin --db-path $dbPath health

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
        $projectVscode = Join-Path $projectRoot '.vscode'
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
    $projectVscode = Join-Path $projectRoot '.vscode'
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

$projectMemoryRoot = $projectMemoryFolder
$venvPython = Join-Path $projectMemoryRoot '.venv\Scripts\python.exe'
$dbPath = Join-Path $projectMemoryRoot 'pm_data\project_memory.db'
$exportDir = Join-Path $projectMemoryRoot 'pm_exports'

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

function Ensure-ProjectMemoryLayout {
    param(
        [string]$ProjectMemoryRoot,
        [string]$ProjectRoot
    )

    $desiredPaths = @{
        '.venv' = Join-Path $ProjectMemoryRoot '.venv'
        'pm_data' = Join-Path $ProjectMemoryRoot 'pm_data'
        'pm_exports' = Join-Path $ProjectMemoryRoot 'pm_exports'
        '.install-complete' = Join-Path $ProjectMemoryRoot '.install-complete'
    }

    foreach ($item in @('.venv', 'data', 'exports')) {
        $src = Join-Path $ProjectRoot $item
        switch ($item) {
            '.venv' { $dst = $desiredPaths['.venv'] }
            'data' { $dst = Join-Path $desiredPaths['pm_data'] '' }
            'exports' { $dst = $desiredPaths['pm_exports'] }
        }
        if ((Test-Path $src) -and -Not (Test-Path $dst)) {
            Write-Host "Moving existing $item from $src to $dst"
            if (-Not (Test-Path (Split-Path $dst))) { New-Item -ItemType Directory -Path (Split-Path $dst) -Force | Out-Null }
            Move-Item -Path $src -Destination $dst -Force
        }
    }

    if (-Not (Test-Path $desiredPaths['pm_data'])) {
        Write-Host "Creating missing pm_data directory: $($desiredPaths['pm_data'])"
        New-Item -ItemType Directory -Path $desiredPaths['pm_data'] -Force | Out-Null
    }
    if (-Not (Test-Path $desiredPaths['pm_exports'])) {
        Write-Host "Creating missing pm_exports directory: $($desiredPaths['pm_exports'])"
        New-Item -ItemType Directory -Path $desiredPaths['pm_exports'] -Force | Out-Null
    }
    if (-Not (Test-Path $desiredPaths['.install-complete'])) {
        New-Item -ItemType File -Path $desiredPaths['.install-complete'] -Force | Out-Null
        Write-Host "Created missing install marker for coherence: $($desiredPaths['.install-complete'])"
    }

    Write-Host "Project Memory layout verification complete."
}

Ensure-ProjectMemoryLayout -ProjectMemoryRoot $projectMemoryFolder -ProjectRoot $projectRoot

# Cleanup: nested checkout is handled by the flatten step earlier, and repo content should now be in project root.
if ($projectRootOriginal -and $scriptRoot -and ($projectRootOriginal -ne $scriptRoot)) {
    Write-Host "Cleanup: nested checkout behavior was applied (script root: $scriptRoot, project root: $projectRoot)."
}

Write-Host "All done! To run server: python -m sqlite_mcp_server"

if ($LogFile) {
    Stop-Transcript
    Write-Host "Transcript saved to $LogFile"
}

