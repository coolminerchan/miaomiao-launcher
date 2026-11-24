[CmdletBinding()]
param(
    [ValidateSet('Account', 'Gardens')]
    [string]$Mode = 'Account',
    [string]$OutDir = (Join-Path $PSScriptRoot 'output'),
    [ValidateRange(1, 65535)]
    [int[]]$Ports = @(11001, 11002, 11003, 11004, 21001, 21002),
    [ValidateRange(0, 3600)]
    [int]$AutoStopSeconds = 0,
    [string]$PythonExe,
    [string]$TSharkExe
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$user = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $user.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请右键对应的 .cmd 文件，选择「以管理员身份运行」。'
}

$python = if ($PythonExe) { $PythonExe } elseif ($env:OVERFIELD_BACKUP_PYTHON) { $env:OVERFIELD_BACKUP_PYTHON } else { Join-Path $PSScriptRoot 'tools\python\python.exe' }
$tshark = if ($TSharkExe) { $TSharkExe } elseif ($env:OVERFIELD_TSHARK) { $env:OVERFIELD_TSHARK } else { Join-Path $PSScriptRoot 'tools\tshark\tshark.exe' }
$env:OVERFIELD_TSHARK = $tshark
$pktmon = Join-Path $env:SystemRoot 'System32\PktMon.exe'
foreach ($program in @($python, $tshark, $pktmon)) {
    if (-not (Test-Path -LiteralPath $program -PathType Leaf)) {
        throw "找不到 $program 。请先完整解压工具包，并在支持 PktMon 的 Windows 上运行。"
    }
}
& $python -B -c 'import cramjam, google.protobuf'
if ($LASTEXITCODE -ne 0) { throw '内置 Python 依赖加载失败，请重新解压工具包。' }
& $tshark --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw '内置 TShark 无法启动，请检查是否完整解压。' }

function Invoke-PacketMonitor([string[]]$CommandArgs) {
    $result = & $pktmon @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PktMon $($CommandArgs[0]) 失败（退出码 $LASTEXITCODE）。$($result -join ' ')"
    }
    $result
}

$prefix = if ($Mode -eq 'Account') { 'account' } else { 'gardens' }
$sessionName = '{0}_{1}' -f $prefix, (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
$sessionPath = [IO.Path]::GetFullPath((Join-Path $OutDir $sessionName))
$etl = Join-Path $sessionPath 'capture.etl'
$pcap = Join-Path $sessionPath 'capture.pcapng'
$export = Join-Path $sessionPath 'export'

$mutex = New-Object Threading.Mutex($false, 'Global\OverFieldBackupCapture')
$ownsMutex = $false
$started = $false
$filtersAdded = $false
try {
    try { $ownsMutex = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { throw '另一个备份窗口正在抓包，请在那个窗口先按回车结束。' }

    $status = (Invoke-PacketMonitor @('status')) -join [Environment]::NewLine
    if ($status -notmatch '(?i)Packet\s+Monitor\s+is\s+not\s+running|数据包监视器\s*没有运行|封包監視器\s*(未執行|未在執行|未運行|沒有執行|沒有運行)') {
        throw "无法确认 PktMon 空闲。请先结束其他 PktMon 会话。当前状态 $status"
    }
    $filters = (Invoke-PacketMonitor @('filter', 'list')) -join [Environment]::NewLine
    if ($filters -notmatch '(?im)^\s*(none|无|無|no (packet )?filters( configured)?)\s*[.。]?\s*$') {
        throw "已有 PktMon 筛选器，或系统语言的输出无法识别。工具保留了现有筛选器。$filters"
    }

    New-Item -ItemType Directory -Path $sessionPath | Out-Null
    foreach ($port in ($Ports | Sort-Object -Unique)) {
        Invoke-PacketMonitor @('filter', 'add', "OFBackup_$port", '-t', 'TCP', '-p', "$port") | Out-Null
        $filtersAdded = $true
    }
    Invoke-PacketMonitor @('start', '--capture', '--comp', 'nics', '--pkt-size', '0', '--file-size', '1024', '--file-name', $etl) | Out-Null
    $started = $true

    Write-Host "抓包已开始。输出目录 $sessionPath"
    if ($Mode -eq 'Account') {
        Write-Host '请退出再启动自己的官服客户端，登录并进入场景。'
        Write-Host '依次点开角色与穿搭、背包、装备、任务、宠物、家园、好友、邮件、抽卡记录和图鉴。'
        Write-Host '要保存某套家园预设，请切到对应预设并进入家园，等家具加载。'
    } else {
        Write-Host '请拜访要保存的好友家园，等家具加载出来后再进入下一家。'
    }
    if ($AutoStopSeconds -gt 0) { Start-Sleep -Seconds $AutoStopSeconds }
    else { [void](Read-Host '操作完毕后，回到本窗口按回车') }
} finally {
    try {
        if ($started) { Invoke-PacketMonitor @('stop') | Out-Null }
    } finally {
        try {
            if ($filtersAdded) { Invoke-PacketMonitor @('filter', 'remove') | Out-Null }
        } finally {
            if ($ownsMutex) { $mutex.ReleaseMutex() }
            $mutex.Dispose()
        }
    }
}

if (-not (Test-Path -LiteralPath $etl -PathType Leaf)) {
    throw "找不到抓包文件 $etl"
}
Invoke-PacketMonitor @('etl2pcap', $etl, '--out', $pcap) | Out-Null
$scriptName = if ($Mode -eq 'Account') { 'parse_pcap.py' } else { 'extract_gardens.py' }
$env:PYTHONUTF8 = '1'
& $python -B -X utf8 (Join-Path $PSScriptRoot $scriptName) $pcap --out $export
if ($LASTEXITCODE -ne 0) {
    throw "解包失败。可从 $pcap 重新解包。"
}
Write-Host "已保存到 $sessionPath"
