@echo off

REM get installed python exe and dir
pushd %HOME%\python*
SET PYTHONHOME=%cd%
SET PYTHON=%PYTHONHOME%\python.exe
IF NOT EXIST "%PYTHON%" (
    echo "%PYTHON%" does not exist!
    exit /b 1
)
popd

REM ensure git is in path
where git.exe
IF %ERRORLEVEL% NEQ 0 (
    echo "git not found"
    exit /b 1
)

REM git clone repo
taskkill /F /IM python.exe
SET CLONEDIR=%HOME%\batch-shipyard
IF EXIST "%CLONEDIR%" (
    rd /s /q "%CLONEDIR%"
)
git clone "https://github.com/Azure/batch-shipyard.git" "%CLONEDIR%"
IF %ERRORLEVEL% NEQ 0 (
    echo "git clone failed"
    exit /b 1
)

REM create cmd file
(echo @echo off) > "%CLONEDIR%\shipyard.cmd"
(echo SET PYTHON=%PYTHON%) >> "%CLONEDIR%\shipyard.cmd"
type shipyard.cmd >> "%CLONEDIR%\shipyard.cmd"

REM install requirements
pushd "%CLONEDIR%"
"%PYTHON%" -m pip install --upgrade appdirs packaging six
IF %ERRORLEVEL% NEQ 0 (
    echo "pip install pre-requisites failed"
    exit /b 1
)
"%PYTHON%" -m pip install --upgrade -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo "pip install requirements.txt failed"
    exit /b 1
)
popd
