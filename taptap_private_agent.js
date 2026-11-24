/* Experimental QuickSDK adapter for an isolated LOCAL private-client process.
 * Host supplies a validated private address and UID; never attach to official client.
 * No credential interception: old QuickSDK startup-token checks are suppressed;
 * local identity is a non-official placeholder, accepted only by local server.
 */
'use strict';
const cfg = __LOCAL_CONFIGURATION__;
const keep = [];
let installed = false;
function install(mod) {
  if (installed) return;
  function api(n, ret, args) { return new NativeFunction(mod.getExportByName(n), ret, args); }
  const domainGet = api('il2cpp_domain_get', 'pointer', []);
  const assembliesGet = api('il2cpp_domain_get_assemblies','pointer',['pointer','pointer']);
  const imageGet = api('il2cpp_assembly_get_image','pointer',['pointer']);
  const classFind = api('il2cpp_class_from_name','pointer',['pointer','pointer','pointer']);
  const methodFind = api('il2cpp_class_get_method_from_name','pointer',['pointer','pointer','int']);
  const strNew = api('il2cpp_string_new','pointer',['pointer']);
  const pin = api('il2cpp_gchandle_new','uint',['pointer','uint8']);
  function utf8(s) { const p = Memory.allocUtf8String(s); keep.push(p); return p; }
  function string(s) { const p = strNew(utf8(s)); pin(p,0); return p; }
  const count = Memory.alloc(Process.pointerSize);
  count.writePointer(ptr(0));
  const domain = domainGet();
  if (domain.isNull()) return;
  const assemblies = assembliesGet(domain,count);
  const length = Process.pointerSize === 8 ? count.readU64().toNumber() : count.readU32();
  function klass(ns,name) {
    for(let i=0;i<length;i++) {
      const k=classFind(imageGet(assemblies.add(i*Process.pointerSize).readPointer()),utf8(ns),utf8(name));
      if(!k.isNull()) return k;
    }
    throw new Error('Required class unavailable: '+ns+'.'+name);
  }
  function method(k,n,arity) {
    const info=methodFind(k,utf8(n),arity);
    if(info.isNull() || info.readPointer().isNull()) throw new Error('Required method unavailable: '+n);
    return {info:info,code:info.readPointer()};
  }
  const quick=klass('quicksdk','QuickSDKImp');
  const nested=api('il2cpp_class_get_nested_types','pointer',['pointer','pointer']);
  const className=api('il2cpp_class_get_name','pointer',['pointer']);
  const parent=klass('','InitConfigAsset'), iter=Memory.alloc(Process.pointerSize);
  iter.writePointer(ptr(0));
  let config=ptr(0), child;
  while(!(child=nested(parent,iter)).isNull()) {
    if(className(child).readUtf8String()==='ConfigProperty'){config=child;break;}
  }
  if(config.isNull())throw new Error('ConfigProperty unavailable');
  const login=method(quick,'login',0), startup=method(quick,'CheckStartArgs',0);
  const success=method(quick,'onLoginSuccess',4);
  const finalServer=method(config,'get_FinalLoginServer',0);
  const invokeSuccess=new NativeFunction(success.code,'void',['pointer','pointer','pointer','pointer','pointer','pointer']);
  const uid=string(String(cfg.uid)), name=string('UID '+cfg.uid), token=string('local-session'), remaining=string('');
  const server=string('http://'+cfg.host+':'+cfg.port);
  const newLogin=new NativeCallback(function(self,mi){
    send({event:'local-login',uid:cfg.uid});
    invokeSuccess(self,uid,name,token,remaining,success.info);
  },'void',['pointer','pointer']);
  const noStartup=new NativeCallback(function(self,mi){send({event:'official-token-check-disabled'});},'void',['pointer','pointer']);
  const localServer=new NativeCallback(function(self,mi){return server;},'pointer',['pointer','pointer']);
  keep.push(newLogin,noStartup,localServer);
  Interceptor.replace(startup.code,noStartup);
  Interceptor.replace(finalServer.code,localServer);
  Interceptor.replace(login.code,newLogin);
  installed=true;
  send({event:'adapter-ready',host:cfg.host,port:cfg.port});
}
Process.attachModuleObserver({onAdded(mod){
 if(mod.name.toLowerCase() !== 'gameassembly.dll')return;
 const init=mod.findExportByName('il2cpp_init');
 if(!init){send({event:'adapter-error',message:'il2cpp_init export unavailable'});return;}
 Interceptor.attach(init,{onLeave(){try{install(mod);}catch(e){send({event:'adapter-error',message:String(e)});}}});
}});
