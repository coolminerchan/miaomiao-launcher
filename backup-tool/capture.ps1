[CmdletBinding()]
param(
    [ValidateSet('Account', 'Gardens')]
    [string]$Mode = 'Account',
    [string]$OutDir,
    [ValidateRange(1, 65535)]
    [int[]]$Ports = @(11001, 11002, 11003, 11004, 21001, 21002),
    [ValidateRange(0, 3600)]
    [int]$AutoStopSeconds = 0,
    [switch]$CleanupOnly,
    [string]$StopFlag,
    [string]$ReadyPath,
    [string]$PythonExe,
    [string]$TSharkExe
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)
if (-not $PSBoundParameters.ContainsKey('OutDir')) {
    $OutDir = Join-Path $PSScriptRoot 'output'
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$user = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $user.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请右键对应的 .cmd 文件，选择「以管理员身份运行」。'
}

$python = if ($PythonExe) { $PythonExe } elseif ($env:OVERFIELD_BACKUP_PYTHON) { $env:OVERFIELD_BACKUP_PYTHON } else { Join-Path $PSScriptRoot 'tools\python\python.exe' }
$tshark = if ($TSharkExe) { $TSharkExe } elseif ($env:OVERFIELD_TSHARK) { $env:OVERFIELD_TSHARK } else { Join-Path $PSScriptRoot 'tools\tshark\tshark.exe' }
$env:OVERFIELD_TSHARK = $tshark
$pktmon = Join-Path $env:SystemRoot 'System32\PktMon.exe'
$programs = if ($CleanupOnly) { $pktmon } else { $python, $tshark, $pktmon }
foreach ($program in $programs) {
    if (-not (Test-Path -LiteralPath $program -PathType Leaf)) {
        throw "找不到 $program 。请先完整解压工具包，并在支持 PktMon 的 Windows 上运行。"
    }
}
if (-not $CleanupOnly) {
    & $python -B -c 'import cramjam, google.protobuf'
    if ($LASTEXITCODE -ne 0) { throw '内置 Python 依赖加载失败，请重新解压工具包。' }
    & $tshark --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '内置 TShark 无法启动，请检查是否完整解压。' }
}

function Invoke-PacketMonitor([string[]]$CommandArgs) {
    # PktMon emits UTF-8 even on a GBK PowerShell 5.1 host. Native '&' decoding
    # can corrupt the idle-state text and falsely report an unknown active session.
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $pktmon
    $info.Arguments = (@($CommandArgs | ForEach-Object {
        '"' + [regex]::Replace([regex]::Replace($_, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
    })) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.UTF8Encoding]::new($false)
    $info.StandardErrorEncoding = [Text.UTF8Encoding]::new($false)
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $text = $stdout.Result
        $errorText = $stderr.Result
        if ($process.ExitCode -ne 0) {
            throw "PktMon $($CommandArgs[0]) 失败（退出码 $($process.ExitCode)）。$errorText $text"
        }
        $text -split '[\r\n]+' | Where-Object { $_ -ne '' }
    } finally { $process.Dispose() }
}

function Get-PacketMonitorFilterState {
    $lines = @(Invoke-PacketMonitor @('filter', 'list'))
    $rows = @($lines | Where-Object { $_ -match '^\s*\d' })
    if ($rows.Count -eq 0 -and ($lines -join "`n") -match '(?im)^\s*(none|无|無|no (packet )?filters( configured)?)\s*[.。]?\s*$') {
        return 'Empty'
    }
    if ($rows.Count -gt 0 -and @($rows -notmatch '^\s*\d+\s+OFBackup_(\d{1,5})\s+TCP\s+\1\s*$').Count -eq 0) {
        return 'Backup'
    }
    return 'Other'
}

function Remove-BackupFilters {
    switch (Get-PacketMonitorFilterState) {
        'Backup' { Invoke-PacketMonitor @('filter', 'remove') | Out-Null }
        'Other' { throw '发现其他 PktMon 筛选器，或筛选器格式无法识别。请先在对应的诊断工具中清理。' }
    }
}

function Clear-PreviousBackupCapture {
    $status = (Invoke-PacketMonitor @('status')) -join [Environment]::NewLine
    $idlePattern = '(?im)^\s*(?:Packet\s+Monitor\s+is\s+not\s+running|数据包监视器\s*(?:没有|未在|未)运行|' +
        '封包監視器\s*(?:未|未在|沒有)(?:執行|運行))[.。]?\s*$'
    if ($status -notmatch $idlePattern) {
        $backupLogPattern = '(?im)^[^:：\r\n]+[:：][ \t]*"?' +
            '(?<etl>(?:[a-z]:|\\\\[^\\\r\n]+\\[^\\\r\n]+)(?:\\[^\\\r\n"]+)*' +
            '\\(?:account|gardens)_\d{8}_\d{6}_\d{3}\\capture\.etl)"?[ \t]*\r?$'
        $logMatch = [regex]::Match($status, $backupLogPattern)
        if (-not $logMatch.Success -or (Get-PacketMonitorFilterState) -ne 'Backup') {
            throw "无法确认 PktMon 会话属于本备份工具。请在原诊断窗口结束会话。当前状态 $status"
        }
        $previousEtl = $logMatch.Groups['etl'].Value
        if (-not (Test-Path -LiteralPath $previousEtl -PathType Leaf)) {
            throw "无法验证上一轮抓包文件 $previousEtl 。请先检查 PktMon 会话。"
        }
        Invoke-PacketMonitor @('stop') | Out-Null
        Write-Host "已停止上一轮备份抓包。原始文件保存在 $previousEtl"
    }
    Remove-BackupFilters
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
$liveWorker = $null
$liveStop = Join-Path $sessionPath 'live-progress-stop.flag'
try {
    try { $ownsMutex = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { throw '另一个备份窗口正在抓包，请在那个窗口先按回车结束。' }

    Clear-PreviousBackupCapture
    if ($CleanupOnly) {
        Write-Host 'PktMon 已空闲。'
        return
    }

    New-Item -ItemType Directory -Path $sessionPath | Out-Null
    foreach ($port in ($Ports | Sort-Object -Unique)) {
        Invoke-PacketMonitor @('filter', 'add', "OFBackup_$port", '-t', 'TCP', '-p', "$port") | Out-Null
        $filtersAdded = $true
    }
    # PktMon buffers events until the trace stops, so a single long trace stays
    # empty on disk until the very end. Rotate short traces instead: each stop
    # flushes a finished segment, and the segments are concatenated into one
    # pcapng (multi-section) so the live checklist can read real data.
    $segmentSeconds = 12
    $segment = 0
    $first = $true
    while ($true) {
        $segment++
        $segmentEtl = Join-Path $sessionPath ("segment_{0:d3}.etl" -f $segment)
        Invoke-PacketMonitor @('start', '--capture', '--comp', 'nics', '--pkt-size', '0', '--file-size', '1024', '--file-name', $segmentEtl) | Out-Null
        $started = $true
        if ($first) {
            $first = $false
            if ($ReadyPath) {
                $readyData = @{ ready=$true; session=$sessionPath; pid=$PID } | ConvertTo-Json -Compress
                [IO.File]::WriteAllText($ReadyPath + '.tmp', $readyData, [Text.UTF8Encoding]::new($false))
                Move-Item -LiteralPath ($ReadyPath + '.tmp') -Destination $ReadyPath -Force
            }
            Write-Host "抓包已开始。输出目录 $sessionPath"
            $observer = Join-Path (Split-Path $PSScriptRoot -Parent) 'capture_checklist.py'
            if ($Mode -eq 'Account' -and $StopFlag -and (Test-Path -LiteralPath $observer)) {
                $liveDir = Join-Path $sessionPath 'live-progress'
                New-Item -ItemType Directory -Path $liveDir -Force | Out-Null
                try {
                    $arguments = '-B -X utf8 "' + $observer + '" watch --capture-root "' + $sessionPath + '"'
                    $liveWorker = Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $liveDir 'observer.log') -RedirectStandardError (Join-Path $liveDir 'observer.err.log')
                } catch { Write-Host '实时清单暂不可用，结束后仍会核对完整产物。' }
            }
            if ($Mode -eq 'Account') {
                Write-Host '请退出再启动自己的官服客户端，登录并进入场景。'
                Write-Host '依次点开角色与穿搭、背包、装备、任务、宠物、家园、好友、邮件、抽卡记录和图鉴。'
                Write-Host '要保存某套家园预设，请切到对应预设并进入家园，等家具加载。'
            } else {
                Write-Host '请拜访要保存的好友家园，等家具加载出来后再进入下一家。'
            }
        }
        $offset = 0
        while ($offset -lt $segmentSeconds) {
            if ($AutoStopSeconds -gt 0 -and ($segment - 1) * $segmentSeconds + $offset -ge $AutoStopSeconds) { break }
            if ($StopFlag -and (Test-Path -LiteralPath $StopFlag)) { break }
            Start-Sleep -Milliseconds 500
            $offset += 0.5
        }
        Invoke-PacketMonitor @('stop') | Out-Null
        $started = $false
        if (Test-Path -LiteralPath $segmentEtl -PathType Leaf) {
            $segmentPcap = Join-Path $sessionPath ("segment_{0:d3}.pcapng" -f $segment)
            Invoke-PacketMonitor @('etl2pcap', $segmentEtl, '--out', $segmentPcap) | Out-Null
            if ((Test-Path -LiteralPath $segmentPcap) -and (Get-Item -LiteralPath $segmentPcap).Length -gt 256) {
                # Appending pcapng sections keeps every segment readable by TShark.
                $bytes = [IO.File]::ReadAllBytes($segmentPcap)
                $stream = [IO.File]::Open($pcap, 'Append', 'Write', 'ReadWrite')
                try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
            }
        }
        $done = $AutoStopSeconds -gt 0 -and ($segment * $segmentSeconds) -ge $AutoStopSeconds
        $stopped = $StopFlag -and (Test-Path -LiteralPath $StopFlag)
        if ($done -or $stopped) { break }
    }
} finally {
    if (Test-Path -LiteralPath $sessionPath) {
        New-Item -ItemType File -Path $liveStop -Force | Out-Null
        if ($liveWorker) { [void]$liveWorker.WaitForExit(2000); $liveWorker.Dispose() }
    }
    try {
        if ($started) { Invoke-PacketMonitor @('stop') | Out-Null }
        if ($filtersAdded) { Remove-BackupFilters }
    } finally {
        if ($ownsMutex) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $pcap -PathType Leaf)) {
    $segments = @(Get-ChildItem -LiteralPath $sessionPath -Filter 'segment_*.pcapng' -ErrorAction SilentlyContinue)
    if ($segments.Count -eq 0) { throw "没有采集到任何数据包：请确认登录公服后确实进入了游戏场景。" }
    throw "找不到合并后的抓包文件 $pcap"
}
$scriptName = if ($Mode -eq 'Account') { 'parse_pcap.py' } else { 'extract_gardens.py' }
$env:PYTHONUTF8 = '1'
& $python -B -X utf8 (Join-Path $PSScriptRoot $scriptName) $pcap --out $export
if ($LASTEXITCODE -ne 0) {
    throw "解包失败。可从 $pcap 重新解包。"
}
Write-Host "已保存到 $sessionPath"
