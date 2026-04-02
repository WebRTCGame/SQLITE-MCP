<#
install.ps1
SQLite MCP installer for Windows PowerShell.

Usage:
  .\install.ps1                       # fresh install or update
  .\install.ps1 -LogFile install.log  # with transcript logging
    .\install.ps1 -AppendInstructions   # append snippet to suggested instructions file
#>

# Date modified: 2026-04-01
#
param(
    [string]$LogFile,
    [switch]$AppendInstructions
)

if ($LogFile) {
    Write-Host "Logging to $LogFile"
    Start-Transcript -Path $LogFile -Append -Force
}

$ErrorActionPreference = 'Stop'
Write-Host "=== SQLite MCP install script started ==="

# The install script lives inside the sqlite-mcp checkout.
# If the directory is named 'sqlite-mcp', the user's project root is its parent.
$scriptRoot = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
if ([System.IO.Path]::GetFileName($scriptRoot) -ieq 'sqlite-mcp') {
    $projectRoot = Split-Path $scriptRoot -Parent
} else {
    $projectRoot = $scriptRoot
}

Write-Host "Using project root: $projectRoot"
Set-Location $projectRoot

function Move-NestedCheckout {
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

    Write-Host "Moving repository source from $ScriptRoot into Project Memory: $ProjectMemoryFolder"
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

        $dst = Join-Path $ProjectMemoryFolder $item.Name
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

$projectMemoryFolder = Join-Path $projectRoot 'Project Memory'
if (-Not (Test-Path $projectMemoryFolder)) {
    Write-Host "Creating Project Memory folder: $projectMemoryFolder"
    New-Item -ItemType Directory -Path $projectMemoryFolder | Out-Null
}

# Track whether this is a nested install (sqlite-mcp repo lives inside the user's project).
$isNestedInstall = $scriptRoot -ne $projectRoot

# Move repo contents into Project Memory so nothing from sqlite-mcp pollutes the user's project root.
if ($isNestedInstall) {
    Move-NestedCheckout -ScriptRoot $scriptRoot -ProjectRoot $projectRoot -ProjectMemoryFolder $projectMemoryFolder -InstallScriptPath $MyInvocation.MyCommand.Path
    $scriptRoot = $projectRoot
}

# Resolve source root: developer scenario (projectRoot IS the repo), PM folder (nested install), fallback.
if (Test-Path (Join-Path $projectRoot 'pyproject.toml')) {
    $sourceRoot = $projectRoot
} elseif (Test-Path (Join-Path $projectMemoryFolder 'pyproject.toml')) {
    $sourceRoot = $projectMemoryFolder
    Write-Host "Using Project Memory folder as source root for pip install: $sourceRoot"
} else {
    Write-Warning "pyproject.toml not found; proceeding with project root as source root."
    $sourceRoot = $projectRoot
}

# Auto-migrate legacy artifact locations (no-op if already in PM or source doesn't exist).
$moveMappings = @(
    @{ Source = Join-Path $projectRoot '.venv';   Destination = Join-Path $projectMemoryFolder '.venv';      Label = '.venv' },
    @{ Source = Join-Path $projectRoot 'data';    Destination = Join-Path $projectMemoryFolder 'pm_data';    Label = 'data' },
    @{ Source = Join-Path $projectRoot 'exports'; Destination = Join-Path $projectMemoryFolder 'pm_exports'; Label = 'exports' }
)
foreach ($mapping in $moveMappings) {
    if (-Not (Test-Path $mapping.Source)) { continue }
    if (Test-Path $mapping.Destination) {
        Write-Host "Migration skipped for $($mapping.Label): destination already exists."
        continue
    }
    Write-Host "Migrating $($mapping.Label) from $($mapping.Source) to $($mapping.Destination)"
    Move-Item -Path $mapping.Source -Destination $mapping.Destination -Force
}

# Create virtual environment inside Project Memory
$venvPath = Join-Path $projectMemoryFolder '.venv'
function New-VenvWithTimeout {
    param([string]$Target, [int]$TimeoutSec = 300)
    $job = Start-Job -ScriptBlock { param($t); python -m venv $t } -ArgumentList $Target
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
        Write-Warning "Python venv creation failed or timed out, trying --without-pip fallback. Error: $_"
        python -m venv $venvPath --without-pip
        $fallbackPython = Join-Path $venvPath 'Scripts\python.exe'
        Write-Host "Bootstrapping pip in fallback venv..."
        & $fallbackPython -m ensurepip --default-pip
        & $fallbackPython -m pip install --upgrade pip
    }
} else {
    Write-Host ".venv already exists at $venvPath, skipping creation."
}

$activateScript = Join-Path $venvPath 'Scripts\Activate.ps1'
if (-Not (Test-Path $activateScript)) {
    Write-Error "Activation script not found at $activateScript"
    exit 1
}

Write-Host "Activating virtual environment..."
. $activateScript

$venvPython = Join-Path $venvPath 'Scripts\python.exe'
Write-Host "Installing package from $sourceRoot..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $sourceRoot

$dbPath    = Join-Path $projectMemoryFolder 'pm_data\project_memory.db'
$exportDir = Join-Path $projectMemoryFolder 'pm_exports'

# Ensure PM subdirectories exist
if (-Not (Test-Path (Split-Path $dbPath))) { New-Item -ItemType Directory -Path (Split-Path $dbPath) -Force | Out-Null }
if (-Not (Test-Path $exportDir))           { New-Item -ItemType Directory -Path $exportDir -Force | Out-Null }

Write-Host "Bootstrapping project memory..."
$env:SQLITE_MCP_DB_PATH    = $dbPath
$env:SQLITE_MCP_EXPORT_DIR = $exportDir
sqlite-project-memory-admin --db-path "$dbPath" bootstrap-self --repo-root "$projectRoot"

# Stop any running server processes before health checks
Write-Host "Checking for running sqlite_mcp_server processes..."
$runningMcp = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and ($_.CommandLine -like '*-m sqlite_mcp_server*' -or $_.CommandLine -like '*sqlite_mcp_server*')
}
if ($runningMcp) {
    Write-Host "Stopping active sqlite_mcp_server process(es)..."
    foreach ($proc in $runningMcp) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped PID $($proc.ProcessId)"
        } catch {
            Write-Warning "Failed to stop PID $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
} else {
    Write-Host "No running sqlite_mcp_server processes found."
}

Write-Host "Running health checks..."
if (-Not (Get-Command sqlite-project-memory-admin -ErrorAction SilentlyContinue)) {
    Write-Error "sqlite-project-memory-admin not found after install."
    exit 1
}
sqlite-project-memory-admin --db-path "$dbPath" project-state
sqlite-project-memory-admin --db-path "$dbPath" health

# Write .vscode/mcp.json (always project-local)
$projectVscode = Join-Path $projectRoot '.vscode'
if (-Not (Test-Path $projectVscode)) { New-Item -ItemType Directory -Path $projectVscode | Out-Null }
$mcpConfigPath = Join-Path $projectVscode 'mcp.json'
Write-Host "Writing MCP config: $mcpConfigPath"

if (Test-Path $mcpConfigPath) {
    $mcp = Get-Content -Path $mcpConfigPath -Raw | ConvertFrom-Json
    if (-Not $mcp.servers) { $mcp | Add-Member -NotePropertyName 'servers' -NotePropertyValue @{} -Force }
    if (-Not $mcp.inputs)  { $mcp | Add-Member -NotePropertyName 'inputs'  -NotePropertyValue @() -Force }
} else {
    $mcp = [pscustomobject]@{ servers = @{}; inputs = @() }
}

$serverEntry = [pscustomobject]@{
    type    = 'stdio'
    command = $venvPython
    args    = @('-m', 'sqlite_mcp_server')
    env     = [ordered]@{
        SQLITE_MCP_TRANSPORT  = 'stdio'
        SQLITE_MCP_DB_PATH    = $dbPath
        SQLITE_MCP_EXPORT_DIR = $exportDir
    }
}

# Merge into servers (handle both PSCustomObject and Hashtable)
$hashtable = @{}
if ($mcp.servers -is [System.Collections.Hashtable]) {
    $hashtable = $mcp.servers
} else {
    foreach ($key in $mcp.servers.PSObject.Properties.Name) { $hashtable[$key] = $mcp.servers.$key }
}
$hashtable['sqlite-project-memory'] = $serverEntry
$mcp.servers = $hashtable

$mcp | ConvertTo-Json -Depth 10 | Set-Content -Path $mcpConfigPath -Encoding UTF8
Write-Host "Updated MCP config at $mcpConfigPath"

# Deploy copilot customizations (.github/copilot-instructions.md, skill, agent) to the target project.
# Source files live under assets/ inside the sqlite-mcp repo (or Project Memory for nested installs).
$assetsDir = Join-Path $sourceRoot 'assets'
if (Test-Path $assetsDir) {
    $githubDir = Join-Path $projectRoot '.github'

    # --- Skill ---------------------------------------------------------------
    $skillSrc    = Join-Path $assetsDir 'skills\sqlite-project-memory\SKILL.md'
    $skillDstDir = Join-Path $githubDir 'skills\sqlite-project-memory'
    if (Test-Path $skillSrc) {
        if (-Not (Test-Path $skillDstDir)) { New-Item -ItemType Directory -Path $skillDstDir -Force | Out-Null }
        Copy-Item -Path $skillSrc -Destination (Join-Path $skillDstDir 'SKILL.md') -Force
        Write-Host "Deployed skill: $skillDstDir\SKILL.md"
    }

    # --- Agent ---------------------------------------------------------------
    $agentSrc    = Join-Path $assetsDir 'agents\project-memory.agent.md'
    $agentDstDir = Join-Path $githubDir 'agents'
    if (Test-Path $agentSrc) {
        if (-Not (Test-Path $agentDstDir)) { New-Item -ItemType Directory -Path $agentDstDir -Force | Out-Null }
        Copy-Item -Path $agentSrc -Destination (Join-Path $agentDstDir 'project-memory.agent.md') -Force
        Write-Host "Deployed agent: $agentDstDir\project-memory.agent.md"
    }

    # --- copilot-instructions snippet (print notice — user must add manually) ---
    $snippetSrc = Join-Path $assetsDir 'copilot-instructions-snippet.md'
    if (Test-Path $snippetSrc) {
        $snippetCopied = $false
        $instructionsCandidates = @(
            (Join-Path $projectRoot '.github\copilot-instructions.md'),
            (Join-Path $projectRoot 'AGENTS.md'),
            (Join-Path $projectRoot 'CLAUDE.md')
        )
        $instructionsTarget = $instructionsCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-Not $instructionsTarget) {
            $instructionsTarget = Join-Path $projectRoot '.github\copilot-instructions.md'
        }

        $snippetText = Get-Content -Path $snippetSrc -Raw

        if ($AppendInstructions) {
            try {
                $targetDir = Split-Path -Parent $instructionsTarget
                if ($targetDir -and -Not (Test-Path $targetDir)) {
                    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                }
                if (-Not (Test-Path $instructionsTarget)) {
                    New-Item -ItemType File -Path $instructionsTarget -Force | Out-Null
                }
                $existingTarget = Get-Content -Path $instructionsTarget -Raw -ErrorAction SilentlyContinue
                if ($existingTarget -notmatch 'sqlite-project-memory') {
                    if ($existingTarget -and -not $existingTarget.EndsWith("`n")) {
                        Add-Content -Path $instructionsTarget -Value "`n"
                    }
                    Add-Content -Path $instructionsTarget -Value "`n---`n$snippetText"
                    Write-Host "Appended SQLite Project Memory snippet to: $instructionsTarget"
                } else {
                    Write-Host "Instructions target already contains sqlite-project-memory section: $instructionsTarget"
                }
            } catch {
                Write-Warning "Could not append instructions automatically: $($_.Exception.Message)"
            }
        }

        if (Get-Command Set-Clipboard -ErrorAction SilentlyContinue) {
            try {
                $snippetText | Set-Clipboard
                $snippetCopied = $true
            } catch {
                Write-Warning "Could not copy snippet to clipboard: $($_.Exception.Message)"
            }
        }

        Write-Host ""
        Write-Host "=== ACTION REQUIRED: Add AI instructions ===" -ForegroundColor Yellow
        Write-Host "Append the snippet below to your AI instructions file"
        Write-Host "(.github/copilot-instructions.md, AGENTS.md, CLAUDE.md, etc.)."
        Write-Host "Suggested target: $instructionsTarget"
        Write-Host "A copy is saved at: $snippetSrc"
        if ($snippetCopied) {
            Write-Host "Snippet copied to clipboard."
        } else {
            Write-Host "Clipboard copy unavailable; copy from the snippet below."
        }
        Write-Host "--- snippet start ---"
        $snippetText | Write-Host
        Write-Host "--- snippet end ---"

        if (Get-Command code -ErrorAction SilentlyContinue) {
            try {
                $targetDir = Split-Path -Parent $instructionsTarget
                if ($targetDir -and -Not (Test-Path $targetDir)) {
                    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                }
                if (-Not (Test-Path $instructionsTarget)) {
                    New-Item -ItemType File -Path $instructionsTarget -Force | Out-Null
                }
                code $instructionsTarget | Out-Null
                Write-Host "Opened in VS Code: $instructionsTarget"
            } catch {
                Write-Warning "Could not open target instructions file: $($_.Exception.Message)"
            }
        }
        Write-Host ""
    }
} else {
    Write-Host "Assets directory not found at $assetsDir; skipping copilot customization deployment."
}

# Optional post-install hook
$postInstallHook = Join-Path $projectRoot '.scripts\post_install.ps1'
if (Test-Path $postInstallHook) {
    Write-Host "Running post-install hook: $postInstallHook"
    try { & $postInstallHook } catch { Write-Warning "Post-install hook failed: $_" }
}

# Install completion marker
$installationMarker = Join-Path $projectMemoryFolder '.install-complete'
if (-Not (Test-Path $installationMarker)) {
    New-Item -ItemType File -Path $installationMarker -Force | Out-Null
    Write-Host "Created install marker: $installationMarker"
} else {
    Write-Host "Install marker already present (update complete): $installationMarker"
}

# For nested installs: remove any sqlite-mcp source files that leaked into project root.
# (All source should have moved into Project Memory; this is a safety net only.)
if ($isNestedInstall) {
    $leakedArtifacts = @(
        'src', 'tests', 'pyproject.toml', 'README.md', 'INSTALL.md',
        'API SUMMARY.md', 'Chart.mmd', 'install.sh', '.gitignore',
        'tmp_views', 'tmp_smoke_test.py', 'tmp.db', 'tmp.db-shm', 'tmp.db-wal'
    )
    foreach ($artifact in $leakedArtifacts) {
        $path = Join-Path $projectRoot $artifact
        if (Test-Path $path) {
            Write-Host "Removing leaked source artifact from project root: $path"
            try {
                Remove-Item -Path $path -Recurse -Force -ErrorAction Stop
            } catch {
                $errMsg = $_.Exception.Message
                Write-Warning "Could not remove ${path}: $errMsg"
            }
        }
    }
    Write-Host "Nested install complete. Project Memory contains all sqlite-mcp source and runtime files."
}

Write-Host "=== Install complete ==="
Write-Host "Project Memory: $projectMemoryFolder"
Write-Host "MCP config:     $mcpConfigPath"

$agentPath = Join-Path $projectRoot '.github\agents\project-memory.agent.md'
$skillPath = Join-Path $projectRoot '.github\skills\sqlite-project-memory\SKILL.md'
$instructionsTargets = @(
    (Join-Path $projectRoot '.github\copilot-instructions.md'),
    (Join-Path $projectRoot 'AGENTS.md'),
    (Join-Path $projectRoot 'CLAUDE.md')
)
$instructionsFound = $false
foreach ($target in $instructionsTargets) {
    if (Test-Path $target) {
        $targetText = Get-Content -Path $target -Raw -ErrorAction SilentlyContinue
        if ($targetText -match 'sqlite-project-memory') {
            $instructionsFound = $true
            break
        }
    }
}

Write-Host ""
Write-Host "=== Usage Gates Report ==="
Write-Host ("[PASS] .vscode/mcp.json has sqlite-project-memory entry: {0}" -f (Test-Path $mcpConfigPath))
Write-Host ("[PASS] Project Memory agent file exists: {0}" -f (Test-Path $agentPath))
Write-Host ("[PASS] sqlite-project-memory skill file exists: {0}" -f (Test-Path $skillPath))
Write-Host ("[{0}] Instructions snippet found in project instructions file" -f ($(if ($instructionsFound) { 'PASS' } else { 'ACTION REQUIRED' })))
Write-Host "[ACTION REQUIRED] Approve/trust MCP server in VS Code if prompted."
Write-Host "[ACTION REQUIRED] Reload VS Code window after install if tools do not appear."
Write-Host "[ACTION REQUIRED] Use Agent mode and choose Project Memory agent (or /sqlite-project-memory)."
if (-not $instructionsFound) {
    Write-Host "Next: paste the SQLite Project Memory snippet into your project instructions file." -ForegroundColor Yellow
}

if ($LogFile) {
    Stop-Transcript
    Write-Host "Transcript saved to $LogFile"
}

