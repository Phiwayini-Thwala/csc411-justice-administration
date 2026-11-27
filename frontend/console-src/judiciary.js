/* ===================== Court Console (Judiciary, port 8002) ===================== */
let CASES=[], filter={q:'',s:''};
const STATUS=COURT;
const OPEN_FOR={ // which statuses allow each action (matches the service rules)
  schedule:['RECEIVED','HEARING_SCHEDULED','ON_BAIL','ON_REMAND'],
  bail:['HEARING_SCHEDULED','ON_REMAND'],
  remand:['HEARING_SCHEDULED','ON_BAIL'],
  verdict:['HEARING_SCHEDULED','ON_BAIL','ON_REMAND']};
const canAct=()=>USER&&['court_officer','admin'].includes(USER.role);
const can=(a,c)=>canAct()&&OPEN_FOR[a].includes(c.status);
const byId=id=>CASES.find(c=>c.court_case_id===id);

function navItems(){
  const items=[['Overview'],['dashboard','🏠','Dashboard'],['Cases'],['cases','📁','All Court Cases']];
  if(canAct())items.push(['register','➕','Receive a Referred Case'],['Court Proceedings'],
    ['schedule','📅','Schedule a Hearing'],['bail','🔓','Grant Bail'],['remand','🔒','Remand in Custody'],['verdict','🔨','Deliver Verdict & Sentence']);
  if(USER.role==='admin')items.push(['Records'],['audit','🧾','Activity History']);
  return items;
}
async function loadFor(v){if(v!=='register'&&v!=='audit')CASES=await api('/court-cases')}

/* ---------- Dashboard ---------- */
function dashboard(){
  const n=s=>CASES.filter(c=>c.status===s).length;
  const stats=[['Total Cases',CASES.length,'📁','var(--brand)'],['Awaiting Hearing',n('RECEIVED'),'⏳','var(--info)'],['Hearing Scheduled',n('HEARING_SCHEDULED'),'📅','var(--brand)'],
    ['Out on Bail',n('ON_BAIL'),'🔓','var(--warn)'],['Held in Custody',n('ON_REMAND'),'🔒','var(--muted)'],['Sentenced',n('SENTENCED'),'🔨','var(--bad)'],['Cases Closed',n('CLOSED'),'✅','var(--ok)']];
  const recent=[...CASES].reverse().slice(0,5);
  const unsynced=CASES.filter(c=>c.police_sync==='FAILED').length;
  const qa=canAct()?`<h2>What would you like to do?</h2><div class="qa">
    <button onclick="go('schedule')"><span class="ic">📅</span><b>Schedule a Hearing</b><span class="d">Set a trial or hearing date</span></button>
    <button onclick="go('bail')"><span class="ic">🔓</span><b>Grant Bail</b><span class="d">Release the suspect on conditions</span></button>
    <button onclick="go('remand')"><span class="ic">🔒</span><b>Remand in Custody</b><span class="d">Hold the suspect at a facility</span></button>
    <button onclick="go('verdict')"><span class="ic">🔨</span><b>Deliver a Verdict</b><span class="d">Record outcome &amp; sentence</span></button></div>`:'';
  $('#main').innerHTML=head('Welcome, '+esc(USER.username),'Here is what is happening across the court docket.',
    canAct()?`<button class="btn primary" onclick="go('register')">➕ Receive a Referred Case</button>`:'')+flowStrip()+
  `<div class="grid">${stats.map(s=>`<div class="card stat"><div class="l">${s[2]} ${s[0]}</div><div class="n">${s[1]}</div><div class="bar" style="background:${s[3]};opacity:.7"></div></div>`).join('')}</div>
  ${unsynced?`<div class="notice">⚠️ ${unsynced} case${unsynced>1?'s have':' has'} court news the Police service has not received yet. Open the case file and choose “Resend to Police”.</div>`:''}${qa}
  <h2>Most Recent Cases</h2><div class="card tbl">${caseTable(recent)}</div>`;
}

/* ---------- Cases ---------- */
function caseTable(list){
  if(!list.length)return emptyBox('📂','No cases to show yet.');
  return `<table><thead><tr><th>Case</th><th>Suspect</th><th>Charges</th><th>Status</th><th>Next Hearing</th><th>Actions</th></tr></thead><tbody>`+
  list.map(c=>{
    const last=c.hearings.length?c.hearings[c.hearings.length-1]:null;
    return `<tr>
    <td><div class="name">${esc(c.court_case_id)}</div><div class="mut">Police ref ${esc(c.police_case_id)}</div></td>
    <td class="name">${esc(c.suspect.full_name)}<div class="mut">ID ${esc(c.suspect.national_id)}</div></td>
    <td style="max-width:220px">${esc(c.charges.map(x=>x.offence).join(', '))}</td>
    <td>${badge(c.status,STATUS)}${c.inmate_id?`<div class="mut">Inmate ${esc(c.inmate_id)}</div>`:''}</td>
    <td>${last?fmtDate(last.hearing_date):'—'}</td>
    <td><div class="acts">
      <button class="btn sm" onclick="openCase('${esc(c.court_case_id)}')">📄 View Case File</button>
      ${can('schedule',c)?`<button class="btn sm" onclick="openSchedule('${esc(c.court_case_id)}')">📅 Schedule Hearing</button>`:''}
      ${can('bail',c)?`<button class="btn sm" onclick="openBail('${esc(c.court_case_id)}')">🔓 Grant Bail</button>`:''}
      ${can('remand',c)?`<button class="btn sm" onclick="openRemand('${esc(c.court_case_id)}')">🔒 Remand</button>`:''}
      ${can('verdict',c)?`<button class="btn sm primary" onclick="openVerdict('${esc(c.court_case_id)}')">🔨 Deliver Verdict</button>`:''}
    </div></td></tr>`}).join('')+`</tbody></table>`;
}
function cases(){
  $('#main').innerHTML=head('All Court Cases','Search, filter and act on every case in the system.',
    canAct()?`<button class="btn primary" onclick="go('register')">➕ Receive a Referred Case</button>`:'')+
  `<div class="toolbar"><input id="q" placeholder="🔍 Search by name, case number or charge…" value="${esc(filter.q)}">
   <select id="fs"><option value="">All statuses</option>${Object.entries(STATUS).map(([k,v])=>`<option value="${k}" ${filter.s===k?'selected':''}>${v}</option>`).join('')}</select></div>
   <div class="card tbl" id="tbl"></div>`;
  const draw=()=>{
    filter.q=$('#q').value;filter.s=$('#fs').value;const q=filter.q.toLowerCase();
    $('#tbl').innerHTML=caseTable(CASES.filter(c=>(!filter.s||c.status===filter.s)&&(!q||[c.court_case_id,c.police_case_id,c.suspect.full_name,c.suspect.national_id,...c.charges.map(x=>x.offence)].join(' ').toLowerCase().includes(q))));
  };
  $('#q').oninput=draw;$('#fs').onchange=draw;draw();
}

/* ---------- Case file (read only) ---------- */
function describeDecision(d){
  if(d.kind==='BAIL')return ['🔓','Bail granted',`Bail ${money(d.amount)}. Conditions: ${d.conditions}`];
  if(d.kind==='REMAND')return ['🔒','Remanded in custody',`${d.reason}. Facility: ${d.facility}. Next hearing ${fmtDate(d.next_hearing_date)}`];
  const t={IMPRISONMENT:`Imprisonment for ${d.sentence_months} months${d.facility?' at '+d.facility:''}`,FINE:`Fine of ${money(d.fine_amount)}`,SUSPENDED:'Suspended sentence'}[d.sentence_type];
  return ['🔨',d.verdict==='GUILTY'?'Verdict: Guilty':'Verdict: Not Guilty',d.verdict==='GUILTY'?t:'The suspect was acquitted.'];
}
function describeCustody(e){
  if(e.event==='TRANSFERRED')return ['🚐','Transferred by Correctional Services',`Now held at ${e.facility||'—'}${e.reason?'. Reason: '+e.reason:''}`];
  return ['🚪','Released by Correctional Services',`${RELEASE[e.reason]||e.reason||'Released'}${e.notes?'. '+e.notes:''}`];
}
function openCase(id){
  const c=byId(id),s=c.suspect;
  openModal(`<h3>📄 Case File ${esc(c.court_case_id)} ${badge(c.status,STATUS)}</h3>
  <div class="sect">Suspect</div>
  <dl class="kv"><dt>Full name</dt><dd>${esc(s.full_name)}</dd><dt>National ID</dt><dd>${esc(s.national_id)}</dd>
  <dt>Date of birth</dt><dd>${fmtDay(s.date_of_birth)}</dd><dt>Gender</dt><dd>${esc(s.gender||'—')}</dd>
  <dt>Address</dt><dd>${esc(s.address||'—')}</dd><dt>Police case</dt><dd>${esc(c.police_case_id)}</dd>
  <dt>Inmate number</dt><dd>${esc(c.inmate_id||'Not in custody')}</dd>${c.summary?`<dt>Summary</dt><dd>${esc(c.summary)}</dd>`:''}</dl>
  <div class="sect">Charges</div>${c.charges.map(x=>`<span class="chip"><b>${esc(x.offence)}</b>${x.statute?' · '+esc(x.statute):''}</span>`).join('')}
  <div class="sect">Hearings</div>${c.hearings.length?c.hearings.map(h=>`<div class="casebox" style="margin-bottom:8px"><b>${fmtDate(h.hearing_date)}</b> · ${esc(h.court_name)}<div class="mut">${esc(h.presiding_officer||'')} ${esc(h.hearing_id)}</div></div>`).join(''):'<div class="mut">No hearings scheduled yet.</div>'}
  <div class="sect">Court Decisions &amp; Custody</div>${(c.decisions.length||c.custody_events.length)?`<ul class="timeline">`+
    [...c.decisions.map(d=>({t:d.decided_at,by:d.decided_by,x:describeDecision(d)})),...c.custody_events.map(e=>({t:e.recorded_at,by:e.recorded_by,x:describeCustody(e)}))]
    .sort((a,b)=>a.t<b.t?-1:1).map(({t,by,x})=>`<li><div class="tl-ic">${x[0]}</div><div><b>${x[1]}</b><div>${esc(x[2])}</div><div class="mut">${esc(by)} · ${fmtDate(utc(t))}</div></div></li>`).join('')+`</ul>`:'<div class="mut">No decisions recorded yet.</div>'}
  <div class="sect">Reported to the Police service</div>
  <div class="syncrow">${syncBadge(c.police_sync)}<span class="mut">${esc(c.police_sync_message||'The Police case is updated after every court decision.')}</span>
   ${canAct()?`<button class="btn sm" id="rs">📨 Resend to Police</button>`:''}</div>
  <div class="sect">Linked records in the other services</div><div id="linked" class="journey"><div class="col mut">Loading live records…</div></div>
  <div class="foot">${can('schedule',c)?`<button class="btn" onclick="openSchedule('${esc(id)}')">📅 Schedule Hearing</button>`:''}
  ${can('bail',c)?`<button class="btn" onclick="openBail('${esc(id)}')">🔓 Grant Bail</button>`:''}
  ${can('remand',c)?`<button class="btn" onclick="openRemand('${esc(id)}')">🔒 Remand</button>`:''}
  ${can('verdict',c)?`<button class="btn primary" onclick="openVerdict('${esc(id)}')">🔨 Deliver Verdict</button>`:''}
  <button class="btn" onclick="closeModal()">Close</button></div>`,true);
  if($('#rs'))$('#rs').onclick=()=>submit($('#rs'),()=>api(`/court-cases/${id}/notify-police`,'POST'),r=>r.police_sync==='OK'?'Police case updated.':'Police service still not reachable.');
  api(`/court-cases/${id}/linked`).then(l=>{
    const p=l.police_case,i=l.inmate;
    $('#linked').innerHTML=`<div class="col"><h4>👮 Police case</h4>${p?kv([['Case',esc(p.case_id)],['Status',badge(p.status,POLICE)],['Arrest',esc(p.arrest_id)],['Opened',fmtDay(utc(p.created_at))],['Court news',p.court_status?badge(p.court_status,COURT):'—']]):`<div class="err">${esc(l.police_error||'Not available')}</div>`}</div>
     <div class="col"><h4>⚖️ This court case</h4>${kv([['Case',esc(c.court_case_id)],['Status',badge(c.status,STATUS)],['Hearings',c.hearings.length],['Decisions',c.decisions.length]])}</div>
     <div class="col"><h4>🏛️ Custody record</h4>${i?kv([['Inmate',esc(i.inmate_id)],['Status',badge(i.status,CUSTODY)],['Facility',esc(i.facility)],['Sentence',i.sentence_months?i.sentence_months+' months':'—'],['Admitted',fmtDay(utc(i.admitted_at))]]):`<div class="${c.inmate_id?'err':'mut'}">${esc(l.inmate_error||'The suspect has not been taken into custody.')}</div>`}</div>`;
  }).catch(e=>{$('#linked').innerHTML=`<div class="col err">${esc(e.message)}</div>`});
}

/* ---------- Receive a referred case ---------- */
function chargeRow(){return `<div class="charge-row"><input class="co" placeholder="Offence (e.g. Theft)"><input class="cs" placeholder="Statute (e.g. Theft Act s.4)"><button class="btn sm" type="button" onclick="this.parentElement.remove()">✖</button></div>`}
function register(){
  $('#main').innerHTML=head('Receive a Referred Case','Normally the Police service sends cases here automatically. Use this form to capture a case manually.')+
  `<div class="card form-card">
    <div class="row2"><div><label>Police Case Reference</label><input id="pc" placeholder="e.g. CASE-2026-0007"></div>
    <div><label>Suspect's National ID</label><input id="ni" placeholder="e.g. 8001015800083"></div></div>
    <div class="row2"><div><label>Suspect's Full Name</label><input id="fn" placeholder="e.g. Thandi Dlamini"></div>
    <div><label>Date of Birth</label><input id="dob" type="date"></div></div>
    <div class="row2"><div><label>Gender</label><select id="gd"><option value="">Not stated</option><option>male</option><option>female</option><option>other</option></select></div>
    <div><label>Address</label><input id="ad" placeholder="Where the suspect lives"></div></div>
    <label>Case Summary</label><textarea id="sm" rows="2" placeholder="Short description of the case"></textarea>
    <label>Charges</label><div id="charges">${chargeRow()}</div>
    <button class="btn sm" type="button" onclick="document.getElementById('charges').insertAdjacentHTML('beforeend',chargeRow())">➕ Add Another Charge</button>
    <div class="hint">The case starts with the status “Awaiting Hearing”.</div>
    <div style="margin-top:22px;display:flex;gap:10px"><button class="btn primary" id="sv">💾 Save Case File</button><button class="btn" onclick="go('cases')">Cancel</button></div>
  </div>`;
  $('#sv').onclick=async()=>{
    const charges=[...document.querySelectorAll('.charge-row')].map(r=>({offence:r.querySelector('.co').value.trim(),statute:r.querySelector('.cs').value.trim()||null})).filter(c=>c.offence);
    const body={police_case_id:$('#pc').value.trim(),summary:$('#sm').value.trim()||null,charges,
      suspect:{national_id:$('#ni').value.trim(),full_name:$('#fn').value.trim(),date_of_birth:$('#dob').value,gender:$('#gd').value||null,address:$('#ad').value.trim()||null}};
    if(!body.police_case_id||!body.suspect.national_id||!body.suspect.full_name||!body.suspect.date_of_birth)return toast('Please fill in the case reference, national ID, name and date of birth.','err');
    if(!charges.length)return toast('Add at least one charge.','err');
    try{const r=await api('/court-cases','POST',body);toast('Case '+r.court_case_id+' received.','ok');go('cases')}catch(e){toast(e.message,'err')}
  };
}

/* ---------- Menu pickers ---------- */
const PK={
  schedule:['Schedule a Hearing','Choose a case, then set its hearing date.','📅 Schedule Hearing','openSchedule'],
  bail:['Grant Bail','Choose a case to release the suspect on bail. A suspect in custody will be released by the Correctional Service.','🔓 Grant Bail','openBail'],
  remand:['Remand in Custody','Choose a case to hold the suspect at a correctional facility until the next hearing.','🔒 Remand','openRemand'],
  verdict:['Deliver Verdict & Sentence','Choose a case to record the trial outcome.','🔨 Deliver Verdict','openVerdict']};
function picker(k){
  const [t,s,label,fn]=PK[k];const list=CASES.filter(c=>can(k,c));
  $('#main').innerHTML=head(t,s)+`<div class="card tbl">${list.length?`<table><thead><tr><th>Case</th><th>Suspect</th><th>Status</th><th></th></tr></thead><tbody>`+
   list.map(c=>`<tr><td class="name">${esc(c.court_case_id)}</td><td>${esc(c.suspect.full_name)}<div class="mut">${esc(c.charges.map(x=>x.offence).join(', '))}</div></td><td>${badge(c.status,STATUS)}</td>
   <td style="text-align:right"><button class="btn primary sm" onclick="${fn}('${esc(c.court_case_id)}')">${label}</button></td></tr>`).join('')+`</tbody></table>`:
   emptyBox('🎉','No cases are ready for this step.',k!=='schedule'?'A hearing must be scheduled first.':'')}</div>`;
}

const caseBox=c=>`<div class="casebox"><b>${esc(c.court_case_id)}</b> — ${esc(c.suspect.full_name)} ${badge(c.status,STATUS)}<div class="mut">${esc(c.charges.map(x=>x.offence).join(', '))}</div></div>`;
const FAC='Matsapha Correctional Centre';

function openSchedule(id){
  const c=byId(id);
  openModal(`<h3>📅 Schedule a Hearing</h3>${caseBox(c)}
   <label>Hearing date &amp; time</label><input type="datetime-local" id="hd">
   <div class="row2"><div><label>Court</label><input id="cn" value="Manzini Magistrate Court"></div><div><label>Presiding officer</label><input id="po" placeholder="e.g. Magistrate Simelane"></div></div>
   ${c.status==='RECEIVED'?'<div class="hint">The case will move to “Hearing Scheduled”. The Police service is told automatically.</div>':''}
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Confirm Hearing</button></div>`);
  $('#ok').onclick=()=>{const v=$('#hd').value,cn=$('#cn').value.trim();if(!v||!cn)return toast('Pick a date and enter the court name.','err');
    submit($('#ok'),()=>api(`/court-cases/${id}/hearings`,'POST',{hearing_date:v,court_name:cn,presiding_officer:$('#po').value.trim()||null}),'Hearing scheduled for '+fmtDate(v)+'.')};
}
function openBail(id){
  const c=byId(id);
  openModal(`<h3>🔓 Grant Bail</h3>${caseBox(c)}
   <div class="row2"><div><label>Bail amount (E)</label><input type="number" id="ba" min="0" step="0.01" placeholder="e.g. 2000"></div></div>
   <label>Bail conditions</label><textarea id="bc" rows="3" placeholder="e.g. Report to the police station every Friday"></textarea>
   ${c.status==='ON_REMAND'?'<div class="notice">⚠️ The suspect is in custody. Granting bail will order the Correctional Service to release them.</div>':''}
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Grant Bail</button></div>`);
  $('#ok').onclick=()=>{const a=$('#ba').value,cd=$('#bc').value.trim();if(a===''||!cd)return toast('Enter the bail amount and conditions.','err');
    submit($('#ok'),()=>api(`/court-cases/${id}/bail`,'POST',{amount:parseFloat(a),conditions:cd}),'Bail granted.')};
}
function openRemand(id){
  const c=byId(id);
  openModal(`<h3>🔒 Remand in Custody</h3>${caseBox(c)}
   <label>Reason for remand</label><input id="rr" placeholder="e.g. Risk of absconding">
   <div class="row2"><div><label>Correctional facility</label><input id="rf" value="${FAC}"></div><div><label>Next hearing</label><input type="datetime-local" id="rn"></div></div>
   <div class="notice">⚠️ The Correctional Service will be asked to admit the suspect. If it cannot, nothing is saved and you can try again.</div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Remand Suspect</button></div>`);
  $('#ok').onclick=()=>{const r=$('#rr').value.trim(),f=$('#rf').value.trim(),n=$('#rn').value;if(!r||!f||!n)return toast('Fill in the reason, facility and next hearing.','err');
    submit($('#ok'),()=>api(`/court-cases/${id}/remand`,'POST',{reason:r,facility:f,next_hearing_date:n}),r=>'Suspect remanded in custody as inmate '+r.inmate_id+'.')};
}
function openVerdict(id){
  const c=byId(id),onRemand=c.status==='ON_REMAND';
  openModal(`<h3>🔨 Deliver Verdict &amp; Sentence</h3>${caseBox(c)}
   <label>Verdict</label>
   <div class="seg"><label><input type="radio" name="v" value="GUILTY" checked> ⚖️ Guilty</label><label><input type="radio" name="v" value="NOT_GUILTY"> ✅ Not Guilty</label></div>
   <div id="gw"><label>Sentence</label><select id="st"><option value="IMPRISONMENT">Imprisonment</option><option value="FINE">Fine</option><option value="SUSPENDED">Suspended sentence</option></select>
    <div id="imp"><div class="row2"><div><label>Term (months)</label><input type="number" id="sm" min="1" placeholder="e.g. 12"></div>
    <div><label>Facility${onRemand?' (optional)':''}</label><input id="sf" value="${FAC}"></div></div></div>
    <div id="fine" class="hidden"><label>Fine amount (E)</label><input type="number" id="fa" min="0" step="0.01" placeholder="e.g. 500"></div></div>
   <div class="notice" id="nt"></div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Confirm Verdict</button></div>`);
  const sync=()=>{
    const v=document.querySelector('[name=v]:checked').value,st=$('#st').value;
    $('#gw').classList.toggle('hidden',v!=='GUILTY');$('#imp').classList.toggle('hidden',st!=='IMPRISONMENT');$('#fine').classList.toggle('hidden',st!=='FINE');
    $('#nt').textContent=
      v==='NOT_GUILTY'?(onRemand?'⚠️ The suspect will be acquitted and released from custody by the Correctional Service.':'The suspect will be acquitted and the case closed.'):
      st==='IMPRISONMENT'?(onRemand?'⚠️ The inmate on remand will be updated to convicted with this sentence.':'⚠️ The suspect will be admitted to the Correctional Service as convicted.'):
      (onRemand?'⚠️ The suspect will be released from custody and the case closed.':'The case will be closed.');
    $('#nt').textContent+=' The Police case will be closed automatically.';
  };
  document.querySelectorAll('[name=v]').forEach(r=>r.onchange=sync);$('#st').onchange=sync;sync();
  $('#ok').onclick=()=>{
    const v=document.querySelector('[name=v]:checked').value,st=$('#st').value;let body={verdict:v};
    if(v==='GUILTY'){
      body.sentence_type=st;
      if(st==='IMPRISONMENT'){const m=parseInt($('#sm').value);if(!m||m<1)return toast('Enter the term in months.','err');
        body.sentence_months=m;const f=$('#sf').value.trim();if(!onRemand&&!f)return toast('Enter the facility.','err');if(f)body.facility=f}
      if(st==='FINE'){const a=$('#fa').value;if(a==='')return toast('Enter the fine amount.','err');body.fine_amount=parseFloat(a)}
    }
    submit($('#ok'),()=>api(`/court-cases/${id}/verdict`,'POST',body),v==='NOT_GUILTY'?'Suspect acquitted. Case closed.':'Verdict recorded.');
  };
}

/* ---------- Audit (admin) ---------- */
const AICON={COURT_CASE_RECEIVED:['➕','Case received'],HEARING_SCHEDULED:['📅','Hearing scheduled'],BAIL_GRANTED:['🔓','Bail granted'],REMAND_ORDERED:['🔒','Remand ordered'],VERDICT_RECORDED:['🔨','Verdict recorded'],
  POLICE_NOTIFIED:['📨','Police case updated'],CUSTODY_TRANSFERRED:['🚐','Transfer reported by Correctional'],CUSTODY_RELEASED:['🚪','Release reported by Correctional']};

const VIEWS={dashboard,cases,register,schedule:()=>picker('schedule'),bail:()=>picker('bail'),remand:()=>picker('remand'),verdict:()=>picker('verdict'),audit:()=>auditView(AICON,'court')};
