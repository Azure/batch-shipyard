@echo off
setlocal enabledelayedexpansion

conda install --yes pip & pip install --force-reinstall --upgrade -r requirements.txt
conda list