[CmdletBinding()]
param([string]$GameRoot='',[Parameter(Mandatory=$true)][string]$HostAddress,[string]$ServerExe,[string]$PythonExe)
$ErrorActionPreference='Stop'
$taskAddress=[Net.IPAddress]::Parse($HostAddress)
$taskBytes=$taskAddress.GetAddressBytes()
if ($taskBytes.Length -ne 4 -or -not ($taskBytes[0] -eq 10 -or ($taskBytes[0] -eq 172 -and $taskBytes[1] -ge 16 -and $taskBytes[1] -le 31) -or ($taskBytes[0] -eq 192 -and $taskBytes[1] -eq 168))) { throw 'A LAN IPv4 address is required.' }
$taskLocal=@([Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | ForEach-Object { $_.GetIPProperties().UnicastAddresses } | ForEach-Object { $_.Address.ToString() })
if ($HostAddress -notin $taskLocal) { throw 'Host address does not belong to this computer.' }
$taskServer=(Get-Item -LiteralPath $(if ($ServerExe) { $ServerExe } else { Join-Path $PSScriptRoot 'profiles\host\server\Lolo.exe' })).FullName
$taskIdentity=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $taskIdentity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator permission is required for this LAN firewall rule.' }
Get-NetFirewallRule -Name 'OverFieldLocal-LAN','OverFieldLocal-LAN-Gateway' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -Name 'OverFieldLocal-LAN' -DisplayName 'OverField local LAN world' -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort 19080,19200 -LocalAddress $HostAddress -RemoteAddress LocalSubnet -Program $taskServer -Profile Any | Out-Null
$taskPython=(Get-Item -LiteralPath $PythonExe).FullName
New-NetFirewallRule -Name 'OverFieldLocal-LAN-Gateway' -DisplayName 'OverField local UID room gateway' -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort 19100 -LocalAddress $HostAddress -RemoteAddress LocalSubnet -Program $taskPython -Profile Any | Out-Null
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'runtime\lan-firewall-result.json'),'{"configured":true}',[Text.UTF8Encoding]::new($false))
