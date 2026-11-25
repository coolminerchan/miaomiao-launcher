"""Experimental, version-locked isolated QuickSDK private-client runner.

Never attach to a running official client. Only spawn a source-fingerprinted copy
under profiles/<mode>/client. Fail closed if instrumentation cannot install.
"""
import argparse
import hashlib
import ipaddress
import json
import threading
import time
from pathlib import Path

SUPPORTED_GAME_ASSEMBLY = '2db98364241c95864781f77877523b9d2f728b22a91935fa30cdfb33a8b7f4ea'

# The Steam build ships the same QuickSDK types the adapter hooks, so it can run
# against a local world too. Each supported build is pinned by its own hash; an
# unknown binary still fails closed instead of being instrumented blindly.
SUPPORTED_BUILDS = {
    SUPPORTED_GAME_ASSEMBLY: 'quicksdk-pc',
    '4787fc3abaf911890fd6bccae6d0f85904f7c959a5d14c55f5dc56b75fe82cab': 'steam',
}


def validated_config(client, host, port, uid):
    from client_identity import classify
    client = Path(client).resolve()
    if 'profiles' not in client.parts or client.name != 'client':
        raise ValueError('Adapter must run an isolated profiles/<mode>/client copy.')
    if classify(client) != 'quicksdk-pc':
        raise ValueError('This adapter supports verified QuickSDK PC layout only.')
    address = ipaddress.IPv4Address(host)
    if not (address.is_loopback or any(address in ipaddress.IPv4Network(n)
                                     for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))):
        raise ValueError('Only loopback or private LAN server addresses are permitted.')
    if not 1 <= int(port) <= 65535 or not 1 <= int(uid) <= 0xffffffff:
        raise ValueError('Invalid local port or UID.')
    digest = hashlib.sha256((client/'GameAssembly.dll').read_bytes()).hexdigest()
    if digest not in SUPPORTED_BUILDS:
        raise ValueError('Unverified GameAssembly version; refuse to apply this experimental adapter.')
    return {'host':str(address),'port':int(port),'uid':int(uid),
            # Only the pinned Steam build opts out of the developer error overlay.
            # File logging and ordinary game failure/disconnection dialogs remain.
            'quietErrorOverlay': SUPPORTED_BUILDS[digest] == 'steam'}


def agent_source(config):
    text=Path(__file__).with_name('taptap_private_agent.js').read_text(encoding='utf-8')
    return text.replace('__LOCAL_CONFIGURATION__',json.dumps(config),1)


def run(client,host,port,uid,log_path,result_path=None):
    config=validated_config(client,host,port,uid)
    import frida
    client=Path(client).resolve()
    device=frida.get_local_device()
    ready=threading.Event(); done=threading.Event(); failed=[]
    log=Path(log_path);log.parent.mkdir(parents=True,exist_ok=True)
    def message(payload,data):
        event=payload.get('payload',{}) if payload.get('type')=='send' else {'event':'adapter-error','message':payload.get('description','Agent error')}
        with log.open('a',encoding='utf-8') as out:out.write(json.dumps(event,ensure_ascii=False)+'\n')
        if event.get('event')=='adapter-ready': ready.set()
        if event.get('event')=='adapter-error':failed.append(event);done.set()
    pid=device.spawn([str(client/'launcher.exe'),'-logFile',str(log.with_name('Player.log'))],cwd=str(client))
    try:
        session=device.attach(pid)
        session.on('detached',lambda *args:done.set())
        script=session.create_script(agent_source(config))
        script.on('message',message);script.load();device.resume(pid)
        start=time.monotonic()
        while not ready.is_set() and not done.is_set() and time.monotonic()-start<40:done.wait(.1)
        if not ready.is_set() or failed:
            raise RuntimeError('QuickSDK adapter failed before ready; terminating private test client.')
        result={'pid':pid,'adapter':'quicksdk-local','ready':True}
        if result_path:
            from profile_manager import write_json
            write_json(Path(result_path),result)
        print(json.dumps(result),flush=True)
        done.wait()
        if failed:raise RuntimeError('Private adapter reported an error; terminating client.')
    finally:
        try:device.kill(pid)
        except Exception:pass


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--client',type=Path,required=True)
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=18080)
    p.add_argument('--uid',type=int,default=1000000)
    p.add_argument('--log',type=Path,required=True)
    p.add_argument('--result-path',type=Path)
    a=p.parse_args();run(a.client,a.host,a.port,a.uid,a.log,a.result_path)
