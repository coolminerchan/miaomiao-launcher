"""Offline tests: official path isolation, visible launch and capture-before-launch order."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
import official_launcher as launcher
import official_capture as capture


class OfficialLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'app';self.base.mkdir()
        self.exe=self.root/'official-game'/'launcher.exe';self.exe.parent.mkdir();self.exe.write_bytes(b'MZ-synthetic')
    def test_empty_and_relative_paths_are_rejected(self):
        for value in (None,'','launcher.exe'):
            with self.assertRaises(ValueError):launcher.validate_launcher(value,self.base)
    def test_private_profiles_are_rejected(self):
        exe=self.base/'profiles/solo/client/launcher.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'MZ')
        with self.assertRaises(ValueError):launcher.validate_launcher(exe,self.base)
    def test_private_marker_outside_current_base_is_rejected(self):
        (self.exe.parent/'client-ready.json').write_text('{}')
        with self.assertRaises(ValueError):launcher.validate_launcher(self.exe,self.base)
    def test_local_sdk_replacement_is_rejected(self):
        sdk=self.exe.parent/'launcher_Data/Plugins/x86_64/PCGameSDK.dll';sdk.parent.mkdir(parents=True)
        sdk.write_bytes(b'local-sdk');(self.base/'LocalUidSDK.dll').write_bytes(b'local-sdk')
        with self.assertRaises(ValueError):launcher.validate_launcher(self.exe,self.base)
    def test_private_launcher_name_is_rejected(self):
        exe=self.exe.parent/'OverFieldLauncher.exe';exe.write_bytes(b'MZ')
        with self.assertRaises(ValueError):launcher.validate_launcher(exe,self.base)
    def test_public_path_is_accepted(self):
        self.assertEqual(launcher.validate_launcher(self.exe,self.base),self.exe.resolve())
    def test_visible_launch_has_no_private_args_or_environment(self):
        with patch.dict(os.environ,{'LOLO_SDK_UID':'123','lolo_dispatch_host':'private','PATH':'normal'}), patch.object(launcher.subprocess,'Popen') as spawn:
            launcher.launch_official(self.exe,self.base)
        args,kwargs=spawn.call_args
        self.assertEqual(args[0],[str(self.exe.resolve())]);self.assertEqual(kwargs['creationflags'],0)
        self.assertEqual(kwargs['cwd'],str(self.exe.parent))
        self.assertFalse(any(k.upper().startswith('LOLO_') for k in kwargs['env']))
        self.assertEqual(kwargs['env']['PATH'],'normal')


class CaptureStartOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.base=root/'app';self.base.mkdir();(self.base/'backup-tool').mkdir()
        self.exe=root/'original/launcher.exe';self.exe.parent.mkdir();self.exe.write_bytes(b'MZ-synthetic')
        self.runtime=self.base/'runtime';self.events=[]
        for name,value in {'BASE':self.base,'RUNTIME':self.runtime,'STATE':self.runtime/'capture-state.json',
                           'SESSIONS':self.runtime/'capture-sessions','LOG':self.runtime/'capture.log',
                           'STOP_FLAG':self.runtime/'capture-stop.flag'}.items():
            p=patch.object(capture,name,value);p.start();self.addCleanup(p.stop)
        self.proc=Mock(pid=42);self.proc.poll.return_value=None
        def finish(timeout):self.proc.poll.return_value=0
        self.proc.wait.side_effect=finish
    def spawn_capture(self,command,**kwargs):
        self.events.append('capture')
        ready=Path(command[command.index('-ReadyPath')+1])
        ready.write_text(json.dumps({'ready':True,'pid':42,'session':str(ready.parent/'account')}))
        self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
        self.assertFalse(any(k.upper().startswith('LOLO_') for k in kwargs['env']))
        return self.proc
    def spawn_public(self,value,base):
        self.assertTrue(capture.read_state()['active']);self.events.append('official')
        return Mock(pid=99)
    def contexts(self):
        return (patch.object(capture,'preflight',return_value={'ok':True,'problems':[]}),
                patch.object(capture,'python_exe',return_value=Path('decode-python.exe')),
                patch.object(capture,'tshark_exe',return_value=Path('tshark.exe')))
    def test_capture_ready_precedes_public_launch(self):
        a,b,c=self.contexts()
        with a,b,c,patch.object(capture.subprocess,'Popen',side_effect=self.spawn_capture),patch.object(launcher,'launch_official',side_effect=self.spawn_public):
            result=capture.start(self.exe)
        self.assertEqual(self.events,['capture','official']);self.assertEqual(result['officialPid'],99)
        self.assertEqual(capture.read_state()['officialLauncherPath'],str(self.exe.resolve()))
    def test_capture_failure_never_launches_game(self):
        a,b,c=self.contexts();self.proc.poll.return_value=3
        with a,b,c,patch.object(capture.subprocess,'Popen',return_value=self.proc),patch.object(launcher,'launch_official') as game:
            with self.assertRaises(ValueError):capture.start(self.exe)
        game.assert_not_called();self.assertFalse(capture.read_state()['active'])
    def test_public_spawn_failure_requests_capture_cleanup(self):
        a,b,c=self.contexts()
        with a,b,c,patch.object(capture.subprocess,'Popen',side_effect=self.spawn_capture),patch.object(launcher,'launch_official',side_effect=OSError('synthetic launch failure')):
            with self.assertRaises(OSError):capture.start(self.exe)
        self.assertTrue(capture.STOP_FLAG.is_file());self.assertFalse(capture.read_state()['active'])
        self.proc.kill.assert_not_called()
    def test_missing_official_path_does_not_fall_back_or_capture(self):
        with patch.object(capture.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):capture.start(None)
        spawn.assert_not_called()
    def test_active_private_world_blocks_capture(self):
        self.runtime.mkdir();(self.runtime/'world-state.json').write_text(json.dumps({'Active':True}))
        with patch.object(capture.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):capture.start(self.exe)
        spawn.assert_not_called()
    def test_wait_timeout_is_explicit(self):
        with self.assertRaises(ValueError):capture.wait_capture_ready(self.proc,self.runtime/'no-ready.json',timeout=0)
    def test_failed_worker_reports_readable_first_error(self):
        self.runtime.mkdir()
        (self.runtime/'capture-worker.stderr.log').write_text('拒绝访问。需要管理员权限。\nsynthetic stack',encoding='utf-8')
        self.proc.poll.return_value=5
        with self.assertRaisesRegex(ValueError,'拒绝访问'):
            capture.wait_capture_ready(self.proc,self.runtime/'capture-ready.json')


if __name__=='__main__':unittest.main()
