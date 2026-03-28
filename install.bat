@echo off
REM install.bat
REM Batch script for SQLite MCP setup from clean repo root.

echo === SQLite MCP install script started ===

SETLOCAL ENABLEDELAYEDEXPANSION

IF NOT EXIST pyproject.toml (
  echo ERROR: pyproject.toml not found. Run this script from project root.
  EXIT /B 1
)

IF NOT EXIST .git (
  echo Initializing git repository...
  git init
) ELSE (
  echo Git repository already initialized.
)

IF NOT EXIST .venv (
  echo Creating Python virtual environment in .venv...
  python -m venv .venv
) ELSE (
  echo .venv already exists, skipping creation.
)

echo Activating virtual environment...
call .\.venv\Scripts\activate.bat

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -e .

echo Bootstrapping project memory...
sqlite-project-memory-admin bootstrap-self --repo-root .

echo Running health checks...
sqlite-project-memory-admin project-state
sqlite-project-memory-admin health

echo All done! To run server: python -m sqlite_mcp_server
ENDLOCAL
