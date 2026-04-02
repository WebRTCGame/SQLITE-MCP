<#
uninstall.ps1
SQLite MCP uninstaller for Windows PowerShell.

Usage:
  .\sqlite-mcp\uninstall.ps1                          # remove MCP config entry + AI customizations only (safe default)
  .\sqlite-mcp\uninstall.ps1 -RemoveRuntime           # also remove Project Memory/.venv
  .\sqlite-mcp\uninstall.ps1 -RemoveData              # also remove Project Memory/pm_data + pm_exports (data loss — export runs first)
  .\sqlite-mcp\uninstall.ps1 -RemoveCustomizations    # also remove .github/agents + .github/skills entries
  .\sqlite-mcp\uninstall.ps1 -RemoveAll               # all of the above + remove empty Project Memory folder
  .\sqlite-mcp\uninstall.ps1 -LogFile uninstall.log   # save a full transcript for debugging

All destructive operations require interactive confirmation (Yes/No) unless -Force is supplied.
Data is exported to markdown and JSON before any deletion.
#>

# Date modified: 2026-04-02
#
param(
    [switch]$RemoveRuntime,
    [switch]$RemoveData,
    [switch]$RemoveCustomizations,
    [switch]$RemoveAll,
    [switch]$Force,
    [string]$LogFile
)

if ($LogFile) {
    Write-Host "Logging to $LogFile"
    Start-Transcript -Path $LogFile -Append -Force
}

$ErrorActionPreference = 'Stop'
Write-Host "=== SQLite MCP uninstall script started ==="

if ($RemoveAll) {
    $RemoveRuntime        = $true
    $RemoveData           = $true
    $RemoveCustomizations = $true
}

# Locate project root the same way the installer does.
$scriptRoot = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
if ([System.IO.Path]::GetFileName($scriptRoot) -ieq 'sqlite-mcp') {
    $projectRoot = Split-Path $scriptRoot -Parent
} else {
    $projectRoot = $scriptRoot
}

Write-Host "Using project root: $projectRoot"
Set-Location $projectRoot

$projectMemoryFolder = Join-Path $projectRoot 'Project Memory'
$mcpConfigPath       = Join-Path $projectRoot '.vscode\mcp.json'
$dbPath              = Join-Path $projectMemoryFolder 'pm_data\project_memory.db'
$exportDir           = Join-Path $projectMemoryFolder 'pm_exports'
$agentFile           = Join-Path $projectRoot '.github\agents\project-memory.agent.md'
$skillDir            = Join-Path $projectRoot '.github\skills\sqlite-project-memory'
$venvPath            = Join-Path $projectMemoryFolder '.venv'
$venvPython          = Join-Path $venvPath 'Scripts\python.exe'
$installMarker       = Join-Path $projectMemoryFolder '.install-complete'

function Confirm-Action {
    param([string]$Message)
    if ($Force) { return $true }
    Write-Host ""
    Write-Host $Message -ForegroundColor Yellow
    $answer = Read-Host "Proceed? [y/N]"
    return ($answer -imatch '^y(es)?$')
}

# ── Step 1: Export data before anything is removed ────────────────────────────
if (Test-Path $dbPath) {
    if (-Not (Confirm-Action "Export all project memory to markdown and JSON before uninstalling?")) {
        Write-Host "Uninstall aborted — data not exported, nothing deleted." -ForegroundColor Red
        exit 0
    }

    $exportTimestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $exportTarget    = Join-Path $projectMemoryFolder "pm_exports\uninstall-backup-$exportTimestamp"
    New-Item -ItemType Directory -Path $exportTarget -Force | Out-Null
    Write-Host "Exporting data to: $exportTarget"

    if (Test-Path $venvPython) {
        try {
                        & $venvPython -m sqlite_mcp_server.cli --db-path "$dbPath" `
                export-views `
                --output-dir "$exportTarget" `
                --force `
                --user-requested `
                --request-reason "Pre-uninstall data export"
            Write-Host "Markdown views exported."
        } catch {
            Write-Warning "Markdown export failed (non-fatal): $($_.Exception.Message)"
        }

        try {
            $jsonBackup = Join-Path $exportTarget "project_memory.snapshot.json"
                        & $venvPython -m sqlite_mcp_server.cli --db-path "$dbPath" `
                export-json `
                --output-path "$jsonBackup"
            Write-Host "JSON snapshot exported: $jsonBackup"
        } catch {
            Write-Warning "JSON export failed (non-fatal): $($_.Exception.Message)"
        }
    } else {
        Write-Warning "Virtual environment not found at $venvPython; skipping data export."
        Write-Warning "Your database file is still at: $dbPath"
        if (-Not (Confirm-Action "Continue uninstall without data export?")) {
            Write-Host "Uninstall aborted." -ForegroundColor Red
            exit 0
        }
    }
} else {
    Write-Host "No database found at $dbPath — skipping data export."
}

# ── Step 2: Remove sqlite-project-memory entry from .vscode/mcp.json ──────────
if (Test-Path $mcpConfigPath) {
    if (Confirm-Action "Remove sqlite-project-memory entry from .vscode/mcp.json?") {
        try {
            $mcp = Get-Content -Path $mcpConfigPath -Raw | ConvertFrom-Json
            if ($mcp.servers) {
                $hashtable = @{}
                foreach ($key in $mcp.servers.PSObject.Properties.Name) {
                    if ($key -ne 'sqlite-project-memory') {
                        $hashtable[$key] = $mcp.servers.$key
                    }
                }
                $mcp.servers = if ($hashtable.Count -gt 0) { $hashtable } else { [pscustomobject]@{} }
                $mcp | ConvertTo-Json -Depth 10 | Set-Content -Path $mcpConfigPath -Encoding UTF8
                Write-Host "Removed sqlite-project-memory from $mcpConfigPath"
            } else {
                Write-Host "No servers key in $mcpConfigPath — nothing to remove."
            }
        } catch {
            Write-Warning "Could not update MCP config: $($_.Exception.Message)"
        }
    }
} else {
    Write-Host "No .vscode/mcp.json found — skipping."
}

# ── Step 3: Remove AI customization files ─────────────────────────────────────
if ($RemoveCustomizations) {
    if (Confirm-Action "Remove project-memory agent and skill files from .github/?") {
        if (Test-Path $agentFile) {
            Remove-Item -Path $agentFile -Force
            Write-Host "Removed: $agentFile"
        }
        if (Test-Path $skillDir) {
            Remove-Item -Path $skillDir -Recurse -Force
            Write-Host "Removed: $skillDir"
        }

        # Clean up empty parent dirs
        $agentsDir = Join-Path $projectRoot '.github\agents'
        $skillsDir = Join-Path $projectRoot '.github\skills'
        foreach ($dir in @($agentsDir, $skillsDir)) {
            if ((Test-Path $dir) -and (-Not (Get-ChildItem -Path $dir -Force))) {
                Remove-Item -Path $dir -Force
                Write-Host "Removed empty directory: $dir"
            }
        }
    }
}

# ── Step 4: Remove .venv (runtime) ────────────────────────────────────────────
if ($RemoveRuntime) {
    if (Test-Path $venvPath) {
        if (Confirm-Action "Remove virtual environment at '$venvPath'?") {
            Remove-Item -Path $venvPath -Recurse -Force
            Write-Host "Removed: $venvPath"
        }
    } else {
        Write-Host "No .venv found at $venvPath — skipping."
    }
}

# ── Step 5: Remove data (pm_data + pm_exports, except the backup we just made) ─
if ($RemoveData) {
    $pmData     = Join-Path $projectMemoryFolder 'pm_data'
    $pmExports  = Join-Path $projectMemoryFolder 'pm_exports'
    if (Confirm-Action "Remove database and exports at '$pmData' and '$pmExports'? Your pre-uninstall backup in pm_exports\uninstall-backup-* will also be deleted.") {
        foreach ($target in @($pmData, $pmExports)) {
            if (Test-Path $target) {
                Remove-Item -Path $target -Recurse -Force
                Write-Host "Removed: $target"
            }
        }
    }
}

# ── Step 6: Remove install marker ─────────────────────────────────────────────
if (Test-Path $installMarker) {
    Remove-Item -Path $installMarker -Force
    Write-Host "Removed install marker: $installMarker"
}

# ── Step 7: Remove empty Project Memory folder (only if -RemoveAll) ───────────
if ($RemoveAll) {
    if ((Test-Path $projectMemoryFolder) -and (-Not (Get-ChildItem -Path $projectMemoryFolder -Force))) {
        if (Confirm-Action "Remove now-empty 'Project Memory' folder?") {
            Remove-Item -Path $projectMemoryFolder -Force
            Write-Host "Removed: $projectMemoryFolder"
        }
    }
}

# ── Final report ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Uninstall Report ==="
Write-Host ("[{0}] sqlite-project-memory removed from .vscode/mcp.json" -f $(if (-Not (Test-Path $mcpConfigPath) -or (Get-Content $mcpConfigPath -Raw) -notmatch 'sqlite-project-memory') { 'PASS' } else { 'PENDING' }))
Write-Host ("[{0}] AI agent file removed" -f $(if (-Not (Test-Path $agentFile)) { 'PASS' } else { 'SKIPPED' }))
Write-Host ("[{0}] AI skill directory removed" -f $(if (-Not (Test-Path $skillDir)) { 'PASS' } else { 'SKIPPED' }))
Write-Host ("[{0}] Virtual environment removed" -f $(if (-Not (Test-Path $venvPath)) { 'PASS' } else { 'SKIPPED' }))
Write-Host ("[{0}] Database removed" -f $(if (-Not (Test-Path $dbPath)) { 'PASS' } else { 'SKIPPED' }))
Write-Host ""
Write-Host "Note: if you manually added the SQLite Project Memory snippet to an instructions file"
Write-Host "(copilot-instructions.md, AGENTS.md, CLAUDE.md, etc.), remove that section manually."
Write-Host ""
Write-Host "=== Uninstall complete ==="

if ($LogFile) {
    Stop-Transcript
    Write-Host "Transcript saved to $LogFile"
}
