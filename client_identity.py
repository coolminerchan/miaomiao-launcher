"""Client identity and private-copy boundaries for channel adapters.

Never infer an active login channel solely from the presence of TapTap DLLs.
Never mutate shared official-client assets or reuse a private copy from another
installation. All fingerprints are local; no paths or account material go online.
"""
import hashlib
import json
from pathlib import Path


def fingerprint(client):
    client = Path(client).resolve()
    values = {'source': str(client), 'files': {}}
    for relative in ('launcher.exe', 'GameAssembly.dll', 'launcher_Data/app.info',
                     'launcher_Data/StreamingAssets/Config.txt'):
        path = client / relative
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            values['files'][relative] = digest.hexdigest()
    values['identity'] = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return values


def classify(client):
    client = Path(client)
    plugins = client / 'launcher_Data/Plugins'
    if (plugins / 'x86_64/PCGameSDK.dll').is_file():
        return 'pcgamesdk'
    if (plugins / 'Win/PCSDK_release/PCSDKUI.exe').is_file():
        return 'quicksdk-pc'
    if (plugins / 'x86_64/tapsdkcore.dll').is_file():
        return 'unverified-tap'
    return 'unknown'


def cache_matches(client, marker):
    marker = Path(marker)
    if not marker.is_file():
        return False
    try:
        recorded = json.loads(marker.read_text(encoding='utf-8-sig'))
        return recorded.get('fingerprint') == fingerprint(client)['identity']
    except (ValueError, OSError):
        return False


def assert_private_destination(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    # resolve() follows junctions: the destination must never land in official assets.
    if destination == source or source in destination.parents:
        raise ValueError('Refusing to modify the original official client through a shared path.')
    return destination
