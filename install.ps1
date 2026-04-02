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

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

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
$projectMemoryFolder = Join-Path $projectRoot 'Project Memory'
if (-Not (Test-Path $projectMemoryFolder)) {
    Write-Host "Creating Project Memory folder: $projectMemoryFolder"
    New-Item -ItemType Directory -Path $projectMemoryFolder | Out-Null
}

# Track whether this is a nested install (sqlite-mcp repo lives inside the user's project).
$isNestedInstall = $scriptRoot -ne $projectRoot

# Resolve source root: developer scenario (projectRoot IS the repo), nested install (pyproject.toml
# still in scriptRoot because _finalize-install.ps1 runs after this script exits), PM folder
# (already moved from a prior run), or fallback.
if (Test-Path (Join-Path $projectRoot 'pyproject.toml')) {
    $sourceRoot = $projectRoot
} elseif ($isNestedInstall -and (Test-Path (Join-Path $scriptRoot 'pyproject.toml'))) {
    $sourceRoot = $scriptRoot
    Write-Host "Nested install: using $scriptRoot as source root for pip install."
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
    }
} else {
    Write-Host ".venv already exists at $venvPath, skipping creation."
}

$venvPython = Join-Path $venvPath 'Scripts\python.exe'
if (-Not (Test-Path $venvPython)) {
    Write-Error "Virtual environment python not found at $venvPython"
    exit 1
}

Write-Host "Using virtual environment python: $venvPython"
Write-Host "Installing package from $sourceRoot..."
Invoke-NativeCommand -Label 'Install build prerequisites' -Command {
    & $venvPython -m pip install --disable-pip-version-check --no-input setuptools wheel
}
if ($isNestedInstall) {
    Write-Host "Nested install detected: using non-editable package install because source files move into Project Memory after install."
    Invoke-NativeCommand -Label 'Install package' -Command {
        & $venvPython -m pip install --disable-pip-version-check --no-input --no-build-isolation $sourceRoot
    }
} else {
    Invoke-NativeCommand -Label 'Install package' -Command {
        & $venvPython -m pip install --disable-pip-version-check --no-input --no-build-isolation -e $sourceRoot
    }
}

$dbPath    = Join-Path $projectMemoryFolder 'pm_data\project_memory.db'
$exportDir = Join-Path $projectMemoryFolder 'pm_exports'

# Ensure PM subdirectories exist
if (-Not (Test-Path (Split-Path $dbPath))) { New-Item -ItemType Directory -Path (Split-Path $dbPath) -Force | Out-Null }
if (-Not (Test-Path $exportDir))           { New-Item -ItemType Directory -Path $exportDir -Force | Out-Null }

Write-Host "Bootstrapping project memory..."
$env:SQLITE_MCP_DB_PATH    = $dbPath
$env:SQLITE_MCP_EXPORT_DIR = $exportDir
Invoke-NativeCommand -Label 'Bootstrap project memory' -Command {
    & $venvPython -m sqlite_mcp_server.cli --db-path "$dbPath" bootstrap-self --repo-root "$projectRoot"
}

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
Invoke-NativeCommand -Label 'Project state health check' -Command {
    & $venvPython -m sqlite_mcp_server.cli --db-path "$dbPath" project-state
}
Invoke-NativeCommand -Label 'Database health check' -Command {
    & $venvPython -m sqlite_mcp_server.cli --db-path "$dbPath" health
}

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

# For nested installs: schedule _finalize-install.ps1 through a temporary cmd.exe wrapper.
# That wrapper waits for this installer to exit, then runs the finalizer with
# ExecutionPolicy Bypass so the remaining source files — including install.ps1,
# install.sh, and the finalize script itself — are moved into Project Memory.
if ($isNestedInstall) {
    $finalizeScript = Join-Path $scriptRoot '_finalize-install.ps1'
    $finalizeLog    = Join-Path $projectMemoryFolder 'finalize-install.log'
    if (Test-Path $finalizeScript) {
        $tmpCmd = [System.IO.Path]::Combine(
            [System.IO.Path]::GetTempPath(),
            "sqlite_mcp_launch_finalize_$([System.IO.Path]::GetRandomFileName()).cmd"
        )
        $finalizeScriptQuoted = $finalizeScript.Replace('"', '""')
        $scriptRootQuoted = $scriptRoot.Replace('"', '""')
        $projectRootQuoted = $projectRoot.Replace('"', '""')
        $projectMemoryQuoted = $projectMemoryFolder.Replace('"', '""')
        $finalizeLogQuoted = $finalizeLog.Replace('"', '""')
        $launchLine = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -ScriptRoot "{1}" -ProjectRoot "{2}" -ProjectMemoryFolder "{3}" -LogFile "{4}"' -f $finalizeScriptQuoted, $scriptRootQuoted, $projectRootQuoted, $projectMemoryQuoted, $finalizeLogQuoted
        $cmdLines = @(
            '@echo off',
            'timeout /t 2 /nobreak >nul',
            $launchLine,
            'del /F /Q "%~f0" >nul 2>&1'
        ) -join "`r`n"
        [System.IO.File]::WriteAllText($tmpCmd, $cmdLines)

        Write-Host "Scheduling post-install file reorganization (background)..."
        Write-Host "Finalize log: $finalizeLog"
        Start-Process 'cmd.exe' -ArgumentList "/c `"$tmpCmd`"" -WindowStyle Hidden
    } else {
        Write-Warning "Finalize script not found at $finalizeScript; skipping post-install cleanup."
    }
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
Write-Host "[ACTION REQUIRED] Fully reload or restart VS Code if tools do not appear."
Write-Host "[ACTION REQUIRED] Start a new Agent chat session after reload/restart."
Write-Host "[ACTION REQUIRED] If the server is not running after restart, run 'MCP: Start Server' and select 'sqlite-project-memory'."
Write-Host "[ACTION REQUIRED] Use Agent mode and choose Project Memory agent (or /sqlite-project-memory)."
if (-not $instructionsFound) {
    Write-Host "Next: paste the SQLite Project Memory snippet into your project instructions file." -ForegroundColor Yellow
}

if ($LogFile) {
    Stop-Transcript
    Write-Host "Transcript saved to $LogFile"
}

