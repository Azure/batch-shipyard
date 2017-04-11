@echo off
setlocal enabledelayedexpansion

REM kill any python.exe running
taskkill /F /IM python.exe
SET CLONEDIR=%HOME%\batch-shipyard
IF EXIST "%CLONEDIR%" (
    rd /s /q "%CLONEDIR%"
)
