$ErrorActionPreference = 'Stop'
$taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $taskCompiler /nologo /target:winexe /optimize+ /platform:anycpu `
    /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll `
    "/win32manifest:$PSScriptRoot\launcher.manifest" "/win32icon:$PSScriptRoot\launcher.ico" `
    "/out:$PSScriptRoot\OverFieldLauncher.exe" "$PSScriptRoot\Launcher.cs" "$PSScriptRoot\SeasideUI.cs" "$PSScriptRoot\RoomManagerForm.cs"
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
