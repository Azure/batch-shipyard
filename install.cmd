@echo off

REM check for argument
IF [%1] EQU [] (
	echo Usage: install.cmd [virtual env name] [optional: path to python.exe]
	exit /b 1
)
IF %~1 == shipyard.cmd (
	echo "shipyard.cmd" cannot be specified as the virtual environment name.
	exit /b 1
)
SET VENVNAME=%~1

REM set python to use
IF [%2] NEQ [] (
	SET PYTHON=%~2
) ELSE (
	FOR /f %%i in ('where python.exe') do SET PYTHON="%%i"
)
IF NOT DEFINED PYTHON (
	echo Python not found. Please ensure python.exe is in your PATH.
	exit /b 1
)
echo Using python from %PYTHON%

REM check that shipyard.py is in cwd
SET SHIPYARDFILE="%cd%\shipyard.py"
IF NOT EXIST %SHIPYARDFILE% (
	echo shipyard.py does not exist in current working directory. Please run installer from Batch Shipyard root.
	exit /b 1
)

REM check for anaconda
%PYTHON% -c "from __future__ import print_function; import sys; print(sys.version)" > .pyver.txt
SET /P PYTHONVER=<.pyver.txt
del .pyver.txt
SET ANACONDA=0
IF NOT "%PYTHONVER%"=="%PYTHONVER:anaconda=%" (
	echo Anaconda detected.
	SET ANACONDA=1
)
IF NOT "%PYTHONVER%"=="%PYTHONVER:continuum=%" (
	echo Anaconda detected.
	SET ANACONDA=1
)
IF NOT "%PYTHONVER%"=="%PYTHONVER:conda-forge=%" (
	echo Anaconda detected.
	SET ANACONDA=1
)

REM install env and requirements
IF %ANACONDA% EQU 1 (
	echo Performing install for Anaconda.
	conda create --yes --name %VENVNAME%
	cmd.exe /c "activate %VENVNAME% & conda install --yes pip & pip install --upgrade -r requirements.txt & deactivate %VENVNAME%"
) ELSE (
	echo Performing install for Python.
	pip install --upgrade virtualenv
	IF %ERRORLEVEL% NEQ 0 (
		echo "pip install failed"
		exit /b 1
	)
	virtualenv -p %PYTHON% %VENVNAME%
	cmd.exe /c "%VENVNAME%\Scripts\activate & pip uninstall -y azure-storage & deactivate"
	cmd.exe /c "%VENVNAME%\Scripts\activate & pip install --upgrade -r requirements.txt & deactivate"
)

REM create launcher cmd
SET CMDFILE=shipyard.cmd
(echo @echo off) > %CMDFILE%
IF %ANACONDA% EQU 1 (
	(echo activate %VENVNAME% ^& python %SHIPYARDFILE% %%* ^& deactivate %VENVNAME%) >> %CMDFILE%
) ELSE (
	(echo "%cd%\%VENVNAME%\Scripts\activate" ^& python %SHIPYARDFILE% %%* ^& deactivate) >> %CMDFILE%
)

echo Installation complete. Run Batch Shipyard as: %cd%\shipyard.cmd
