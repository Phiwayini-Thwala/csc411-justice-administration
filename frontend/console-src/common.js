/* ===== Shared console core (identical in the Police, Court and Custody consoles) =====
   Each page defines before this file:  ME  (police | judiciary | correctional)
   and after it: navItems(), VIEWS, loadFor(view) and its own screens. */
const $=s=>document.querySelector(s);
const SVC={
  police:{port:8001,name:'Police Console',org:'Royal Eswatini Police',icon:'👮',does:'Arrest, charge & refer'},
  judiciary:{port:8002,name:'Court Console',org:'Judiciary',icon:'⚖️',does:'Hear, decide & sentence'},
  correctional:{port:8003,name:'Custody Console',org:'Correctional Services',icon:'🏛️',does:'Admit, hold & release'}};
const ONHTTP=location.protocol.startsWith('http');
const HOST=ONHTTP?location.hostname:'localhost';
// Locally the services are localhost:8001-8003. In GitHub Codespaces each port has its
// own address (name-8001.app.github.dev), so swap the port inside the host name instead.
const CODESPACE=/-800[123]\./.test(HOST);
const baseOf=k=>CODESPACE?`https://${HOST.replace(/-800[123]\./,`-${SVC[k].port}.`)}`:`http://${HOST}:${SVC[k].port}`;
const API=ONHTTP?'':baseOf(ME);
const SKEY='jas-'+ME;
let TOKEN=null, USER=null, view='dashboard';

/* ---- labels shared by all consoles (same words for the same status everywhere) ---- */
const COURT={RECEIVED:'Awaiting Hearing',HEARING_SCHEDULED:'Hearing Scheduled',ON_BAIL:'Out on Bail',ON_REMAND:'Held in Custody',SENTENCED:'Sentenced',CLOSED:'Case Closed'};
const POLICE={OPEN:'Open Investigation',REFERRED:'Referred to Court',CLOSED:'Case Closed'};
const CUSTODY={REMAND:'On Remand',CONVICTED:'Serving Sentence',TRANSFERRED:'Transferred',RELEASED:'Released'};
const RELEASE={SENTENCE_COMPLETED:'Sentence completed',ACQUITTED:'Acquitted by the court',COURT_ORDER:'Court order',BAIL_GRANTED:'Bail granted by the court'};
const SYNC={OK:'Delivered',FAILED:'Not delivered',NONE:'Nothing sent yet'};
const roleName=r=>({court_officer:'Court Officer',admin:'Administrator',correctional_officer:'Correctional Officer',police_officer:'Police Officer'}[r]||r);

const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const utc=d=>d&&!/(Z|[+-]\d\d:?\d\d)$/.test(d)?d+'Z':d;           // server times are UTC without a zone
const fmtDate=d=>d?new Date(d).toLocaleString([], {dateStyle:'medium',timeStyle:'short'}):'—';
const fmtDay=d=>d?new Date(d).toLocaleDateString([], {dateStyle:'medium'}):'—';
const money=n=>n==null?'—':'E '+Number(n).toLocaleString([], {minimumFractionDigits:2,maximumFractionDigits:2});
const badge=(s,map)=>s?`<span class="badge b-${esc(s)}">${esc((map||{})[s]||s)}</span>`:'<span class="mut">—</span>';
const syncBadge=s=>badge(s||'NONE',SYNC);
const head=(t,s,right='')=>`<div class="topbar"><div><h1>${t}</h1><div class="sub">${s}</div></div><div>${right}</div></div>`;
const kv=rows=>`<dl class="kv">${rows.filter(r=>r).map(([k,v])=>`<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
const emptyBox=(ic,msg,hint='')=>`<div class="empty"><span class="ic">${ic}</span>${msg}${hint?`<div class="hint">${hint}</div>`:''}</div>`;

function toast(msg,type=''){const t=document.createElement('div');t.className='toast '+type;t.textContent=msg;$('#toasts').append(t);setTimeout(()=>t.remove(),5000)}

async function api(path,method='GET',body){
  const headers={};if(body)headers['Content-Type']='application/json';if(TOKEN)headers.Authorization='Bearer '+TOKEN;
  let r;try{r=await fetch(API+path,{method,headers,body:body?JSON.stringify(body):undefined})}
  catch{throw new Error(`Cannot reach the ${SVC[ME].org} service. Is it running on port ${SVC[ME].port}?`)}
  let data=null;try{data=await r.json()}catch{}
  if(r.status===401&&TOKEN){logout('Your session has expired. Please sign in again.');throw new Error('Session expired')}
  if(r.status===403)throw new Error(data?.message||'Your role is not allowed to do this here.');
  if(!r.ok)throw new Error(data?.message||('Request failed ('+r.status+')'));
  return data;
}

/* ---------- Sign in / out (the same accounts work in every console) ---------- */
async function login(){
  const username=$('#lu').value.trim(),password=$('#lp').value;
  if(!username||!password)return toast('Enter your username and password.','err');
  $('#lbtn').disabled=true;
  try{
    const r=await api('/auth/login','POST',{username,password});
    setSession(r.access_token,{username,role:r.role});start();
  }catch(e){toast(e.message,'err')}finally{$('#lbtn').disabled=false}
}
function setSession(t,u){TOKEN=t;USER=u;try{sessionStorage.setItem(SKEY,JSON.stringify({TOKEN,USER}))}catch{}}
function logout(msg){
  TOKEN=null;USER=null;try{sessionStorage.removeItem(SKEY)}catch{}
  $('#app').classList.add('hidden');$('#login').classList.remove('hidden');$('#lp').value='';
  if(msg)toast(msg,'err');
}
$('#lbtn').onclick=login;$('#lp').onkeydown=e=>{if(e.key==='Enter')login()};

function start(){
  $('#login').classList.add('hidden');$('#app').classList.remove('hidden');
  $('#who').textContent=USER.username;$('#role').textContent=roleName(USER.role);
  const items=navItems();
  $('#nav').innerHTML=items.map(i=>i.length===1?`<div class="menu-label">${i[0]}</div>`:`<button data-v="${i[0]}"><span class="ic">${i[1]}</span>${i[2]}</button>`).join('');
  document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>go(b.dataset.v));
  drawSwitcher();go('dashboard');
}

/* ---------- Navigation ---------- */
async function go(v,...args){
  view=v;
  document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.v===v));
  document.querySelector('aside').classList.remove('open');
  try{await loadFor(v)}
  catch(e){if(TOKEN){$('#main').innerHTML=head(SVC[ME].name,'')+`<div class="card">${emptyBox('🚫',esc(e.message))}</div>`}return}
  VIEWS[v](...args);
}

/* ---------- Modals ---------- */
function openModal(html,wide){$('#modal').className='modal'+(wide?' wide':'');$('#modal').innerHTML=html;$('#modalBg').classList.add('open')}
function closeModal(){$('#modalBg').classList.remove('open')}
$('#modalBg').onclick=e=>{if(e.target.id==='modalBg')closeModal()};
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
async function submit(btn,fn,msg){
  btn.disabled=true;
  try{const r=await fn();closeModal();toast(typeof msg==='function'?msg(r):msg,'ok');await go(view);return r}
  catch(e){toast(e.message,'err');btn.disabled=false}
}

/* ---------- The process strip: where this console sits in the justice chain ---------- */
function flowStrip(){
  const order=['police','judiciary','correctional'];
  return `<div class="flow">${order.map((k,i)=>`${i?'<div class="ar">⇄</div>':''}<div class="st ${k===ME?'me':''}"><span class="ic">${SVC[k].icon}</span><div><b>${SVC[k].org}</b><span>${SVC[k].does}</span></div></div>`).join('')}</div>`;
}

/* ---------- Switch console: carry the sign-in across (one shared JWT secret) ---------- */
function drawSwitcher(){
  $('#svcLinks').innerHTML=['police','judiciary','correctional'].map(k=>
    `<a href="#" data-k="${k}" class="${k===ME?'me':''}"><span class="ic">${SVC[k].icon}</span>${SVC[k].name}<span class="dot" id="dot-${k}"></span></a>`).join('');
  document.querySelectorAll('#svcLinks a').forEach(a=>a.onclick=e=>{
    e.preventDefault();const k=a.dataset.k;if(k===ME)return;
    const target=baseOf(k)+'/ui';
    location.href=TOKEN?`${target}#sso=${encodeURIComponent(TOKEN)}&u=${encodeURIComponent(USER.username)}&r=${encodeURIComponent(USER.role)}`:target;
  });
  pingAll();
}
function takeSso(){
  if(!location.hash.startsWith('#sso='))return false;
  const p=new URLSearchParams(location.hash.slice(1));
  history.replaceState(null,'',location.pathname+location.search);       // never leave the token in the address bar
  const t=p.get('sso');
  try{
    const claims=JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
    if(!claims.exp||claims.exp*1000<Date.now())return false;
    setSession(t,{username:claims.sub||p.get('u'),role:claims.role||p.get('r')});return true;
  }catch{return false}
}

/* ---------- Service status ---------- */
async function pingOne(k){
  try{const r=await fetch((k===ME?API:baseOf(k))+'/');if(!r.ok)throw 0;return true}catch{return false}
}
async function pingAll(){
  for(const k of ['police','judiciary','correctional']){
    const ok=await pingOne(k);const d=$('#dot-'+k);if(d)d.className='dot '+(ok?'on':'off');
    if(k===ME){$('#dot').className='dot '+(ok?'on':'off');$('#svcStatus').textContent=ok?'Service online':'Service unreachable'}
  }
}
setInterval(pingAll,15000);

/* ---------- Audit (admin) ---------- */
function auditView(icons,what){
  $('#main').innerHTML=head('Activity History',`Every action recorded in the ${what} database, newest first.`)+`<div class="card" id="al">Loading…</div>`;
  api('/audit-logs?limit=200').then(logs=>{
    $('#al').innerHTML=logs.length?`<ul class="timeline">`+logs.map(l=>{const [i,t]=icons[l.action]||['📝',l.action.replace(/_/g,' ').toLowerCase()];
      return `<li><div class="tl-ic">${i}</div><div><b>${esc(t)}</b> · ${esc(l.record_id||'')}<div class="mut">${esc(l.username)} (${esc(roleName(l.role))}) · ${fmtDate(utc(l.time||l.timestamp))}</div></div></li>`}).join('')+`</ul>`:
      emptyBox('🧾','No activity recorded yet.');
  }).catch(e=>{$('#al').innerHTML=emptyBox('🚫','Could not load history: '+esc(e.message))});
}

/* ---------- Boot: restore the session after a refresh or a console switch ---------- */
function boot(){
  if(takeSso())return start();
  try{const s=JSON.parse(sessionStorage.getItem(SKEY)||'null');if(s?.TOKEN){TOKEN=s.TOKEN;USER=s.USER;return start()}}catch{}
  pingAll();
}
