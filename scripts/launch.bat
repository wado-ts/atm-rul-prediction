@echo off
set "DIR=%~dp0"

if exist "%DIR%start_local_services.ps1" (
    powershell -ExecutionPolicy Bypass -File "%DIR%start_local_services.ps1"
) else if exist "%DIR%start_local_services.sh" (
    bash "%DIR%start_local_services.sh"
) else (
    echo Error: Neither start_local_services.ps1 nor start_local_services.sh was found in "%DIR%"
)

pause