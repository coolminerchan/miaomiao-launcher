"""Execute the real capture control branch with mocked PktMon, without elevation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).parent
HARNESS=r'''
param([string]$CaptureScript,[string]$Root,[string]$Scenario)
$ErrorActionPreference='Stop'
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($CaptureScript,[ref]$null,[ref]$errors)
if($errors.Count){throw 'Capture source parse failure'}
$operation=$ast.EndBlock.Statements | Where-Object { $_ -is [Management.Automation.Language.TryStatementAst] } | Select-Object -First 1
if(-not $operation){throw 'Capture loop unavailable'}
$script:ops=New-Object 'Collections.Generic.List[string]'
$script:readCount=0
$script:sleepCount=0
function Clear-PreviousBackupCapture {}
function Remove-BackupFilters { $script:ops.Add('remove-filters') }
function Read-Host {
    param([string]$Prompt)
    $script:readCount++
    if($Scenario -eq 'cli-error'){throw 'Simulated input failure'}
    return ''
}
function Start-Sleep {
    param([int]$Seconds,[int]$Milliseconds)
    $script:sleepCount++
    # Simulate 13.5 seconds of polling, beyond the old 12-second segment.
    if($Scenario -eq 'gui-stop' -and $script:sleepCount -eq 27){
        New-Item -ItemType File -Path $StopFlag -Force | Out-Null
    }
}
function Invoke-PacketMonitor {
    param([string[]]$CommandArgs)
    $script:ops.Add(($CommandArgs -join '|'))
    if($CommandArgs[0] -eq 'start'){
        $file=$CommandArgs[[array]::IndexOf($CommandArgs,'--file-name')+1]
        [IO.File]::WriteAllBytes($file,[byte[]](1,2,3))
    }
    if($CommandArgs[0] -eq 'etl2pcap'){
        $file=$CommandArgs[[array]::IndexOf($CommandArgs,'--out')+1]
        [IO.File]::WriteAllBytes($file,(New-Object byte[] 300))
    }
}
$Mode='Account';$Ports=@(11001);$ServerIps=@();$CleanupOnly=$false
$AutoStopSeconds=if($Scenario -eq 'cli-auto'){1}else{0}
$StopFlag=if($Scenario -eq 'gui-stop'){Join-Path $Root 'stop.flag'}else{''}
$ReadyPath=Join-Path $Root 'ready.json'
$sessionPath=Join-Path $Root 'account_20200101_120000_001'
$etl=Join-Path $sessionPath 'capture.etl'
$pcap=Join-Path $sessionPath 'capture.pcapng'
$liveStop=Join-Path $sessionPath 'live-progress-stop.flag'
$python='unused-python'
# Invoke-Expression has no source-file PSScriptRoot. Supply a fixture path so
# observer discovery behaves like a standalone installation without a watcher.
$FixtureScriptRoot=Join-Path $Root 'dummy-tool'
$mutex=New-Object Threading.Mutex($false,('Local\CaptureTest-'+[guid]::NewGuid().ToString()))
$ownsMutex=$false;$started=$false;$filtersAdded=$false;$liveWorker=$null
$failed=$false
try{Invoke-Expression ($operation.Extent.Text.Replace('$PSScriptRoot','$FixtureScriptRoot'))}catch{
    if($Scenario -ne 'cli-error'){throw}
    $failed=$true
}
@{operations=@($script:ops.ToArray());readCount=$script:readCount;sleepCount=$script:sleepCount;failed=$failed;pcapExists=(Test-Path $pcap);ready=(Test-Path $ReadyPath)} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Root 'result.json') -Encoding UTF8
'''

class CaptureModeTests(unittest.TestCase):
    def check(self,scenario):
        if os.name!='nt': self.skipTest('PowerShell fixture requires Windows')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            harness=root/'Harness.ps1';harness.write_text(HARNESS,encoding='utf-8-sig')
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(harness),'-CaptureScript',str(ROOT/'backup-tool/capture.ps1'),'-Root',str(root),'-Scenario',scenario],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
            data=json.loads((root/'result.json').read_text(encoding='utf-8-sig'))
            operations=data['operations']
            self.assertEqual(sum(op=='stop' for op in operations),1)
            self.assertEqual(operations[-1],'remove-filters')
            self.assertTrue(data['ready'])
            return data

    def test_cli_enter_finishes_one_continuous_trace(self):
        data=self.check('cli-enter')
        self.assertEqual(data['readCount'],1)
        self.assertEqual(data['sleepCount'],0)
        starts=[op for op in data['operations'] if op.startswith('start|')]
        self.assertEqual(len(starts),1)
        self.assertTrue(starts[0].endswith('capture.etl'))
        self.assertTrue(data['pcapExists'])

    def test_cli_auto_stop_does_not_wait_for_enter(self):
        data=self.check('cli-auto')
        self.assertEqual(data['readCount'],0)
        self.assertEqual(data['sleepCount'],1)
        self.assertTrue(data['pcapExists'])

    def test_gui_keeps_one_trace_until_stop_flag(self):
        data=self.check('gui-stop')
        self.assertEqual(data['readCount'],0)
        self.assertEqual(data['sleepCount'],27)
        starts=[op for op in data['operations'] if op.startswith('start|')]
        conversions=[op for op in data['operations'] if op.startswith('etl2pcap|')]
        self.assertEqual(len(starts),1)
        self.assertEqual(len(conversions),1)
        self.assertTrue(starts[0].endswith('capture.etl'))
        self.assertLess(data['operations'].index('stop'),data['operations'].index(conversions[0]))
        self.assertTrue(data['pcapExists'])

    def test_cli_input_failure_still_stops_owned_trace(self):
        data=self.check('cli-error')
        self.assertTrue(data['failed'])
        self.assertEqual(data['readCount'],1)
        self.assertFalse(data['pcapExists'])

if __name__=='__main__':unittest.main()
