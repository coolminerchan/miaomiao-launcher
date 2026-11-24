@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl.exe /nologo /LD /MT /O2 /utf-8 /FoLocalUidSDK.obj LocalUidSDK.cpp /link /DEF:sdk.def /OUT:LocalUidSDK.dll Ws2_32.lib
