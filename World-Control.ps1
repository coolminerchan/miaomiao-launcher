[CmdletBinding()]
param(
    [ValidateSet('Start','Stop','Status','Backup')][string]$Action = 'Status',
    [string]$GameRoot = '',
    [ValidateSet('solo','host')][string]$Mode = 'solo',
    [uint32]$Uid = 1000000,
    [string]$HostAddress = '127.0.0.1',
    [int]$ProxyPort = 18890,
    [switch]$LaunchClient, [switch]$StopServer, [switch]$Json,
    [string]$PythonExe, [string]$ResultPath
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if([string]::IsNullOrWhiteSpace($GameRoot)) { $GameRoot=$PSScriptRoot }
$taskBase = Join-Path $PSScriptRoot 'profiles'
$taskStateFile = Join-Path $PSScriptRoot 'runtime\world-state.json'
$taskRegistry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$taskProfile = Join-Path $taskBase $Mode
$taskExecutable = Join-Path $taskProfile 'server\Lolo.exe'
$taskClient = Join-Path $taskProfile 'client\launcher.exe'
function Find-Client([string]$Base) {
    if ([string]::IsNullOrWhiteSpace($Base)) { return $null }
    foreach ($candidate in @(
        (Join-Path $Base 'launcher.exe'),
        (Join-Path $Base 'OverField Game\launcher.exe')
    )) { if (Test-Path -LiteralPath $candidate) { return $candidate } }
    foreach ($child in (Get-ChildItem -LiteralPath $Base -Directory -ErrorAction SilentlyContinue)) {
        foreach ($candidate in @(
            (Join-Path $child.FullName 'launcher.exe'),
            (Join-Path $child.FullName 'OverField Game\launcher.exe')
        )) { if (Test-Path -LiteralPath $candidate) { return $candidate } }
    }
    return $null
}
$taskOriginalClient = Find-Client $GameRoot
$taskTarget = if ($Mode -eq 'solo') { '127.0.0.1' } else { $HostAddress }
$taskHttp = if ($Mode -eq 'solo') { 18080 } else { 19080 }
$taskGateway = if ($Mode -eq 'solo') { 18100 } else { 19100 }
$taskLogPort = if ($Mode -eq 'solo') { 18200 } else { 19200 }
$taskAdminPort = if ($Mode -eq 'solo') { 18300 } else { 19300 }

function Read-State {
    if (Test-Path -LiteralPath $taskStateFile) {
        $taskRead=Get-Content -LiteralPath $taskStateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $taskRead.PSObject.Properties['Gateway']) { $taskRead | Add-Member -NotePropertyName Gateway -NotePropertyValue $null }
        return $taskRead
    }
    return $null
}
function Save-State($State) {
    $taskJson = $State | ConvertTo-Json -Depth 8
    [IO.Directory]::CreateDirectory((Split-Path -Parent $taskStateFile)) | Out-Null
    [IO.File]::WriteAllText($taskStateFile, $taskJson, [Text.UTF8Encoding]::new($false))
}
function Test-Port([string]$Address, [int]$Port) {
    $taskSocket = [Net.Sockets.TcpClient]::new()
    try { $taskConnect=$taskSocket.ConnectAsync($Address,$Port); return $taskConnect.Wait(800) -and $taskSocket.Connected }
    catch { return $false } finally { $taskSocket.Dispose() }
}
function Process-Matches($Record) {
    if (-not $Record) { return $false }
    $taskProcess = Get-Process -Id $Record.Id -ErrorAction SilentlyContinue
    return $taskProcess -and $taskProcess.Path -eq $Record.Path -and $taskProcess.StartTime.ToUniversalTime().ToString('o') -eq $Record.Started
}
function Stop-Recorded($Record) {
    if (Process-Matches $Record) {
        $taskProcess=Get-Process -Id $Record.Id -ErrorAction Stop
        Stop-Process -Id $taskProcess.Id -ErrorAction Stop
        if (-not $taskProcess.WaitForExit(5000)) { throw 'Timed out stopping this profile process.' }
    }
}
function Notify-Proxy {
    if (-not ('WorldWinInet' -as [type])) {
        Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class WorldWinInet { [DllImport("wininet.dll")] public static extern bool InternetSetOption(IntPtr h,int o,IntPtr b,int n); }'
    }
    [WorldWinInet]::InternetSetOption([IntPtr]::Zero,39,[IntPtr]::Zero,0) | Out-Null
    [WorldWinInet]::InternetSetOption([IntPtr]::Zero,37,[IntPtr]::Zero,0) | Out-Null
}
function Restore-Route($State) {
    if (-not $State -or -not $State.ProxyBefore) { return }
    $taskCurrent=Get-ItemProperty -LiteralPath $taskRegistry
    foreach ($taskName in @('AutoConfigURL','ProxyEnable')) {
        $taskExpected = if ($taskName -eq 'AutoConfigURL') { $State.PacUrl } else { 0 }
        if ($taskCurrent.$taskName -ne $taskExpected) { continue }
        $taskBefore=$State.ProxyBefore.$taskName
        if ($taskBefore.Exists) {
            $taskKind=if ($taskName -eq 'ProxyEnable') { 'DWord' } else { 'String' }
            New-ItemProperty -LiteralPath $taskRegistry -Name $taskName -Value $taskBefore.Value -PropertyType $taskKind -Force | Out-Null
        } else { Remove-ItemProperty -LiteralPath $taskRegistry -Name $taskName -ErrorAction SilentlyContinue }
    }
    Notify-Proxy
}
function Stop-World($State) {
    if (-not $State) { return }
    Restore-Route $State
    Stop-Recorded $State.Proxy
    Stop-Recorded $State.Gateway
    Stop-Recorded $State.Server
    $State.Active=$false; Save-State $State
}
function Python-Json([string[]]$Arguments) {
    $taskOutput = & $taskPython -X utf8 (Join-Path $PSScriptRoot 'profile_manager.py') @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Profile operation failed. Check the game directory or LAN address.' }
    return $taskOutput | ConvertFrom-Json
}
function Start-Background([string]$Executable,[string]$Directory,[string]$Name,[string[]]$Arguments,[string[]]$Environment=@()) {
    $taskStamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $taskLogDirectory=Join-Path $taskProfile 'logs'
    $taskArgs=@('-X','utf8',(Join-Path $PSScriptRoot 'service_runner.py'),'--executable',$Executable,'--cwd',$Directory,
        '--stdout',(Join-Path $taskLogDirectory "$Name-$taskStamp.log"),'--stderr',(Join-Path $taskLogDirectory "$Name-$taskStamp.err.log"))
    foreach ($taskEnv in $Environment) { $taskArgs+=@('--env',$taskEnv) }
    $taskArgs+=@('--')+$Arguments
    $taskOutput=& $taskPython @taskArgs
    if ($LASTEXITCODE -ne 0) { throw 'Could not start this profile service.' }
    $taskPid=($taskOutput | ConvertFrom-Json).pid
    $taskProcess=Get-Process -Id $taskPid -ErrorAction Stop
    return [pscustomobject]@{ Id=$taskPid; Path=$Executable; Started=$taskProcess.StartTime.ToUniversalTime().ToString('o'); Owned=$true }
}
function Wait-Ready([string]$Address,[int]$Port,$Record) {
    for ($taskAttempt=0;$taskAttempt -lt 40;$taskAttempt++) {
        if (-not (Process-Matches $Record)) { throw 'Profile service exited. See this profile logs.' }
        if (Test-Port $Address $Port) { return }
        Start-Sleep -Milliseconds 250
    }
    throw "Profile port $Port did not become ready."
}
function Client-Running {
    return @(Get-Process -Name 'launcher' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $taskOriginalClient -or ($_.Path -and $_.Path.StartsWith($taskBase+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) }).Count -gt 0
}
function Invoke-World {
    $taskState=Read-State
    if ($Action -eq 'Status') {
        $taskCurrent=Get-ItemProperty -LiteralPath $taskRegistry
        $taskSame=$taskState -and $taskState.Active -and $taskState.Mode -eq $Mode -and $taskState.Target -eq $taskTarget
        $taskHttpUp=Test-Port $taskTarget $taskHttp
        $taskGateUp=Test-Port $taskTarget $taskGateway
        $taskFirewall=$false
        if ($Mode -eq 'host') { try { $taskFirewall=@(Get-NetFirewallRule -Name 'OverFieldLocal-LAN','OverFieldLocal-LAN-Gateway' -ErrorAction Stop | Where-Object { $_.Enabled -eq 'True' }).Count -eq 2 } catch { } }
        [pscustomobject]@{
            HttpListening=$taskHttpUp; GatewayListening=$taskGateUp; ProxyListening=Test-Port '127.0.0.1' $taskAdminPort
            ServerRunning=$taskSame -and (Process-Matches $taskState.Server)
            ServerRequired=$true; ProxyRunning=$taskSame -and (Process-Matches $taskState.Gateway)
            ProxyEnabled=$taskSame -and (Process-Matches $taskState.Gateway)
            ClientRunning=Client-Running; Mode=$Mode; RuntimeMode=if ($taskState -and $taskState.Active) { $taskState.Mode } else { '' }
            Target=$taskTarget; HttpPort=$taskHttp; GatewayPort=$taskGateway; ProfilePath=$taskProfile; FirewallConfigured=$taskFirewall
        } | ConvertTo-Json -Compress
        return
    }
    if ($Action -eq 'Stop') { Stop-World $taskState; Write-Output 'Profile services stopped; previous routing restored.'; return }
    $taskPython=if ($PythonExe) { (Get-Item -LiteralPath $PythonExe).FullName } else { (Get-Command python.exe).Source }
    if ($Action -eq 'Backup') {
        $taskBackup=Python-Json @('backup','--base',$taskBase,'--mode',$Mode)
        Write-Output $taskBackup.backup; return
    }
    if (Client-Running) {
        if (-not $taskState -or -not $taskState.Active -or $taskState.Mode -ne $Mode -or $taskState.Target -ne $taskTarget -or $taskState.Uid -ne $Uid) { throw 'Close the game before changing its mode or UID.' }
    }
    if ($taskState -and $taskState.Active -and ($taskState.Mode -ne $Mode -or $taskState.Target -ne $taskTarget)) { throw 'Stop the current world before switching modes or host addresses.' }
    if ($taskState -and $taskState.Active -and -not $taskState.Gateway) { Stop-World $taskState; $taskState=$null }
    # Migrate the old shared controller exactly once, preserving its proxy snapshot.
    $taskLegacy=Join-Path $PSScriptRoot 'runtime\state.json'
    if (Test-Path -LiteralPath $taskLegacy) {
        $taskLegacyState=Get-Content -LiteralPath $taskLegacy -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($taskLegacyState.Active) {
            if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'Lolo-Control.ps1'))) { throw 'Active legacy services detected. Stop them using the original launcher before using this clean public build. Do not copy private runtime state into a release folder.' }
            & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Lolo-Control.ps1') -Action Stop -StopServer
            if ($LASTEXITCODE -ne 0) { throw 'Could not stop the previous shared services.' }
        }
    }
    if ($LaunchClient -and -not (Test-Path -LiteralPath $taskOriginalClient)) { throw 'Game client not found. Select the local Bilibili PC installation for solo play.' }
    $taskInfo=Python-Json @('prepare','--root',$GameRoot,'--base',$taskBase,'--mode',$Mode,'--host',$taskTarget)
    if (-not $taskState -or -not $taskState.Active) {
        $taskBefore=Get-ItemProperty -LiteralPath $taskRegistry
        $taskSnapshot=@{}
        foreach ($taskName in @('ProxyEnable','ProxyServer','ProxyOverride','AutoConfigURL')) {
            $taskValue=$taskBefore.PSObject.Properties[$taskName]
            $taskSnapshot[$taskName]=@{ Exists=$null -ne $taskValue; Value=if ($taskValue) { $taskValue.Value } else { $null } }
        }
        $taskState=[pscustomobject]@{ Active=$true; Mode=$Mode; Target=$taskTarget; Profile=$taskProfile; Uid=$Uid; ProxyBefore=$null; PacUrl=''; Server=$null; Proxy=$null; Gateway=$null }
        Save-State $taskState
    }
    try {
        if (-not (Process-Matches $taskState.Server)) {
            foreach ($taskPort in @($taskHttp,$taskGateway,$taskLogPort)) { if (Test-Port $taskTarget $taskPort) { throw "Profile port $taskPort is occupied by another service." } }
            $taskState.Server=Start-Background $taskExecutable $taskProfile 'server' @('-c',(Join-Path $taskProfile 'config.json'))
            Save-State $taskState
            Wait-Ready $taskTarget $taskHttp $taskState.Server
            Wait-Ready '127.0.0.1' ($taskGateway+1) $taskState.Server
        }
        if (-not (Process-Matches $taskState.Gateway)) {
            if ((Test-Port $taskTarget $taskGateway) -or (Test-Port '127.0.0.1' $taskAdminPort)) { throw 'The room gateway port is occupied.' }
            $taskRoomArgs=@('-X','utf8',(Join-Path $PSScriptRoot 'room_gateway.py'),'--profile',$taskProfile,'--host',$taskTarget,'--port',"$taskGateway",'--backend-port',"$($taskGateway+1)",'--admin-port',"$taskAdminPort")
            $taskState.Gateway=Start-Background $taskPython $PSScriptRoot 'rooms' $taskRoomArgs
            Save-State $taskState
            Wait-Ready $taskTarget $taskGateway $taskState.Gateway
            Wait-Ready '127.0.0.1' $taskAdminPort $taskState.Gateway
        }
        # The isolated client redirects only its own dispatch connections.
        # Existing system proxy and PAC settings are not modified.
        Restore-Route $taskState
        $taskUidOutput=& $taskPython -X utf8 (Join-Path $PSScriptRoot 'capture_import.py') uid --profile $taskProfile --uid $Uid
        if ($LASTEXITCODE -ne 0) { throw 'UID account could not be prepared.' }
        $taskUidData=$taskUidOutput | ConvertFrom-Json
        $taskState.Uid=$Uid; Save-State $taskState
        Write-Output "World ready: $Mode $taskTarget UID $Uid."
        if ($taskInfo.imported) { Write-Output 'Previous progress imported into the isolated solo save.' }
        if ($LaunchClient) {
            if (Client-Running) { Write-Output 'Client already running; kept current session.' }
            else {
                Python-Json @('client','--root',$GameRoot,'--base',$taskBase,'--mode',$Mode) | Out-Null
                $taskSdkLog=Join-Path $taskProfile 'logs\uid-sdk.log'
                $taskClientArguments=@('-X','utf8',(Join-Path $PSScriptRoot 'service_runner.py'),'--visible','--executable',$taskClient,'--cwd',(Split-Path -Parent $taskClient),
                    '--stdout',(Join-Path $taskProfile 'logs\client-stdout.log'),'--stderr',(Join-Path $taskProfile 'logs\client-stderr.log'),
                    '--env',"LOLO_SDK_UID=$($taskUidData.sdkUid)",'--env',"LOLO_SDK_LOG=$taskSdkLog",'--env',"LOLO_DISPATCH_HOST=$taskTarget",'--env',"LOLO_DISPATCH_PORT=$taskHttp",'--','-logFile',(Join-Path $taskProfile 'logs\Player.log'))
                & $taskPython @taskClientArguments | Out-Null
                if ($LASTEXITCODE -ne 0) { throw 'Local UID client could not launch.' }
                Write-Output 'Client launched with local UID SDK.'
            }
        }
    } catch { Stop-World $taskState; throw }
}

$taskExitCode=0
$taskLock=[Threading.Mutex]::new($false,'Local\OverFieldWorldControl')
$taskLockHeld=$false
try {
    if ($Action -ne 'Status') {
        try { $taskLockHeld=$taskLock.WaitOne(0) } catch [Threading.AbandonedMutexException] { $taskLockHeld=$true }
        if (-not $taskLockHeld) { throw 'Another world operation is running. Try again shortly.' }
    }
    $taskOutput=(Invoke-World | Out-String).Trim()
    $taskResult=@{ Code=0; Output=$taskOutput; Error='' }
} catch { $taskExitCode=1; $taskResult=@{ Code=1; Output=''; Error=$_.Exception.Message } }
finally { if ($taskLockHeld) { $taskLock.ReleaseMutex() }; $taskLock.Dispose() }
if ($ResultPath) { [IO.File]::WriteAllText($ResultPath,($taskResult | ConvertTo-Json -Compress -Depth 6),[Text.UTF8Encoding]::new($false)) }
else { if ($taskExitCode) { Write-Error $taskResult.Error } else { Write-Output $taskResult.Output } }
exit $taskExitCode
