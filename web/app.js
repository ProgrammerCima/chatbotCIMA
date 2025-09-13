async function loadCfg(){
  const r = await fetch('/api/config'); const j = await r.json();
  system.value = j.system_prompt; temp.value = j.temp; maxn.value = j.max_new_tokens;
  allow.value = j.allow_out_of_scope ? "true":"false";
}
async function saveCfg(){
  const fd = new FormData();
  fd.append('system_prompt', system.value);
  fd.append('temp', temp.value);
  fd.append('max_new_tokens', maxn.value);
  fd.append('allow_out_of_scope', allow.value);
  const r = await fetch('/api/config', {method:'PUT', body:fd});
  cfgStatus.textContent = r.ok ? '✅' : '❌';
}
async function sendDoc(){
  const f = doc.files[0]; if(!f){docStatus.textContent="❌";return;}
  const fd = new FormData(); fd.append('file', f);
  const r = await fetch('/api/docs', {method:'POST', body:fd});
  docStatus.textContent = r.ok ? '✅' : '❌';
}
async function askChat(){
  const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message: msg.value})});
  const j = await r.json(); resp.textContent = j.response || JSON.stringify(j);
}
const system=document.getElementById('system');
const temp=document.getElementById('temp');
const maxn=document.getElementById('maxn');
const allow=document.getElementById('allow');
const cfgStatus=document.getElementById('cfgStatus');
const doc=document.getElementById('doc');
const docStatus=document.getElementById('docStatus');
const msg=document.getElementById('msg');
const resp=document.getElementById('resp');
document.getElementById('saveCfg').onclick=saveCfg;
document.getElementById('sendDoc').onclick=sendDoc;
document.getElementById('ask').onclick=askChat;
loadCfg();
