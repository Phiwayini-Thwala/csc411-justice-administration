/* ===================== Custody Console (Correctional Services, port 8003) ===================== */
let INMATES=[], filter={q:'',s:''};
const STATUS=CUSTODY;
const canAct=()=>USER&&['correctional_officer','admin'].includes(USER.role);
const byId=id=>INMATES.find(i=>i.inmate_id===id);
const inCustody=i=>i.status!=='RELEASED';
const FACILITIES=['Matsapha Correctional Centre','Sidwashini Correctional Centre','Mawelawela Correctional Centre (Women)','Bhalekane Correctional Centre','Big Bend Correctional Centre','Mbabane Remand Centre','Malkerns Juvenile Centre'];
const facilityOptions=(cur,skip)=>FACILITIES.filter(f=>f!==skip).map(f=>`<option ${f===cur?'selected':''}>${esc(f)}</option>`).join('');
const legal=i=>i.legal_status||(i.sentence_months?'CONVICTED':'REMAND');
const endOf=i=>{if(!i.sentence_months)return null;const d=new Date(utc(i.admitted_at));d.setMonth(d.getMonth()+i.sentence_months);return d};

function navItems(){
  const items=[['Overview'],['dashboard','🏠','Dashboard'],['Inmates'],['inmates','🗂️','All Inmate Records']];
  if(canAct())items.push(['admit','➕','Admit an Inmate'],['Custody Actions'],['transfer','🚐','Transfer an Inmate'],['release','🚪','Release an Inmate'],['convict','📝','Record a Conviction']);
  if(USER.role==='admin')items.push(['Records'],['audit','🧾','Activity History']);
  return items;
}
async function loadFor(v){if(v!=='admit'&&v!=='audit')INMATES=await api('/inmates')}

/* ---------- Dashboard ---------- */
function dashboard(){
  const now=INMATES.filter(inCustody);
  const stats=[['In Custody Now',now.length,'🏛️','var(--brand)'],['On Remand',now.filter(i=>legal(i)==='REMAND').length,'⏳','var(--muted)'],
    ['Serving Sentence',now.filter(i=>legal(i)==='CONVICTED').length,'🔒','var(--bad)'],['Transferred',INMATES.filter(i=>i.status==='TRANSFERRED').length,'🚐','var(--warn)'],
    ['Released',INMATES.filter(i=>i.status==='RELEASED').length,'🚪','var(--ok)'],['Total Records',INMATES.length,'🗂️','var(--info)']];
  const due=now.filter(i=>endOf(i)&&endOf(i)-Date.now()<1000*60*60*24*60).sort((a,b)=>endOf(a)-endOf(b));
  const unsynced=INMATES.filter(i=>i.court_sync==='FAILED').length;
  const byFac={};now.forEach(i=>byFac[i.facility]=(byFac[i.facility]||0)+1);
  const qa=canAct()?`<h2>What would you like to do?</h2><div class="qa">
    <button onclick="go('admit')"><span class="ic">➕</span><b>Admit an Inmate</b><span class="d">Record a new admission</span></button>
    <button onclick="go('transfer')"><span class="ic">🚐</span><b>Transfer an Inmate</b><span class="d">Move to another facility</span></button>
    <button onclick="go('release')"><span class="ic">🚪</span><b>Release an Inmate</b><span class="d">Sentence served or court order</span></button>
    <button onclick="go('inmates')"><span class="ic">🔎</span><b>Find a Record</b><span class="d">Search by name, ID or case</span></button></div>`:'';
  $('#main').innerHTML=head('Welcome, '+esc(USER.username),'Here is who is in custody across the correctional facilities.',
    canAct()?`<button class="btn primary" onclick="go('admit')">➕ Admit an Inmate</button>`:'')+flowStrip()+
  `<div class="grid">${stats.map(s=>`<div class="card stat"><div class="l">${s[2]} ${s[0]}</div><div class="n">${s[1]}</div><div class="bar" style="background:${s[3]};opacity:.7"></div></div>`).join('')}</div>
  ${unsynced?`<div class="notice">⚠️ ${unsynced} transfer or release${unsynced>1?'s have':' has'} not reached the Judiciary yet. Open the inmate record and choose “Resend to Court”.</div>`:''}${qa}
  <div class="row2" style="gap:16px;margin-top:6px">
   <div><h2>Occupancy by Facility</h2><div class="card">${Object.keys(byFac).length?Object.entries(byFac).sort((a,b)=>b[1]-a[1]).map(([f,n])=>`<div style="margin-bottom:12px"><div style="display:flex;justify-content:space-between"><b>${esc(f)}</b><span>${n}</span></div><div class="progress"><i style="width:${(n/now.length*100).toFixed(0)}%"></i></div></div>`).join(''):emptyBox('🏛️','Nobody is in custody.')}</div></div>
   <div><h2>Releases Due in 60 Days</h2><div class="card">${due.length?`<ul class="timeline">${due.map(i=>`<li><div class="tl-ic">📆</div><div><b>${esc(i.full_name)}</b> · ${esc(i.inmate_id)}<div class="mut">${fmtDay(endOf(i))} · ${esc(i.facility)}</div></div></li>`).join('')}</ul>`:emptyBox('📆','No releases due soon.')}</div></div>
  </div>
  <h2>Most Recent Admissions</h2><div class="card tbl">${inmateTable(INMATES.slice(0,5))}</div>`;
}

/* ---------- Inmates ---------- */
function acts(i){
  const a=canAct()&&inCustody(i);
  return `<div class="acts"><button class="btn sm" onclick="openInmate('${esc(i.inmate_id)}')">📄 View Record</button>
   ${a?`<button class="btn sm" onclick="openTransfer('${esc(i.inmate_id)}')">🚐 Transfer</button>`:''}
   ${a&&legal(i)==='REMAND'?`<button class="btn sm" onclick="openConvict('${esc(i.inmate_id)}')">📝 Convict</button>`:''}
   ${a?`<button class="btn sm primary" onclick="openRelease('${esc(i.inmate_id)}')">🚪 Release</button>`:''}</div>`;
}
function inmateTable(list){
  if(!list.length)return emptyBox('🗂️','No inmate records to show.');
  return `<table><thead><tr><th>Inmate</th><th>Name</th><th>Court Case</th><th>Status</th><th>Facility</th><th>Sentence</th><th>Actions</th></tr></thead><tbody>`+
  list.map(i=>`<tr><td class="name">${esc(i.inmate_id)}<div class="mut">Admitted ${fmtDay(utc(i.admitted_at))}</div></td>
   <td class="name">${esc(i.full_name)}<div class="mut">ID ${esc(i.national_id)}</div></td>
   <td>${esc(i.court_case_id)}</td>
   <td>${badge(i.status,STATUS)}${i.status==='TRANSFERRED'?`<div class="mut">${legal(i)==='REMAND'?'On remand':'Serving sentence'}</div>`:''}</td>
   <td style="max-width:200px">${esc(i.facility)}</td>
   <td>${i.sentence_months?`${i.sentence_months} months${inCustody(i)?`<div class="mut">until ${fmtDay(endOf(i))}</div>`:''}`:'<span class="mut">—</span>'}</td>
   <td>${acts(i)}</td></tr>`).join('')+`</tbody></table>`;
}
function inmates(){
  $('#main').innerHTML=head('All Inmate Records','Search, filter and act on every custody record.',
    canAct()?`<button class="btn primary" onclick="go('admit')">➕ Admit an Inmate</button>`:'')+
  `<div class="toolbar"><input id="q" placeholder="🔍 Search by name, national ID, inmate or court case…" value="${esc(filter.q)}">
   <select id="fs"><option value="">All statuses</option>${Object.entries(STATUS).map(([k,v])=>`<option value="${k}" ${filter.s===k?'selected':''}>${v}</option>`).join('')}</select></div>
   <div class="card tbl" id="tbl"></div>`;
  const draw=()=>{
    filter.q=$('#q').value;filter.s=$('#fs').value;const q=filter.q.toLowerCase();
    $('#tbl').innerHTML=inmateTable(INMATES.filter(i=>(!filter.s||i.status===filter.s)&&(!q||[i.inmate_id,i.full_name,i.national_id,i.court_case_id,i.facility].join(' ').toLowerCase().includes(q))));
  };
  $('#q').oninput=draw;$('#fs').onchange=draw;draw();
}

/* ---------- Admit ---------- */
function admit(){
  $('#main').innerHTML=head('Admit an Inmate','Normally the Judiciary admits people automatically when it remands or sentences them. Use this form to capture an admission manually.')+
  `<div class="card form-card">
    <div class="row2"><div><label>Full name</label><input id="fn" placeholder="e.g. Sipho Dlamini"></div><div><label>National ID</label><input id="ni" placeholder="13 digits"></div></div>
    <label>Court case number</label><input id="cc" placeholder="e.g. CRT-2026-0003">
    <label>Admission type</label>
    <div class="seg"><label><input type="radio" name="at" value="REMAND" checked> ⏳ Remand (awaiting trial)</label><label><input type="radio" name="at" value="CONVICTED"> 🔒 Convicted (sentenced)</label></div>
    <div class="row2"><div><label>Facility</label><select id="fc">${facilityOptions(FACILITIES[0])}</select></div>
    <div id="smw" class="hidden"><label>Sentence (months)</label><input id="sm" type="number" min="1" placeholder="e.g. 24"></div></div>
    <div class="hint">One court case can only have one person in custody at a time.</div>
    <div style="margin-top:22px;display:flex;gap:10px"><button class="btn primary" id="sv">💾 Admit Inmate</button><button class="btn" onclick="go('inmates')">Cancel</button></div>
  </div>`;
  document.querySelectorAll('[name=at]').forEach(r=>r.onchange=()=>$('#smw').classList.toggle('hidden',document.querySelector('[name=at]:checked').value!=='CONVICTED'));
  $('#sv').onclick=async()=>{
    const t=document.querySelector('[name=at]:checked').value;
    const body={full_name:$('#fn').value.trim(),national_id:$('#ni').value.trim(),court_case_id:$('#cc').value.trim(),admission_type:t,facility:$('#fc').value};
    if(!body.full_name||!body.national_id||!body.court_case_id)return toast('Fill in the name, national ID and court case number.','err');
    if(t==='CONVICTED'){const m=parseInt($('#sm').value);if(!m||m<1)return toast('Enter the sentence in months.','err');body.sentence_months=m}
    $('#sv').disabled=true;
    try{const r=await api('/inmates','POST',body);toast('Admitted as '+r.inmate_id+'.','ok');go('inmates')}catch(e){toast(e.message,'err');$('#sv').disabled=false}
  };
}

/* ---------- Pickers ---------- */
const PK={
  transfer:['Transfer an Inmate','Choose who to move. The Judiciary is told about the new facility automatically.','🚐 Transfer','openTransfer',i=>inCustody(i)],
  release:['Release an Inmate','Choose who to release. A completed sentence closes the court case and the police case.','🚪 Release','openRelease',i=>inCustody(i)],
  convict:['Record a Conviction','Normally the court does this when it delivers a guilty verdict. Choose a remand inmate to record the sentence manually.','📝 Convict','openConvict',i=>inCustody(i)&&legal(i)==='REMAND']};
function picker(k){
  const [t,s,label,fn,ok]=PK[k];const list=INMATES.filter(ok);
  $('#main').innerHTML=head(t,s)+`<div class="card tbl">${list.length?`<table><thead><tr><th>Inmate</th><th>Name</th><th>Status</th><th>Facility</th><th></th></tr></thead><tbody>`+
   list.map(i=>`<tr><td class="name">${esc(i.inmate_id)}</td><td>${esc(i.full_name)}<div class="mut">${esc(i.court_case_id)}</div></td><td>${badge(i.status,STATUS)}</td><td>${esc(i.facility)}</td>
   <td style="text-align:right"><button class="btn primary sm" onclick="${fn}('${esc(i.inmate_id)}')">${label}</button></td></tr>`).join('')+`</tbody></table>`:
   emptyBox('🎉','Nobody is waiting for this step.')}</div>`;
}

/* ---------- Modals ---------- */
const inmateBox=i=>`<div class="casebox"><b>${esc(i.inmate_id)}</b> — ${esc(i.full_name)} ${badge(i.status,STATUS)}<div class="mut">${esc(i.facility)} · Court case ${esc(i.court_case_id)}</div></div>`;
async function openInmate(id){
  let i;try{i=await api('/inmates/'+id)}catch(e){return toast(e.message,'err')}
  const end=endOf(i);let prog='';
  if(end&&inCustody(i)){const st=new Date(utc(i.admitted_at)),pct=Math.max(0,Math.min(100,(Date.now()-st)/(end-st)*100));prog=`<div class="progress"><i style="width:${pct.toFixed(0)}%"></i></div><div class="hint">${pct.toFixed(0)}% of the sentence served</div>`}
  const hist=[...i.transfers.map(t=>[t.transferred_at,'🚐','Transferred',`${t.from_facility} → ${t.new_facility}${t.reason?' · '+t.reason:''}`,t.by_user]),
    ...i.releases.map(r=>[r.released_at,'🚪','Released',`${RELEASE[r.reason]||r.reason}${r.notes?' · '+r.notes:''}`,r.by_user])].sort((a,b)=>a[0]<b[0]?-1:1);
  const a=canAct()&&inCustody(i);
  openModal(`<h3>📄 Inmate Record ${esc(i.inmate_id)} ${badge(i.status,STATUS)}</h3>
  <div class="sect">Person</div>${kv([['Full name',esc(i.full_name)],['National ID',esc(i.national_id)],['Court case',esc(i.court_case_id)]])}
  <div class="sect">Custody</div>${kv([['Legal status',legal(i)==='REMAND'?'On remand (awaiting trial)':'Convicted'],['Admitted',fmtDate(utc(i.admitted_at))+' as '+(i.admission_type==='REMAND'?'remand':'convicted')],
    ['Facility',esc(i.facility)],['Sentence',i.sentence_months?`${i.sentence_months} months`:'—'],end&&['Expected release',fmtDay(end)],i.released_at&&['Released',fmtDate(utc(i.released_at))]])}${prog}
  <div class="sect">Movement History</div>${hist.length?`<ul class="timeline">${hist.map(h=>`<li><div class="tl-ic">${h[1]}</div><div><b>${h[2]}</b><div>${esc(h[3])}</div><div class="mut">${esc(h[4])} · ${fmtDate(utc(h[0]))}</div></div></li>`).join('')}</ul>`:'<div class="mut">No transfers or releases yet.</div>'}
  <div class="sect">Reported to the Judiciary</div>
  <div class="syncrow">${syncBadge(i.court_sync)}<span class="mut">${esc(i.court_sync_message||'Transfers and releases are reported to the court automatically.')}</span>
   ${canAct()&&hist.length?`<button class="btn sm" id="rs">📨 Resend to Court</button>`:''}</div>
  <div class="sect">Court case behind this record (live from the Judiciary)</div><div id="linked" class="mut">Loading…</div>
  <div class="foot">${a?`<button class="btn" onclick="openEdit('${esc(id)}')">✏️ Correct Details</button><button class="btn" onclick="openTransfer('${esc(id)}')">🚐 Transfer</button>`:''}
  ${a&&legal(i)==='REMAND'?`<button class="btn" onclick="openConvict('${esc(id)}')">📝 Convict</button>`:''}
  ${a?`<button class="btn primary" onclick="openRelease('${esc(id)}')">🚪 Release</button>`:''}
  <button class="btn" onclick="closeModal()">Close</button></div>`,true);
  if($('#rs'))$('#rs').onclick=()=>submit($('#rs'),()=>api(`/inmates/${id}/notify-court`,'POST'),r=>r.court_sync==='OK'?'Court record updated.':'Judiciary still not reachable.');
  api(`/inmates/${id}/linked`).then(l=>{
    const c=l.court_case;if(!c){$('#linked').innerHTML=`<div class="journey"><div class="col err">${esc(l.court_error||'Not available')}</div></div>`;return}
    const d=c.decisions&&c.decisions.length?c.decisions[c.decisions.length-1]:null;
    $('#linked').innerHTML=`<div class="journey"><div class="col"><h4>⚖️ Court case</h4>${kv([['Case',esc(c.court_case_id)],['Status',badge(c.status,COURT)],['Police ref',esc(c.police_case_id)]])}</div>
     <div class="col"><h4>📜 Charges</h4>${(c.charges||[]).map(x=>`<span class="chip"><b>${esc(x.offence)}</b></span>`).join('')||'—'}</div>
     <div class="col"><h4>🔨 Latest decision</h4>${d?esc(d.kind==='VERDICT'?(d.verdict==='GUILTY'?'Guilty':'Not guilty')+(d.sentence_months?` · ${d.sentence_months} months`:''):d.kind==='REMAND'?'Remanded: '+(d.reason||''):'Bail '+money(d.amount))+`<div class="mut">${fmtDate(utc(d.decided_at))}</div>`:'<span class="mut">No decision yet</span>'}</div></div>`;
  }).catch(e=>{$('#linked').innerHTML=`<div class="err">${esc(e.message)}</div>`});
}
function openTransfer(id){
  const i=byId(id);
  openModal(`<h3>🚐 Transfer an Inmate</h3>${inmateBox(i)}
   <label>New facility</label><select id="nf">${facilityOptions('',i.facility)}</select>
   <label>Reason</label><input id="rr" placeholder="e.g. Overcrowding, medical care, rehabilitation programme">
   <div class="notice">ℹ️ The Judiciary is told about the move, and passes it on to the Police case.</div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Transfer</button></div>`);
  $('#ok').onclick=()=>{const r=$('#rr').value.trim();if(!r)return toast('Enter the reason for the transfer.','err');
    submit($('#ok'),()=>api(`/inmates/${id}/transfer`,'PUT',{new_facility:$('#nf').value,reason:r}),r=>`Transferred to ${r.facility}.`+(r.court_sync==='FAILED'?' (Court not reachable — resend later.)':''))};
}
function openRelease(id){
  const i=byId(id),end=endOf(i);
  openModal(`<h3>🚪 Release an Inmate</h3>${inmateBox(i)}
   <label>Reason</label><select id="rr"><option value="SENTENCE_COMPLETED" ${legal(i)==='CONVICTED'?'selected':''}>Sentence completed</option><option value="COURT_ORDER" ${legal(i)==='REMAND'?'selected':''}>Court order</option></select>
   <label>Notes</label><textarea id="rn" rows="2" placeholder="Optional"></textarea>
   ${end&&end>Date.now()?`<div class="notice">⚠️ The sentence runs until ${fmtDay(end)}.</div>`:''}
   <div class="hint">Acquittals and bail are sent by the court automatically. A completed sentence closes the court case, which then closes the police case.</div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Release</button></div>`);
  $('#ok').onclick=()=>submit($('#ok'),()=>api(`/inmates/${id}/release`,'POST',{reason:$('#rr').value,notes:$('#rn').value.trim()||null}),r=>'Inmate released.'+(r.court_sync==='FAILED'?' (Court not reachable — resend later.)':''));
}
function openConvict(id){
  const i=byId(id);
  openModal(`<h3>📝 Record a Conviction</h3>${inmateBox(i)}
   <label>Sentence (months)</label><input type="number" id="sm" min="1" placeholder="e.g. 12">
   <div class="notice">⚠️ The court normally does this when it delivers a guilty verdict. Only use it to capture a sentence the court has already passed.</div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Record Conviction</button></div>`);
  $('#ok').onclick=()=>{const m=parseInt($('#sm').value);if(!m||m<1)return toast('Enter the sentence in months.','err');
    submit($('#ok'),()=>api(`/inmates/${id}/status`,'PUT',{status:'CONVICTED',sentence_months:m}),'Conviction recorded.')};
}
function openEdit(id){
  const i=byId(id);
  openModal(`<h3>✏️ Correct Details</h3>${inmateBox(i)}
   <label>Full name</label><input id="fn" value="${esc(i.full_name)}">
   ${legal(i)==='CONVICTED'?`<label>Sentence (months)</label><input id="sm" type="number" min="1" value="${esc(i.sentence_months)}">`:''}
   <div class="hint">To change the facility use Transfer, so the move is recorded and reported.</div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Save</button></div>`);
  $('#ok').onclick=()=>{const b={full_name:$('#fn').value.trim()};if($('#sm'))b.sentence_months=parseInt($('#sm').value)||null;
    if(!b.full_name)return toast('The name cannot be empty.','err');
    submit($('#ok'),()=>api(`/inmates/${id}`,'PUT',b),'Details updated.')};
}

const AICON={LOGIN:['🔐','Signed in'],INMATE_ADMITTED:['➕','Inmate admitted'],STATUS_UPDATED:['📝','Legal status updated'],INMATE_TRANSFERRED:['🚐','Inmate transferred'],
  INMATE_RELEASED:['🚪','Inmate released'],INMATE_DETAILS_UPDATED:['✏️','Details corrected'],COURT_NOTIFIED:['📨','Judiciary informed']};

const VIEWS={dashboard,inmates,admit,transfer:()=>picker('transfer'),release:()=>picker('release'),convict:()=>picker('convict'),audit:()=>auditView(AICON,'correctional')};
