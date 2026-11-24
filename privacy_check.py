"""Conservative release-tree check; not a substitute for manual secret review."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
ALLOWED = {
    'Launcher.cs', 'SeasideUI.cs', 'RoomManagerForm.cs', 'launcher.manifest', 'launcher.ico',
    'build_launcher.ps1', 'LocalUidSDK.cpp', 'sdk.def', 'build_sdk.cmd',
    'World-Control.ps1', 'Lan-Firewall.ps1', 'profile_manager.py',
    'capture_import.py', 'room_gateway.py', 'proto_fields.json',
    'model_schema.json', 'service_runner.py', 'make_junction.ps1',
    'repair_version.py', 'lolo_redirect.py', 'test_launcher.py',
    'README.md', 'requirements.txt', '.gitignore', 'privacy_check.py',
    'RELEASE-CHECKLIST.md', 'RELEASE-NOTES.md', 'test_backup_tool.py',
    'official_capture.py', 'official_import.py', 'test_official_import.py',
    'official_launcher.py', 'test_official_launcher.py', 'test_pktmon_encoding.py',
    'capture_zip.py', 'test_capture_zip.py',
    'docs/official-capture.md', 'docs/taptap-private.md',
    'client_identity.py', 'taptap_private_runner.py', 'taptap_private_agent.js', 'test_taptap_private.py',
    'docs/login-and-data.md', 'docs/release-audit.md', 'docs/channel-login.md', 'preflight.py',
    'backup-tool/1_backup_account.cmd', 'backup-tool/2_backup_gardens.cmd',
    'backup-tool/3_decode_pcap.cmd', 'backup-tool/capture.ps1',
    'backup-tool/parse_pcap.py', 'backup-tool/extract_gardens.py',
    'backup-tool/README.md', 'backup-tool/requirements.txt',
    'backup-tool/THIRD-PARTY.txt', 'backup-tool/使用说明.txt',
    'backup-tool/4_import_player.cmd', 'backup-tool/import_to_ofps.py',
    'backup-tool/proto_gen/cmdid.csv', 'backup-tool/proto_gen/msg_id.txt',
    'backup-tool/proto_gen/net_pb2.py',
    'backup-tool/proto_gen/Lolo-LICENSE.txt',
    'backup-tool/proto_gen/of-ps-LICENSE.txt',
}
GENERATED = {'OverFieldLauncher.exe', 'LocalUidSDK.dll', 'LocalUidSDK.obj',
             'LocalUidSDK.lib', 'LocalUidSDK.exp'}
PATTERNS = [
    re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s"\']+', re.I),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
]

def main():
    errors = []
    count = 0
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        parts = relative.parts
        if parts[0] == '.git' or '__pycache__' in parts:
            continue
        if relative.as_posix() not in ALLOWED | GENERATED:
            errors.append(f'Unexpected file: {path.relative_to(ROOT)}')
            continue
        count += 1
        data = path.read_bytes()
        texts = [data.decode('utf-8', errors='ignore'), data.decode('utf-16-le', errors='ignore')]
        if any(pattern.search(text) for pattern in PATTERNS for text in texts):
            errors.append(f'Potential private data: {path.name}')
    if errors:
        print('\n'.join(errors))
        return 1
    print(f'PASS: {count} allowlisted files; no detected user paths or private keys.')
    print('Manually review account identifiers, binary metadata and asset licenses before uploading.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
