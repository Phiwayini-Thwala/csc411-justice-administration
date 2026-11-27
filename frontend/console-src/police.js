/* ===================== Police Console (Police, port 8001) ===================== */
let SUSPECTS=[], ARRESTS=[], CASES=[], filter={q:'',s:''};
const STATUS=POLICE;
const canAct=()=>USER&&['police_officer','admin'].includes(USER.role);
const byId=id=>CASES.find(c=>c.case_id===id);
const suspectOf=id=>SUSPECTS.find(s=>s.suspect_id===id);
const arrestOf=id=>ARRESTS.find(a=>a.arrest_id===id);
const caseOfArrest=id=>CASES.find(c=>c.arrest_id===id);

function navItems(){
  const items=[['Overview'],['dashboard','🏠','Dashboard'],['Records'],['cases','📂','All Police Cases'],['suspects','🧑','Suspects'],['arrests','🚨','Arrests']];
  if(canAct())items.push(['Actions'],['book','➕','Process a New Arrest'],['refer','📤','Refer a Case to Court']);
  items.push(['Follow Up'],['track','🧭','Track a Case']);
  if(USER.role==='admin')items.push(['Admin'],['audit','🧾','Activity History']);
  return items;
}
async function loadFor(v){
  if(v==='audit')return;
  [SUSPECTS,ARRESTS,CASES]=await Promise.all([api('/suspects'),api('/arrests'),api('/cases')]);
}

/* ---------- Dashboard ---------- */
function dashboard(){
  const n=s=>CASES.filter(c=>c.status===s).length;
  const custody=CASES.filter(c=>c.inmate_id&&['ON_REMAND','SENTENCED'].includes(c.court_status)).length;
  const stats=[['Suspects on Record',SUSPECTS.length,'🧑','var(--brand)'],['Arrests',ARRESTS.length,'🚨','var(--info)'],['Open Investigations',n('OPEN'),'🔎','var(--info)'],
    ['Referred to Court',n('REFERRED'),'📤','var(--brand)'],['In Custody',custody,'🔒','var(--muted)'],['Cases Closed',n('CLOSED'),'✅','var(--ok)']];
  const recent=CASES.slice(0,5);
  const qa=canAct()?`<h2>What would you like to do?</h2><div class="qa">
    <button onclick="go('book')"><span class="ic">🚨</span><b>Process a New Arrest</b><span class="d">Suspect, arrest, case and charges in one go</span></button>
    <button onclick="go('suspects')"><span class="ic">🧑</span><b>Arrest a Known Suspect</b><span class="d">Record a new arrest for someone on file</span></button>
    <button onclick="go('refer')"><span class="ic">📤</span><b>Refer to Court</b><span class="d">Send a charged case to the Judiciary</span></button>
    <button onclick="go('track')"><span class="ic">🧭</span><b>Track a Case</b><span class="d">See court and custody progress live</span></button></div>`:'';
  $('#main').innerHTML=head('Welcome, '+esc(USER.username),'Here is what is happening across police cases.',
    canAct()?`<button class="btn primary" onclick="go('book')">➕ Process a New Arrest</button>`:'')+flowStrip()+
  `<div class="grid">${stats.map(s=>`<div class="card stat"><div class="l">${s[2]} ${s[0]}</div><div class="n">${s[1]}</div><div class="bar" style="background:${s[3]};opacity:.7"></div></div>`).join('')}</div>${qa}
  <h2>Most Recent Cases</h2><div class="card tbl">${caseTable(recent)}</div>`;
}

/* ---------- Cases ---------- */
function caseActions(c){
  return `<div class="acts">
    <button class="btn sm" onclick="openCaseFile('${esc(c.case_id)}')">📄 View Case File</button>
    ${canAct()&&c.status==='OPEN'?`<button class="btn sm" onclick="openCharge('${esc(c.case_id)}')">➕ Add Charge</button>`:''}
    ${canAct()&&c.status==='OPEN'&&c.charges.length?`<button class="btn sm primary" onclick="openRefer('${esc(c.case_id)}')">📤 Refer to Court</button>`:''}
    ${c.court_case_id?`<button class="btn sm" onclick="openTrack('${esc(c.case_id)}')">🧭 Track</button>`:''}
  </div>`;
}
function caseTable(list){
  if(!list.length)return emptyBox('📂','No cases to show yet.');
  return `<table><thead><tr><th>Case</th><th>Suspect</th><th>Charges</th><th>Police Status</th><th>Court</th><th>Actions</th></tr></thead><tbody>`+
  list.map(c=>`<tr>
    <td><div class="name">${esc(c.case_id)}</div><div class="mut">Arrest ${esc(c.arrest_id)}</div></td>
    <td class="name">${esc(c.suspect_name||c.suspect_id)}<div class="mut">ID ${esc(c.national_id||'—')}</div></td>
    <td style="max-width:200px">${c.charges.length?esc(c.charges.map(x=>x.offence).join(', ')):'<span class="mut">No charges yet</span>'}</td>
    <td>${badge(c.status,STATUS)}</td>
    <td>${c.court_case_id?`<div class="name">${esc(c.court_case_id)}</div>${c.court_status?badge(c.court_status,COURT):''}`:'<span class="mut">Not referred</span>'}${c.inmate_id?`<div class="mut">Inmate ${esc(c.inmate_id)}</div>`:''}</td>
    <td>${caseActions(c)}</td></tr>`).join('')+`</tbody></table>`;
}
function cases(){
  $('#main').innerHTML=head('All Police Cases','Search, filter and act on every case the police have opened.',
    canAct()?`<button class="btn primary" onclick="go('book')">➕ Process a New Arrest</button>`:'')+
  `<div class="toolbar"><input id="q" placeholder="🔍 Search by name, ID, case number or charge…" value="${esc(filter.q)}">
   <select id="fs"><option value="">All statuses</option>${Object.entries(STATUS).map(([k,v])=>`<option value="${k}" ${filter.s===k?'selected':''}>${v}</option>`).join('')}</select></div>
   <div class="card tbl" id="tbl"></div>`;
  const draw=()=>{
    filter.q=$('#q').value;filter.s=$('#fs').value;const q=filter.q.toLowerCase();
    $('#tbl').innerHTML=caseTable(CASES.filter(c=>(!filter.s||c.status===filter.s)&&(!q||[c.case_id,c.court_case_id,c.suspect_name,c.national_id,c.inmate_id,...c.charges.map(x=>x.offence)].join(' ').toLowerCase().includes(q))));
  };
  $('#q').oninput=draw;$('#fs').onchange=draw;draw();
}

/* ---------- Suspects & arrests ---------- */
function suspects(){
  $('#main').innerHTML=head('Suspects','Everyone registered by the police. One record per national ID, shared by all three services.',
    canAct()?`<button class="btn primary" onclick="go('book')">➕ Process a New Arrest</button>`:'')+
  `<div class="toolbar"><input id="q" placeholder="🔍 Search by name or national ID…"></div><div class="card tbl" id="tbl"></div>`;
  const draw=()=>{const q=$('#q').value.toLowerCase();const list=SUSPECTS.filter(s=>!q||[s.suspect_id,s.full_name,s.national_id,s.address].join(' ').toLowerCase().includes(q));
    $('#tbl').innerHTML=list.length?`<table><thead><tr><th>Suspect</th><th>National ID</th><th>Born</th><th>Address</th><th>Cases</th><th>Actions</th></tr></thead><tbody>`+
    list.map(s=>{const cs=CASES.filter(c=>c.suspect_id===s.suspect_id);return `<tr><td><div class="name">${esc(s.full_name)}</div><div class="mut">${esc(s.suspect_id)}</div></td>
      <td>${esc(s.national_id)}</td><td>${fmtDay(s.date_of_birth)}</td><td>${esc(s.address)}</td>
      <td>${cs.length?cs.map(c=>`<div>${esc(c.case_id)} ${badge(c.status,STATUS)}</div>`).join(''):'<span class="mut">None</span>'}</td>
      <td>${canAct()?`<button class="btn sm" onclick="openArrest('${esc(s.suspect_id)}')">🚨 Record Arrest</button>`:''}</td></tr>`}).join('')+`</tbody></table>`:emptyBox('🧑','No suspects match.')};
  $('#q').oninput=draw;draw();
}
function arrests(){
  $('#main').innerHTML=head('Arrests','Every arrest on record. An arrest becomes a case once charges are prepared.')+
  `<div class="card tbl">${ARRESTS.length?`<table><thead><tr><th>Arrest</th><th>Suspect</th><th>When &amp; Where</th><th>Officer</th><th>Case</th><th></th></tr></thead><tbody>`+
   ARRESTS.map(a=>{const s=suspectOf(a.suspect_id),c=caseOfArrest(a.arrest_id);return `<tr><td class="name">${esc(a.arrest_id)}</td>
   <td>${esc(s?s.full_name:a.suspect_id)}</td><td>${fmtDate(a.arrest_date)}<div class="mut">${esc(a.location)}</div></td><td>${esc(a.arresting_officer)}</td>
   <td>${c?`${esc(c.case_id)} ${badge(c.status,STATUS)}`:'<span class="mut">No case yet</span>'}</td>
   <td style="text-align:right">${!c&&canAct()?`<button class="btn sm primary" onclick="openNewCase('${esc(a.arrest_id)}')">📂 Open Case</button>`:''}</td></tr>`}).join('')+`</tbody></table>`:emptyBox('🚨','No arrests recorded yet.')}</div>`;
}

/* ---------- Process a new arrest (suspect -> arrest -> case -> charges [-> refer]) ---------- */
function chargeRow(){return `<div class="charge-row"><input class="co" placeholder="Offence (e.g. Theft)"><input class="cs" placeholder="Statute (e.g. Theft Act s.4)"><button class="btn sm" type="button" onclick="this.parentElement.remove()">✖</button></div>`}
const nowLocal=()=>{const d=new Date();d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,16)};
function book(){
  $('#main').innerHTML=head('Process a New Arrest','Register the suspect, record the arrest, open the case and lay the charges in one step.')+
  `<div class="card form-card">
    <div class="steps"><span class="on">1 · Suspect</span><span class="on">2 · Arrest</span><span class="on">3 · Charges</span><span>4 · Court (optional)</span></div>
    <h3>🧑 Suspect</h3>
    <div class="seg" style="margin-top:10px"><label><input type="radio" name="sk" value="new" checked> New suspect</label><label><input type="radio" name="sk" value="old" ${SUSPECTS.length?'':'disabled'}> Already on record</label></div>
    <div id="sNew"><div class="row2"><div><label>Full name</label><input id="fn" placeholder="e.g. Sibusiso Dlamini"></div><div><label>National ID</label><input id="ni" placeholder="13 digits"></div></div>
      <div class="row2"><div><label>Date of birth</label><input id="dob" type="date"></div><div><label>Gender</label><select id="gd"><option value="">Not stated</option><option>male</option><option>female</option><option>other</option></select></div></div>
      <label>Address</label><input id="ad" placeholder="Where the suspect lives"></div>
    <div id="sOld" class="hidden"><label>Suspect</label><select id="sid">${SUSPECTS.map(s=>`<option value="${esc(s.suspect_id)}">${esc(s.full_name)} · ${esc(s.national_id)}</option>`).join('')}</select></div>
    <h3>🚨 Arrest</h3>
    <div class="row2"><div><label>Date &amp; time of arrest</label><input id="adt" type="datetime-local" value="${nowLocal()}"></div><div><label>Location</label><input id="loc" placeholder="e.g. Manzini Central"></div></div>
    <label>Arresting officer</label><input id="ao" placeholder="Leave blank to use ${esc(USER.username)}">
    <h3>📂 Case &amp; charges</h3>
    <label>Case summary</label><textarea id="sm" rows="2" placeholder="Short description of what happened"></textarea>
    <label>Charges</label><div id="charges">${chargeRow()}</div>
    <button class="btn sm" type="button" onclick="document.getElementById('charges').insertAdjacentHTML('beforeend',chargeRow())">➕ Add Another Charge</button>
    <label style="display:flex;gap:10px;align-items:center;font-weight:500;margin-top:18px"><input type="checkbox" id="rf" style="width:auto"> Refer the case to court straight away (sends it to the Judiciary service)</label>
    <div style="margin-top:22px;display:flex;gap:10px"><button class="btn primary" id="sv">💾 Save</button><button class="btn" onclick="go('cases')">Cancel</button></div>
  </div>`;
  document.querySelectorAll('[name=sk]').forEach(r=>r.onchange=()=>{const old=document.querySelector('[name=sk]:checked').value==='old';$('#sNew').classList.toggle('hidden',old);$('#sOld').classList.toggle('hidden',!old)});
  $('#sv').onclick=async()=>{
    const old=document.querySelector('[name=sk]:checked').value==='old';
    const sus={full_name:$('#fn').value.trim(),national_id:$('#ni').value.trim(),date_of_birth:$('#dob').value,gender:$('#gd').value||null,address:$('#ad').value.trim()};
    const ch=[...document.querySelectorAll('.charge-row')].map(r=>({offence:r.querySelector('.co').value.trim(),statute:r.querySelector('.cs').value.trim()||null})).filter(c=>c.offence);
    if(!old&&(!sus.full_name||!sus.national_id||!sus.date_of_birth||!sus.address))return toast('Fill in the suspect’s name, national ID, date of birth and address.','err');
    if(!$('#adt').value||!$('#loc').value.trim())return toast('Enter when and where the arrest happened.','err');
    if(!ch.length)return toast('Add at least one charge.','err');
    $('#sv').disabled=true;let step='registering the suspect';
    try{
      const suspect_id=old?$('#sid').value:(await api('/suspects','POST',sus)).suspect_id;
      step='recording the arrest';
      const arr=await api('/arrests','POST',{suspect_id,arrest_date:$('#adt').value,location:$('#loc').value.trim(),arresting_officer:$('#ao').value.trim()||null});
      step='opening the case';
      const cs=await api('/cases','POST',{arrest_id:arr.arrest_id,summary:$('#sm').value.trim()||null});
      step='adding the charges';
      for(const c of ch)await api(`/cases/${cs.case_id}/charges`,'POST',c);
      let msg=`Case ${cs.case_id} opened with ${ch.length} charge${ch.length>1?'s':''}.`;
      if($('#rf').checked){step='referring the case to court';const r=await api(`/cases/${cs.case_id}/refer`,'POST');msg+=` Referred to court as ${r.court_case_id}.`}
      toast(msg,'ok');go('cases');
    }catch(e){toast(`Stopped while ${step}: ${e.message}`,'err');$('#sv').disabled=false;if(step!=='registering the suspect')loadFor('cases').catch(()=>{})}
  };
}

/* ---------- Pickers ---------- */
function referPicker(){
  const ready=CASES.filter(c=>c.status==='OPEN'&&c.charges.length),noCharge=CASES.filter(c=>c.status==='OPEN'&&!c.charges.length);
  $('#main').innerHTML=head('Refer a Case to Court','Choose a charged case. The Judiciary service receives it immediately and returns a court case number.')+
  `<div class="card tbl">${ready.length?`<table><thead><tr><th>Case</th><th>Suspect</th><th>Charges</th><th></th></tr></thead><tbody>`+
   ready.map(c=>`<tr><td class="name">${esc(c.case_id)}</td><td>${esc(c.suspect_name)}</td><td>${esc(c.charges.map(x=>x.offence).join(', '))}</td>
   <td style="text-align:right"><button class="btn primary sm" onclick="openRefer('${esc(c.case_id)}')">📤 Refer to Court</button></td></tr>`).join('')+`</tbody></table>`:
   emptyBox('🎉','No cases are ready to be referred.',noCharge.length?`${noCharge.length} open case${noCharge.length>1?'s need':' needs'} a charge first.`:'')}</div>`;
}
function trackPicker(){
  const list=CASES.filter(c=>c.court_case_id);
  $('#main').innerHTML=head('Track a Case','Follow a referred case through the court and into custody. Live records come straight from the Judiciary and Correctional services.')+
  `<div class="card tbl">${list.length?`<table><thead><tr><th>Case</th><th>Suspect</th><th>Court</th><th>Latest news</th><th></th></tr></thead><tbody>`+
   list.map(c=>`<tr><td class="name">${esc(c.case_id)}<div>${badge(c.status,STATUS)}</div></td><td>${esc(c.suspect_name)}</td>
   <td>${esc(c.court_case_id)}<div>${c.court_status?badge(c.court_status,COURT):''}</div></td><td style="max-width:260px">${esc(c.court_outcome||'—')}<div class="mut">${c.court_updated_at?'Updated '+fmtDate(utc(c.court_updated_at)):''}</div></td>
   <td style="text-align:right"><button class="btn primary sm" onclick="openTrack('${esc(c.case_id)}')">🧭 Track</button></td></tr>`).join('')+`</tbody></table>`:
   emptyBox('🧭','No case has been referred to court yet.')}</div>`;
}

/* ---------- Modals ---------- */
const caseBox=c=>`<div class="casebox"><b>${esc(c.case_id)}</b> — ${esc(c.suspect_name)} ${badge(c.status,STATUS)}<div class="mut">${c.charges.length?esc(c.charges.map(x=>x.offence).join(', ')):'No charges yet'}</div></div>`;
function openCaseFile(id){
  const c=byId(id),s=suspectOf(c.suspect_id)||{},a=arrestOf(c.arrest_id)||{};
  openModal(`<h3>📄 Case File ${esc(c.case_id)} ${badge(c.status,STATUS)}</h3>
  <div class="sect">Suspect</div>${kv([['Full name',esc(s.full_name)],['National ID',esc(s.national_id)],['Date of birth',fmtDay(s.date_of_birth)],['Gender',esc(s.gender||'—')],['Address',esc(s.address)],['Suspect number',esc(c.suspect_id)]])}
  <div class="sect">Arrest</div>${kv([['Arrest number',esc(c.arrest_id)],['When',fmtDate(a.arrest_date)],['Where',esc(a.location)],['Officer',esc(a.arresting_officer)]])}
  <div class="sect">Case</div>${kv([['Opened',fmtDate(utc(c.created_at))+' by '+esc(c.created_by)],c.summary&&['Summary',esc(c.summary)],['Court case',esc(c.court_case_id||'Not referred yet')],
    c.court_status&&['Court status',badge(c.court_status,COURT)],c.court_outcome&&['Latest court news',esc(c.court_outcome)],c.inmate_id&&['Inmate number',esc(c.inmate_id)]])}
  <div class="sect">Charges</div>${c.charges.length?c.charges.map(x=>`<span class="chip"><b>${esc(x.offence)}</b>${x.statute?' · '+esc(x.statute):''} <span class="mut">${esc(x.charge_id)}</span></span>`).join(''):'<div class="mut">No charges laid yet.</div>'}
  <div class="foot">${canAct()&&c.status==='OPEN'?`<button class="btn" onclick="openCharge('${esc(id)}')">➕ Add Charge</button>`:''}
  ${canAct()&&c.status==='OPEN'&&c.charges.length?`<button class="btn primary" onclick="openRefer('${esc(id)}')">📤 Refer to Court</button>`:''}
  ${c.court_case_id?`<button class="btn primary" onclick="openTrack('${esc(id)}')">🧭 Track in Court &amp; Custody</button>`:''}
  <button class="btn" onclick="closeModal()">Close</button></div>`,true);
}
function openArrest(sid){
  const s=suspectOf(sid);
  openModal(`<h3>🚨 Record an Arrest</h3><div class="casebox"><b>${esc(s.full_name)}</b> · ${esc(s.national_id)}<div class="mut">${esc(s.suspect_id)}</div></div>
   <div class="row2"><div><label>Date &amp; time</label><input id="adt" type="datetime-local" value="${nowLocal()}"></div><div><label>Location</label><input id="loc" placeholder="e.g. Manzini Central"></div></div>
   <label>Arresting officer</label><input id="ao" placeholder="Leave blank to use ${esc(USER.username)}">
   <label style="display:flex;gap:10px;align-items:center;font-weight:500"><input type="checkbox" id="oc" checked style="width:auto"> Open a case for this arrest</label>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Record Arrest</button></div>`);
  $('#ok').onclick=()=>{if(!$('#adt').value||!$('#loc').value.trim())return toast('Enter when and where.','err');
    const open=$('#oc').checked;
    submit($('#ok'),async()=>{const a=await api('/arrests','POST',{suspect_id:sid,arrest_date:$('#adt').value,location:$('#loc').value.trim(),arresting_officer:$('#ao').value.trim()||null});
      if(open){const c=await api('/cases','POST',{arrest_id:a.arrest_id});return {a,c}}return {a}},
      r=>`Arrest ${r.a.arrest_id} recorded.`+(r.c?` Case ${r.c.case_id} opened; add the charges next.`:''))};
}
function openNewCase(aid){
  const a=arrestOf(aid),s=suspectOf(a.suspect_id);
  openModal(`<h3>📂 Open a Case</h3><div class="casebox"><b>${esc(a.arrest_id)}</b> — ${esc(s?s.full_name:a.suspect_id)}<div class="mut">${fmtDate(a.arrest_date)} · ${esc(a.location)}</div></div>
   <label>Case summary</label><textarea id="sm" rows="3" placeholder="Short description of what happened"></textarea>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Open Case</button></div>`);
  $('#ok').onclick=()=>submit($('#ok'),()=>api('/cases','POST',{arrest_id:aid,summary:$('#sm').value.trim()||null}),r=>`Case ${r.case_id} opened. Add the charges next.`);
}
function openCharge(id){
  const c=byId(id);
  openModal(`<h3>➕ Add a Charge</h3>${caseBox(c)}
   <div class="row2"><div><label>Offence</label><input id="of" placeholder="e.g. Theft"></div><div><label>Statute</label><input id="stt" placeholder="e.g. Theft Act section 4"></div></div>
   <div class="hint">Charges can only be added while the case is open (before it goes to court).</div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Add Charge</button></div>`);
  $('#ok').onclick=()=>{const o=$('#of').value.trim();if(o.length<2)return toast('Enter the offence.','err');
    submit($('#ok'),()=>api(`/cases/${id}/charges`,'POST',{offence:o,statute:$('#stt').value.trim()||null}),r=>`Charge ${r.charge_id} added.`)};
}
function openRefer(id){
  const c=byId(id);
  openModal(`<h3>📤 Refer to Court</h3>${caseBox(c)}
   <div class="notice">⚠️ The full case file (suspect, arrest and ${c.charges.length} charge${c.charges.length>1?'s':''}) is sent to the Judiciary service. If the court service cannot be reached nothing changes here and you can try again. After referral no more charges can be added.</div>
   <div class="foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="ok">Send to Court</button></div>`);
  $('#ok').onclick=()=>submit($('#ok'),()=>api(`/cases/${id}/refer`,'POST'),r=>`Referred. Court case number ${r.court_case_id}.`);
}

/* ---------- Track: one case across all three databases ---------- */
function journeyTimeline(t,arrest){
  const ev=[],c=t.case,court=t.court_case,inm=t.inmate;
  if(arrest)ev.push([new Date(arrest.arrest_date),'🚨','Arrested',`${arrest.location} · ${arrest.arresting_officer}`,'Police']);
  ev.push([new Date(utc(c.created_at)),'📂','Police case opened',c.case_id,'Police']);
  if(court){
    ev.push([new Date(utc(court.created_at)),'⚖️','Received by the court',court.court_case_id,'Judiciary']);
    court.hearings.forEach(h=>ev.push([new Date(h.hearing_date),'📅','Hearing',`${h.court_name}${h.presiding_officer?' · '+h.presiding_officer:''}`,'Judiciary']));
    court.decisions.forEach(d=>{const x=d.kind==='BAIL'?['🔓','Bail granted',money(d.amount)]:d.kind==='REMAND'?['🔒','Remanded in custody',d.facility]:
      ['🔨',d.verdict==='GUILTY'?'Found guilty':'Found not guilty',d.verdict==='GUILTY'?({IMPRISONMENT:`${d.sentence_months} months imprisonment`,FINE:'Fine of '+money(d.fine_amount),SUSPENDED:'Suspended sentence'}[d.sentence_type]):'Acquitted'];
      ev.push([new Date(utc(d.decided_at)),x[0],x[1],x[2]||'','Judiciary'])});
  }
  if(inm){
    ev.push([new Date(utc(inm.admitted_at)),'🏛️','Admitted to custody',`${inm.inmate_id} · ${inm.admission_type==='REMAND'?'on remand':'convicted'}`,'Correctional']);
    (inm.transfers||[]).forEach(x=>ev.push([new Date(utc(x.transferred_at)),'🚐','Transferred',`${x.from_facility} → ${x.new_facility}`,'Correctional']));
    (inm.releases||[]).forEach(x=>ev.push([new Date(utc(x.released_at)),'🚪','Released',RELEASE[x.reason]||x.reason,'Correctional']));
  }
  return `<ul class="timeline">${ev.sort((a,b)=>a[0]-b[0]).map(e=>`<li><div class="tl-ic">${e[1]}</div><div><b>${esc(e[2])}</b> <span class="mut">· ${e[4]}</span><div>${esc(e[3])}</div><div class="mut">${isNaN(e[0])?'':fmtDate(e[0])}</div></div></li>`).join('')}</ul>`;
}
async function openTrack(id){
  openModal(`<h3>🧭 Tracking ${esc(id)}</h3><div class="mut">Asking the Judiciary and Correctional services…</div>`,true);
  let t;try{t=await api(`/cases/${id}/tracking`)}catch(e){$('#modal').innerHTML=`<h3>🧭 Tracking ${esc(id)}</h3>${emptyBox('🚫',esc(e.message))}<div class="foot"><button class="btn" onclick="closeModal()">Close</button></div>`;return}
  const c=t.case,court=t.court_case,i=t.inmate;
  const fresh=CASES.findIndex(x=>x.case_id===c.case_id);if(fresh>=0)CASES[fresh]=c;      // tracking also refreshed our copy
  let sentence='';
  if(i&&i.sentence_months&&i.status!=='RELEASED'){const start=new Date(utc(i.admitted_at)),end=new Date(start);end.setMonth(end.getMonth()+i.sentence_months);
    const pct=Math.max(0,Math.min(100,(Date.now()-start)/(end-start)*100));sentence=`<div class="mut" style="margin-top:8px">Expected release ${fmtDay(end)}</div><div class="progress"><i style="width:${pct.toFixed(0)}%"></i></div>`}
  $('#modal').innerHTML=`<h3>🧭 Tracking ${esc(c.case_id)} ${badge(c.status,STATUS)}</h3>
   <div class="casebox"><b>${esc(c.suspect_name)}</b> · ID ${esc(c.national_id)}<div class="mut">${esc(c.charges.map(x=>x.offence).join(', '))}</div></div>
   <div class="sect">Where the case is now</div>
   <div class="journey">
    <div class="col"><h4>👮 Police</h4>${kv([['Case',esc(c.case_id)],['Status',badge(c.status,STATUS)],['Arrest',esc(c.arrest_id)]])}</div>
    <div class="col"><h4>⚖️ Court</h4>${court?kv([['Case',esc(court.court_case_id)],['Status',badge(court.status,COURT)],['Hearings',court.hearings.length],
       court.hearings.length&&['Latest',fmtDate(court.hearings[court.hearings.length-1].hearing_date)]]):`<div class="err">${esc(t.court_error||'Not referred yet')}</div>`}</div>
    <div class="col"><h4>🏛️ Custody</h4>${i?kv([['Inmate',esc(i.inmate_id)],['Status',badge(i.status,CUSTODY)],['Facility',esc(i.facility)],['Sentence',i.sentence_months?i.sentence_months+' months':'—']])+sentence:
       `<div class="${t.inmate_error?'err':'mut'}">${esc(t.inmate_error||'Not in custody')}</div>`}</div>
   </div>
   ${c.court_outcome?`<div class="notice" style="background:var(--brand-soft);color:var(--brand)">📰 Latest court news: ${esc(c.court_outcome)}</div>`:''}
   <div class="sect">Full journey</div>${journeyTimeline(t,arrestOf(c.arrest_id))}
   <div class="foot"><button class="btn" id="rt">🔄 Refresh</button><button class="btn" onclick="closeModal()">Close</button></div>`;
  $('#rt').onclick=()=>openTrack(id);
}

const AICON={SUSPECT_CREATED:['🧑','Suspect registered'],ARREST_RECORDED:['🚨','Arrest recorded'],CASE_CREATED:['📂','Case opened'],CHARGE_ADDED:['➕','Charge added'],
  CASE_REFERRED:['📤','Case referred to court'],COURT_UPDATE_RECEIVED:['📰','Court news received'],CASE_CLOSED:['✅','Case closed after verdict']};

const VIEWS={dashboard,cases,suspects,arrests,book,refer:referPicker,track:trackPicker,audit:()=>auditView(AICON,'police')};
