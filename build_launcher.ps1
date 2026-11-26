param([ValidateSet('Both','CN','EN')][string]$Edition='Both')
$ErrorActionPreference = 'Stop'

# Two editions share one code base. The Chinese launcher defaults to the national
# world; the English launcher defaults to the Steam world. Each gets its own
# assembly name so both can be installed and run side by side.
$taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$taskSources = @(
    "$PSScriptRoot\Launcher.cs"
    "$PSScriptRoot\SeasideUI.cs"
    "$PSScriptRoot\RoomManagerForm.cs"
    "$PSScriptRoot\Strings.cs"
)
$taskReferences = @(
    '/reference:System.Windows.Forms.dll'
    '/reference:System.Drawing.dll'
    '/reference:System.Web.Extensions.dll'
)

function Build-Edition([string]$Name, [string[]]$Defines, [string]$Output) {
    $taskArguments = @('/nologo', '/target:winexe', '/optimize+', '/platform:anycpu', '/codepage:65001') + $taskReferences
    foreach ($define in $Defines) { $taskArguments += "/define:$define" }
    $taskArguments += "/win32manifest:$PSScriptRoot\launcher.manifest"
    $taskArguments += "/win32icon:$PSScriptRoot\launcher.ico"
    $taskArguments += "/out:$Output"
    $taskArguments += $taskSources
    & $taskCompiler @taskArguments
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed for $Name." }
    Write-Host ("{0} -> {1}" -f $Name, (Split-Path -Leaf $Output))
}

if($Edition -in @('Both','CN')) { Build-Edition 'national (zh-CN)' @() (Join-Path $PSScriptRoot 'OverFieldLauncher.exe') }
if($Edition -in @('Both','EN')) { Build-Edition 'international (en)' @('ENGLISH') (Join-Path $PSScriptRoot 'OverFieldLauncher-EN.exe') }
