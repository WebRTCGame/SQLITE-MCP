<#
_finalize-install.ps1

Post-install file reorganization for nested SQLite MCP installs.

Moves the sqlite-mcp source tree (including install.ps1, install.sh, and this
script itself) into Project Memory, then removes the now-empty source folder.

Called automatically by install.ps1 as a detached background process.
Do not run this script directly unless you know what you are doing.

Date modified: 2026-04-02
#>
param(
    [string]$ScriptRoot,
    [string]$ProjectRoot,
    [string]$ProjectMemoryFolder,
    [string]$LogFile
)

if ($LogFile) {
    Start-Transcript -Path $LogFile -Force | Out-Null
}

# Wait for installer.ps1 to fully exit and release any file locks.
Start-Sleep -Seconds 3

$selfPath = (Resolve-Path $PSCommandPath -ErrorAction SilentlyContinue).Path

Write-Host "=== SQLite MCP post-install finalize started ==="
Write-Host "Source:      $ScriptRoot"
Write-Host "Destination: $ProjectMemoryFolder"

$moved   = 0
$skipped = 0
$errors  = 0

function Invoke-WithRetry {
    param(
        [scriptblock]$Action,
        [string]$Label,
        [int]$Attempts = 15,
        [int]$DelaySeconds = 2
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            & $Action
            if ($attempt -gt 1) {
                Write-Host "Succeeded after retry ($attempt/$Attempts): $Label"
            }
            return $true
        } catch {
            if ($attempt -eq $Attempts) {
                Write-Warning "Failed after $Attempts attempts: $Label : $($_.Exception.Message)"
                return $false
            }
            Write-Host "Retrying ($attempt/$Attempts): $Label"
            Start-Sleep -Seconds $DelaySeconds
        }
    }

    return $false
}

# Move every item from ScriptRoot (sqlite-mcp/) to ProjectMemoryFolder (Project Memory/).
foreach ($item in Get-ChildItem -Path $ScriptRoot -Force -ErrorAction SilentlyContinue) {

    $itemPath = (Resolve-Path $item.FullName -ErrorAction SilentlyContinue).Path

    # Skip Project Memory folder (it lives inside the project root, not inside ScriptRoot,
    # but guard in case paths overlap).
    $pmResolved = (Resolve-Path $ProjectMemoryFolder -ErrorAction SilentlyContinue).Path
    if ($pmResolved -and $itemPath -and ($itemPath -ieq $pmResolved)) { continue }

    # Skip self — handled below after all other items are moved.
    if ($selfPath -and $itemPath -and ($itemPath -ieq $selfPath)) { continue }

    $dst = Join-Path $ProjectMemoryFolder $item.Name
    if (Test-Path $dst) {
        Write-Host "Destination exists, skipping: $($item.Name)"
        $skipped++
        continue
    }

    if (Invoke-WithRetry -Label "Move $($item.Name)" -Action {
        Move-Item -Path $item.FullName -Destination $dst -Force -ErrorAction Stop
    }) {
        Write-Host "Moved: $($item.Name)"
        $moved++
    } else {
        $errors++
    }
}

# Clean up any source-repo artifacts that leaked directly into ProjectRoot.
$leakedArtifacts = @(
    'src', 'tests', 'pyproject.toml', 'README.md', 'INSTALL.md',
    'API SUMMARY.md', 'Chart.mmd', '.gitignore',
    'tmp_views', 'tmp_smoke_test.py', 'tmp.db', 'tmp.db-shm', 'tmp.db-wal'
)
foreach ($artifact in $leakedArtifacts) {
    $path = Join-Path $ProjectRoot $artifact
    if (Test-Path $path) {
        if (Invoke-WithRetry -Label "Remove leaked artifact $artifact" -Action {
            Remove-Item -Path $path -Recurse -Force -ErrorAction Stop
        }) {
            Write-Host "Removed leaked artifact: $artifact"
        }
    }
}

# Remove ScriptRoot if now empty (only self may remain at this point).
$remaining = Get-ChildItem -Path $ScriptRoot -Force -ErrorAction SilentlyContinue |
    Where-Object { -not $selfPath -or ((Resolve-Path $_.FullName -ErrorAction SilentlyContinue).Path -ine $selfPath) }
if (-not $remaining) {
    if (Invoke-WithRetry -Label "Remove source folder $ScriptRoot" -Attempts 5 -DelaySeconds 2 -Action {
        Remove-Item -Path $ScriptRoot -Recurse -Force -Confirm:$false -ErrorAction Stop
    }) {
        Write-Host "Removed empty source folder: $ScriptRoot"
    } else {
        # Will be retried after self-move clears the last item.
        Write-Host "Source folder not yet empty (self still present); will retry after self-move."
    }
}

Write-Host "Finalize: moved=$moved  skipped=$skipped  errors=$errors"

if ($LogFile) {
    Stop-Transcript | Out-Null
}

# ── Self-move ────────────────────────────────────────────────────────────────
# PowerShell may or may not lock the .ps1 file; try a direct move first.
# Fall back to a tiny cmd.exe wrapper that runs after this process exits.
if ($selfPath) {
    $selfName = Split-Path $selfPath -Leaf
    $selfDst  = Join-Path $ProjectMemoryFolder $selfName

    if (-Not (Test-Path $selfDst)) {
        if (Invoke-WithRetry -Label "Move self $selfName" -Attempts 5 -DelaySeconds 2 -Action {
            Move-Item -Path $selfPath -Destination $selfDst -Force -ErrorAction Stop
        }) {
            # Also attempt to remove the now-empty ScriptRoot.
            Invoke-WithRetry -Label "Remove source folder $ScriptRoot after self-move" -Attempts 5 -DelaySeconds 2 -Action {
                Remove-Item -Path $ScriptRoot -Recurse -Force -Confirm:$false -ErrorAction Stop
            } | Out-Null
        } else {
            # Schedule via cmd after this process exits.
            $tmpCmd = [System.IO.Path]::Combine(
                [System.IO.Path]::GetTempPath(),
                "sqlite_mcp_finalize_$([System.IO.Path]::GetRandomFileName()).cmd"
            )
            $srcQuoted  = $selfPath  -replace '"', '\"'
            $dstQuoted  = $selfDst   -replace '"', '\"'
            $rootQuoted = $ScriptRoot -replace '"', '\"'
            $lines = "@echo off`r`ntimeout /t 2 /nobreak >nul`r`nmove /Y `"$srcQuoted`" `"$dstQuoted`" >nul 2>&1`r`nrmdir /S /Q `"$rootQuoted`" >nul 2>&1`r`ndel /F /Q `"%~f0`" >nul 2>&1"
            [System.IO.File]::WriteAllText($tmpCmd, $lines)
            Start-Process 'cmd' -ArgumentList "/c `"$tmpCmd`"" -WindowStyle Hidden
        }
    }
}
