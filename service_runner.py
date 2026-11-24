"""Launch a background service with native file handles, separate from controller IO."""
import argparse
import json
from pathlib import Path
import subprocess
import os


def launch(executable, arguments, cwd, stdout_path, stderr_path, extra_env=None, visible=False):
    from client_identity import classify
    if visible and Path(executable).name.lower() == 'launcher.exe' and classify(Path(executable).parent) == 'quicksdk-pc':
        return launch_quicksdk(executable, cwd, stdout_path, stderr_path, extra_env or {})
    with open(stdout_path, 'ab', buffering=0) as output, open(stderr_path, 'ab', buffering=0) as error:
        process = subprocess.Popen(
            [executable, *arguments], cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=output, stderr=error, close_fds=True,
            creationflags=0 if visible else subprocess.CREATE_NO_WINDOW,
            env=dict(os.environ, **(extra_env or {})),
        )
    return process.pid


def launch_quicksdk(executable, cwd, stdout_path, stderr_path, environment):
    import sys, time, uuid
    from taptap_private_runner import validated_config
    host = environment.get('LOLO_DISPATCH_HOST', '')
    port = int(environment.get('LOLO_DISPATCH_PORT', '0'))
    uid = int(environment.get('LOLO_SDK_UID', '0'))
    validated_config(Path(executable).parent, host, port, uid)
    import frida  # fail before spawning if the portable adapter dependency is missing
    result_path = Path(stdout_path).with_name('quicksdk-start-' + uuid.uuid4().hex + '.json')
    command = [sys.executable, '-X', 'utf8', str(Path(__file__).with_name('taptap_private_runner.py')),
               '--client', str(Path(executable).parent), '--host', host, '--port', str(port),
               '--uid', str(uid), '--log', str(Path(stdout_path).with_name('quicksdk-local.jsonl')),
               '--result-path', str(result_path)]
    with open(stdout_path, 'ab', buffering=0) as out, open(stderr_path, 'ab', buffering=0) as err:
        worker = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                  close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                  env=dict(os.environ, **environment))
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if result_path.is_file():
                result = json.loads(result_path.read_text(encoding='utf-8'))
                if result.get('ready') and result.get('pid'):
                    return int(result['pid'])
                raise RuntimeError('QuickSDK local adapter did not become ready.')
            if worker.poll() is not None:
                raise RuntimeError('QuickSDK adapter exited; see private client logs.')
            time.sleep(.05)
        raise TimeoutError('QuickSDK adapter startup timed out.')
    finally:
        result_path.unlink(missing_ok=True)
        if worker.poll() is None and not result_path.exists() and time.monotonic() >= deadline:
            worker.terminate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--stdout', required=True)
    parser.add_argument('--stderr', required=True)
    parser.add_argument('--env', action='append', default=[])
    parser.add_argument('--visible', action='store_true')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    environment = dict(item.split('=', 1) for item in args.env)
    print(json.dumps({'pid': launch(args.executable, command, args.cwd, args.stdout, args.stderr, environment, args.visible)}), flush=True)
