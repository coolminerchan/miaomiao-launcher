"""Launch a background service with native file handles, separate from controller IO."""
import argparse
import json
from pathlib import Path
import subprocess
import os


def launch(executable, arguments, cwd, stdout_path, stderr_path, extra_env=None, visible=False):
    with open(stdout_path, 'ab', buffering=0) as output, open(stderr_path, 'ab', buffering=0) as error:
        process = subprocess.Popen(
            [executable, *arguments], cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=output, stderr=error, close_fds=True,
            creationflags=0 if visible else subprocess.CREATE_NO_WINDOW,
            env=dict(os.environ, **(extra_env or {})),
        )
    return process.pid


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
