@echo off
rem Sets up Outlast co-op: copies your Steam Outlast, installs OpenOL 2.1.0 and the co-op patch. See tools\outlast-coop\README.md
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\outlast-coop\play\install.ps1" %*
pause
