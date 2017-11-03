# Dockerfile for Azure/batch-shipyard Cargo (Windows)
# Adapted from: https://github.com/StefanScherer/dockerfiles-windows/blob/master/python/Dockerfile

FROM python:3.6.3-windowsservercore
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

ENV chocolateyUseWindowsCompression false
RUN iex ((new-object net.webclient).DownloadString('https://chocolatey.org/install.ps1')); \
    choco install --no-progress -y git -params "/GitAndUnixToolsOnPath"

ARG GIT_BRANCH
ARG GIT_COMMIT

WORKDIR C:\\batch-shipyard
RUN git clone -b $Env:GIT_BRANCH --single-branch --depth 5 https://github.com/Azure/batch-shipyard.git C:\batch-shipyard ; \
    git checkout $Env:GIT_COMMIT ; \
    pip install --no-cache-dir -r cargo\requirements.txt ; \
	del C:\batch-shipyard\cargo\*.sh ; \
	del C:\batch-shipyard\cargo\Dockerfile ; \
    copy C:\batch-shipyard\cargo\windows\*.cmd C:\batch-shipyard\cargo

RUN python -m compileall C:\Python\Lib ; \
    python -m compileall C:\batch-shipyard\cargo ; \
	exit 0

FROM microsoft/nanoserver

COPY --from=0 /Python /Python
COPY --from=0 /batch-shipyard/cargo /batch-shipyard

SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';"]

ENV PYTHON_VERSION 3.6.3
ENV PYTHON_PIP_VERSION 9.0.1

RUN $env:PATH = 'C:\Python;C:\Python\Scripts;{0}' -f $env:PATH ; \
    Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment\' -Name Path -Value $env:PATH ; \
    mkdir $env:APPDATA\Python\Python36\site-packages ; \
    Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py' -UseBasicParsing ; \
    $replace = ('import tempfile{0}import site{0}site.getusersitepackages()' -f [char][int]10) ; \
    Get-Content get-pip.py | Foreach-Object { $_ -replace 'import tempfile', $replace } | Out-File -Encoding Ascii getpip.py ; \
    $pipInstall = ('pip=={0}' -f $env:PYTHON_PIP_VERSION) ; \
    python getpip.py $pipInstall ; \
    Remove-Item get-pip.py ; \
    Remove-Item getpip.py
