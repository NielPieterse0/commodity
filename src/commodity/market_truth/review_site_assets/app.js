"use strict";
const state={meta:null,token:null,year:2022,id:null,metric:"close",scale:10,series:null,mode:"fact",rank:1};
const $=id=>document.getElementById(id);
const fmt=n=>n===null||n===undefined?"--":Number(n).toLocaleString("en-US");
const showError=msg=>{const e=$("error");e.hidden=false;e.textContent=msg;};
const hideError=()=>{$("error").hidden=true;};
const num=n=>n===null||n===undefined?"--":Number(n).toLocaleString("en-US",{maximumFractionDigits:8});
async function api(path,options){
  const response=await fetch(path,Object.assign({cache:"no-store"},options||{}));
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||"Request failed");
  return data;
}
function tabs(){
  document.querySelectorAll(".nav").forEach(button=>button.addEventListener("click",()=>activate(button.dataset.tab)));
  document.querySelectorAll(".back").forEach(button=>button.addEventListener("click",()=>activate("import")));
}
function activate(tab){
  document.querySelectorAll(".nav").forEach(n=>n.classList.toggle("active",n.dataset.tab===tab));
  document.querySelectorAll(".page").forEach(p=>p.classList.toggle("visible",p.id==="page-"+tab));
  $("breadcrumb").textContent=({import:"DATA IMPORT",models:"MODELS",results:"RESULTS"})[tab];
}
function svgNode(name,attrs,text){
  const e=document.createElementNS("http://www.w3.org/2000/svg",name);
  for(const [k,v] of Object.entries(attrs||{}))e.setAttribute(k,String(v));
  if(text!==undefined)e.textContent=String(text);
  return e;
}
function add(parent,name,attrs,text){const e=svgNode(name,attrs,text);parent.appendChild(e);return e;}
const theme={grid:"#2a3649",text:"#8092ad",source:"#4b9cff",final:"#edaa53",delta:"#ff6987"};
function renderChart(){
  const svg=$("chart");svg.replaceChildren();
  const data=state.series;if(!data||!data.points.length){add(svg,"text",{x:480,y:200,"text-anchor":"middle",fill:"#9ab0ca","font-size":16},"No recorded observations for this selection");return;}
  const points=data.points,deltaFactor=state.scale;
  const vals=points.flatMap(p=>[p.source,p.final]).filter(v=>v!==null&&Number.isFinite(v));
  if(!vals.length){add(svg,"text",{x:480,y:200,"text-anchor":"middle",fill:"#9ab0ca"},"No comparable numeric observations");return;}
  const xmin=Date.parse(points[0].date+"T00:00:00Z"),xmax=Date.parse(points[points.length-1].date+"T00:00:00Z");
  const L=73,R=872,T=28,B=339,W=R-L,H=B-T;
  const x=p=>L+(Date.parse(p.date+"T00:00:00Z")-xmin)/(xmax-xmin||1)*W;
  const vmin=Math.min(...vals),vmax=Math.max(...vals),pad=Math.max((vmax-vmin)*.1,1e-3);
  const lo=vmin-pad,hi=vmax+pad,yl=v=>B-(v-lo)/(hi-lo)*H;
  const magnified=points.map(p=>p.delta!==null?p.delta*deltaFactor:null).filter(v=>v!==null);
  const hasNonzeroDelta=magnified.some(v=>v!==0);
  const deltaMax=Math.max(1e-6,Math.max(0,...magnified.map(Math.abs))*1.15);
  const yd=v=>B-(v+deltaMax)/(2*deltaMax)*H;
  const root=add(svg,"g",{});
  for(let i=0;i<=5;i++){
    const y=T+H*i/5;
    add(root,"line",{x1:L,y1:y,x2:R,y2:y,stroke:theme.grid,"stroke-width":1});
    const lv=hi-(hi-lo)*i/5;const dv=deltaMax*(1-2*i/5);
    add(root,"text",{x:L-10,y:y+4,"text-anchor":"end",fill:theme.text,"font-size":12},Number(lv.toFixed(3)).toLocaleString("en-US"));
    if(hasNonzeroDelta)add(root,"text",{x:R+10,y:y+4,fill:theme.red||theme.delta,"font-size":12},dv===0?"0":dv.toPrecision(3));
  }
  const markers=Math.min(7,points.length);
  for(let i=0;i<markers;i++){const p=points[Math.round(i*(points.length-1)/(markers-1||1))],xx=x(p);
    add(root,"line",{x1:xx,y1:B,x2:xx,y2:B+6,stroke:"#647792"});
    add(root,"text",{x:xx,y:B+25,"text-anchor":"middle",fill:theme.text,"font-size":12},p.date.slice(5));}
  add(root,"line",{x1:L,y1:B,x2:R,y2:B,stroke:"#66778e"});
  const makePath=(name,yfn)=>{let path="",open=false;
    for(const p of points){const v=p[name];if(v===null||!Number.isFinite(v)){open=false;continue;}
      path+=(open?"L":"M")+x(p).toFixed(2)+","+yfn(v).toFixed(2)+" ";open=true;}
    return path;};
  add(root,"path",{d:makePath("source",yl),stroke:theme.source,fill:"none","stroke-width":2.7,"stroke-linecap":"round","stroke-linejoin":"round"});
  add(root,"path",{d:makePath("final",yl),stroke:theme.final,fill:"none","stroke-width":2.0,"stroke-dasharray":"5 4","stroke-linejoin":"round"});
  const zero=yd(0);
  if(!hasNonzeroDelta&&magnified.length>0)add(root,"text",{x:R+10,y:zero+4,fill:theme.delta,"font-size":12},"0");
  add(root,"line",{x1:L,y1:zero,x2:R,y2:zero,stroke:theme.delta,"stroke-width":.9,"stroke-opacity":.48,"stroke-dasharray":"3 5"});
  add(root,"path",{d:makePath("delta",v=>yd(v*deltaFactor)),stroke:theme.delta,fill:"none","stroke-width":2.0,"stroke-linejoin":"round"});
  for(const p of points.filter(p=>p.roll_transition)){const xx=x(p);add(root,"line",{x1:xx,y1:T,x2:xx,y2:B,stroke:"#f0c078","stroke-width":1.5,"stroke-dasharray":"5 5"});add(root,"text",{x:xx+5,y:T+14,fill:"#f0c078","font-size":10},"ROLL");}
  for(const p of points.filter(p=>p.delta!==null&&p.delta!==0).slice(0,1000))add(root,"circle",{cx:x(p),cy:yd(p.delta*deltaFactor),r:4,fill:theme.delta});
  for(const p of points.filter(p=>!p.final_present||!p.source_present||p.status==="null_mismatch"))add(root,"circle",{cx:x(p),cy:p.source!==null?yl(p.source):p.final!==null?yl(p.final):zero,r:6,fill:"#ffce7e",stroke:"#111827","stroke-width":2});
  add(root,"text",{x:L,y:14,fill:theme.text,"font-size":11},state.metric==="volume"?"CONTRACTS":"USD / MMBTU");
  add(root,"text",{x:R+11,y:14,fill:theme.delta,"font-size":11},"DELTA x"+deltaFactor);
  add(root,"text",{x:(L+R)/2,y:394,"text-anchor":"middle",fill:theme.text,"font-size":12},"Trading date / "+state.year);
  const focus=add(root,"line",{x1:L,y1:T,x2:L,y2:B,stroke:"#99badd","stroke-dasharray":"4 4","stroke-opacity":0});
  const hit=add(root,"rect",{x:L,y:T,width:W,height:H,fill:"transparent"});
  const tip=$("tooltip");
  const showPoint=event=>{
    const bounds=svg.getBoundingClientRect();const mx=(event.clientX-bounds.left)/bounds.width*960;
    let near=points[0],distance=Infinity;for(const p of points){const d=Math.abs(mx-x(p));if(d<distance){distance=d;near=p;}}
    const xx=x(near);focus.setAttribute("x1",xx);focus.setAttribute("x2",xx);focus.setAttribute("stroke-opacity",".75");
    tip.hidden=false;tip.replaceChildren();
    const title=document.createElement("b");title.textContent=near.date;tip.appendChild(title);
    const rows=[["Original",near.source],["V3/Final",near.final],["Delta",near.delta],["Delta x"+deltaFactor,near.delta===null?null:near.delta*deltaFactor],["Classification",near.status]];
    if(state.mode==="v3")rows.push(["V3 instrument",near.instrument_id||"not listed"],["Symbol",near.contract_symbol||"not listed"],["Rank boundary",near.rank_boundary_status],["Roll",near.roll_transition?"yes":"no"]);
    for(const [label,value] of rows){const d=document.createElement("div");d.textContent=label+": "+(typeof value==="string"?value.replace("_"," "):num(value));tip.appendChild(d);}
    const parent=$("chart").getBoundingClientRect();tip.style.left=Math.min(Math.max(15,(xx/960)*parent.width+9),Math.max(10,parent.width-180))+"px";
    tip.style.top=Math.max(4,(event.clientY-parent.top)-105)+"px";
  };
  hit.addEventListener("pointermove",showPoint);
  hit.addEventListener("pointerdown",showPoint);
  hit.addEventListener("pointerleave",event=>{if(event.pointerType!=="touch"){focus.setAttribute("stroke-opacity",0);tip.hidden=true;}});
}
function renderSeries(){
  const s=state.series.summary;
  $("k-match").textContent=fmt(s.matched);$("k-diff").textContent=fmt(s.different);
  $("k-unmatched").textContent=fmt(s.missing_final+s.extra_final)+" unmatched keys";
  $("maxdelta").textContent=num(s.max_abs_delta);$("meandelta").textContent=num(s.mean_abs_delta);
  $("unmatched").textContent=fmt(s.missing_final+s.extra_final);
  const gaps=s.different+s.missing_final+s.extra_final;
  const excluded=state.mode==="v3"?((s.excluded_unverified_expiry_rank||0)+(s.excluded_unverified_expiry_window||0)):0;
  $("pair-status").textContent=gaps?"Differences found":excluded?"CME rank exclusion active":state.mode==="v3"?"Pre-approval diagnostic":s.both_null?"Match incl. nulls":"Exact match";
  $("pair-status").style.color=gaps||state.mode==="v3"?"#ffb886":"#67d4ac";
  $("coverage").textContent=state.mode==="v3"?("V3 M"+state.rank+" / "+fmt(s.matched)+" matched / "+fmt(s.roll_transitions)+" rolls / "+fmt(s.unverified_expiry_boundaries)+" unverified boundaries / "+fmt(excluded)+" CME rank/window exclusions"):fmt(s.matched)+" matched observations";
  $("comparison-detail").textContent=state.mode==="v3"?"Diagnostic: actual model-safe V3 rank outputs from verified Parquet versus original source CSV. Unverified CME ranks, their dependent suffix, and fenced terminal sessions are explicitly EXCLUDED, not silently missing or matched. "+(state.series.window==="year"?"All eligible sessions in selected year through end date":"Last 20 available sessions")+"; source PIT and expiry are NOT independently qualified.": "Actual original source rows vs normalized Parquet facts. No inferred timestamps or smoothing.";
  $("window").textContent=state.series.points.length?
    state.series.points[0].date+" to "+state.series.points[state.series.points.length-1].date:state.year;
  $("delta-legend").textContent=state.scale;$("delta-mult").textContent=state.scale;
  renderChart();
}
async function reloadContracts(){
  hideError();
  const items=await api("/api/contracts?year="+state.year);
  const select=$("contract");const previous=state.id;select.replaceChildren();
  for(const item of items){const option=document.createElement("option");option.value=item.id;
    option.textContent=item.symbol+" / "+item.id+"  ("+fmt(item.source_rows)+" source / "+fmt(item.final_rows)+" final)";select.appendChild(option);}
  if(items.some(x=>x.id===previous))select.value=previous;
  state.id=select.value||null;
  await reloadSeries();
}
async function reloadSeries(){
  if(state.mode==="fact"&&!state.id){state.series={points:[],summary:{matched:0,different:0,missing_final:0,extra_final:0,both_null:0,max_abs_delta:null,mean_abs_delta:null}};renderSeries();return;}
  if(state.mode==="v3"){
    state.series=await api("/api/v3-series?year="+state.year+"&end_day="+encodeURIComponent($("v3-date").value)+"&clock="+encodeURIComponent($("v3-clock").value)+"&rank="+state.rank+"&metric="+state.metric+"&window="+encodeURIComponent($("v3-window").value));
  }else{
    state.series=await api("/api/series?year="+state.year+"&id="+encodeURIComponent(state.id)+"&metric="+state.metric);
  }
  renderSeries();hideError();
}
async function reloadDecisions(){
  const [records,signed]=await Promise.all([api("/api/decisions"),api("/api/signed-decisions")]);
  const box=$("decisions");box.replaceChildren();
  for(const item of signed){const d=document.createElement("div");d.className="receipt";
    const header=document.createElement("strong");header.textContent="SIGNED APPROVAL / "+item.review.reviewer_login;
    const detail=document.createElement("small");detail.textContent=item.review.created_at_utc+" | Ed25519 / "+item.catalog.signer_key_id+" | admission pending";
    d.append(header,detail);box.appendChild(d);}
  if(!records.length&&!signed.length){const p=document.createElement("p");p.textContent="No local decisions recorded.";box.appendChild(p);return;}
  for(const item of records){const d=document.createElement("div");d.className="receipt";
    const header=document.createElement("strong");header.textContent=item.decision.toUpperCase().replace("_"," ")+" / "+item.reviewer_label_unverified;
    const detail=document.createElement("small");detail.textContent=item.created_at_utc+" | Unsigned owner intent";
    d.append(header,detail);if(item.notes){const p=document.createElement("p");p.textContent=item.notes;d.appendChild(p);}box.appendChild(d);}
}
async function saveDecision(decision){
  const message=$("message");message.textContent="";
  if(!$("ack").checked){message.textContent="Confirm the reviewed dataset and admission boundary before recording a decision.";return;}
  if(!$("reviewer").value.trim()){message.textContent="Enter a reviewer label.";return;}
  const payload={decision,reviewer:$("reviewer").value,notes:$("notes").value,
    dataset_content_sha256:state.meta.dataset_content_sha256,acknowledge_not_admitted:true};
  const headers={"Content-Type":"application/json","X-Review-Token":state.token};
  if(decision==="approve"){
    const code=$("owner-code").value.trim();
    if(!code){message.textContent="Enter the private owner approval code from your laptop.";return;}
    headers["X-Owner-Approval-Code"]=code;
  }
  try{const result=await api(decision==="approve"?"/api/owner-approve":"/api/decision",{method:"POST",headers,body:JSON.stringify(payload)});
    message.textContent=result.status;
    await reloadDecisions();
  }catch(err){message.textContent="Could not save decision: "+err.message;}
  finally{$("owner-code").value="";}
}
function renderFamilies(){
  const node=$("families");node.replaceChildren();
  for(const name of ["bars","definitions","statistics"]){
    const data=state.meta.families[name],card=document.createElement("div");
    card.className="family";
    const title=document.createElement("h3");title.textContent=({bars:"OHLCV bars",definitions:"Contract definitions",statistics:"Official statistics"})[name];
    card.appendChild(title);
    for(const [label,value] of [["Original source",data.source_rows],["Normalized final",data.final_rows],["Excluded / exact retransmissions",data.excluded_or_retransmissions]]){
      const line=document.createElement("div");line.className="family-line";
      const text=document.createElement("span");text.textContent=label;
      const count=document.createElement("strong");count.textContent=fmt(value);
      line.append(text,count);card.appendChild(line);
    }
    const evidence=document.createElement("small");
    evidence.textContent="Source SHA-256: "+data.source_sha256+" | Parquet SHA-256: "+data.final_sha256;
    card.appendChild(evidence);node.appendChild(card);
  }
}
function setComparison(mode){
  state.mode=mode;
  $("contract-label").style.display=mode==="v3"?"none":"";
  $("rank-label").style.display=mode==="v3"?"":"none";
  $("v3-date-label").style.display=mode==="v3"?"":"none";
  $("v3-clock-label").style.display=mode==="v3"?"":"none";
  $("v3-window-label").style.display=mode==="v3"?"":"none";
  $("compare-mode").value=mode;
}
let barsAudit=null;
function renderBarsAudit(){
  const container=$("bars-audit-table");container.replaceChildren();
  if(!barsAudit)return;
  const year=$("bars-audit-year").value;
  const rows=year==="all"?barsAudit.metrics:barsAudit.years.filter(r=>String(r.year)===year);
  for(const row of rows){
    const card=document.createElement("div");card.className="family";
    const title=document.createElement("h3");title.textContent=row.metric.toUpperCase()+(year==="all"?" / ALL YEARS":" / "+year);
    card.appendChild(title);
    const mean=year==="all"?row.mean_abs_delta:(row.numeric_pairs?row.sum_abs_delta/row.numeric_pairs:null);
    const details=[
      ["Original",row.source_rows],["Final",row.final_rows],
      ["Matched keys",row.paired_rows],["Source only",row.source_only],
      ["Final only",row.final_only],["Different",row.differing],
      ["Null mismatch",row.null_mismatch],["Both null",row.both_null],
      ["Max |delta|",num(row.max_abs_delta)],["Mean |delta|",num(mean)]
    ];
    for(const [label,value] of details){
      const line=document.createElement("div");line.className="family-line";
      const caption=document.createElement("span");caption.textContent=label;
      const count=document.createElement("strong");count.textContent=typeof value==="number"?fmt(value):value;
      line.append(caption,count);card.appendChild(line);
    }
    container.appendChild(card);
  }
}
async function runBarsAudit(){
  const button=$("audit-bars"),status=$("bars-result");
  button.disabled=true;status.textContent="Reading all original CSV and final Parquet OHLCV values...";
  barsAudit=null;$("bars-audit-table").replaceChildren();
  try{
    const result=await api("/api/bars-audit");
    barsAudit=result;
    status.textContent=(result.exact?"EXACT NORMALIZED FACT PARITY":"OHLCV DIFFERENCES FOUND")+
      " | 2010–2022 complete dataset | source SHA-256: "+result.source_sha256+
      " | final SHA-256: "+result.final_sha256+
      " | signed research admission: NO | source PIT and V3 selection not qualified by this audit.";
    status.style.color=result.exact?"#67d4ac":"#ffb886";
    renderBarsAudit();
  }catch(err){
    status.textContent="OHLCV AUDIT NOT VERIFIED: "+err.message;
    status.style.color="#ffb886";
  }finally{button.disabled=false;}
}
let v3Evidence=null;
const V3_COUNTS=[
  ["exact","Exact numeric matches"],["different","Numeric differences"],
  ["missing_source","Source selection absent"],["null_value","Null / no numeric pair"],
  ["excluded_rank","CME rank exclusions"],["excluded_window","CME window exclusions"],
  ["unavailable_rank","Rank unavailable"],
];
function renderV3Evidence(){
  const node=$("v3-full-metrics");node.replaceChildren();
  if(!v3Evidence)return;
  const year=$("v3-audit-year").value,rank=$("v3-audit-rank").value,
    metric=$("v3-audit-metric").value;
  const rows=v3Evidence.groups.filter(r=>(year==="all"||String(r.year)===year)
    &&(rank==="all"||String(r.rank)===rank)&&(metric==="all"||r.metric===metric));
  const totals=Object.fromEntries(V3_COUNTS.map(([key])=>[key,0]));
  let compared=0;
  for(const row of rows){
    for(const key of Object.keys(totals))totals[key]+=row[key];
    compared+=row.numeric_pairs;
  }
  const classified=Object.entries(totals).reduce((s,[k,n])=>
    s+(k==="exact"||k==="different"?0:n),0)+compared;
  const scoped=(year==="all"?"2010–2022":year)+" / "+(rank==="all"?"M1–M12":"M"+rank)
    +" / "+(metric==="all"?"OHLCV":metric.toUpperCase());
  const cards=[["Classified slots",classified],...V3_COUNTS.map(([key,label])=>[label,totals[key]])];
  for(const [label,value] of cards){
    const card=document.createElement("div");card.className="family";
    const caption=document.createElement("h3");caption.textContent=label;
    const count=document.createElement("strong");count.textContent=fmt(value);
    card.append(caption,count);node.appendChild(card);
  }
  $("v3-full-summary").textContent=scoped+" | "+fmt(rows.length)+" year/rank/field groups"
    +" | "+fmt(classified)+" fully classified slots; "+fmt(totals.different)
    +" numeric differences; "+fmt(totals.missing_source)
    +" source-selection gaps (still unqualified). Receipt SHA-256: "
    +v3Evidence.receipt_sha256+" | SIGNED ADMISSION: NO.";
  $("v3-full-summary").style.color=
    totals.different||totals.missing_source?"#ffb886":"#67d4ac";
  $("v3-audit-chart").disabled=year==="all"||rank==="all";
}
async function loadV3Evidence(){
  const button=$("load-v3-full");
  button.disabled=true;$("v3-full-summary").textContent="Checking pinned full-history receipt and accounting...";
  v3Evidence=null;$("v3-full-metrics").replaceChildren();
  try{
    const result=await api("/api/v3-full-history-audit");
    if(result.research_admitted!==false||result.owner_signed!==false)
      throw new Error("Invalid diagnostic admission boundary");
    v3Evidence=result;renderV3Evidence();
  }catch(err){
    $("v3-full-summary").textContent="Historical V3 audit NOT VERIFIED: "+err.message;
    $("v3-full-summary").style.color="#ffb886";
  }finally{button.disabled=false;}
}
async function openV3AuditChart(){
  if(!v3Evidence)return;
  const year=$("v3-audit-year").value,rank=$("v3-audit-rank").value;
  if(year==="all"||rank==="all")return;
  state.year=Number(year);state.rank=Number(rank);
  $("year").value=year;$("rank").value=rank;
  $("metric").value=$("v3-audit-metric").value==="all"?"close":$("v3-audit-metric").value;
  state.metric=$("metric").value;
  $("v3-date").value=year+"-12-31";$("v3-clock").value="23:59";
  $("v3-window").value="year";
  setComparison("v3");
  try{
    await reloadContracts();
    $("chart").scrollIntoView({behavior:"smooth",block:"center"});
  }catch(err){showError(err.message);}
}
async function loadStatisticsEvidence(){
  const button=$("load-statistics"),status=$("statistics-result"),node=$("statistics-metrics");
  button.disabled=true;status.textContent="Checking existing pinned statistics receipt...";node.replaceChildren();
  try{
    const result=await api("/api/statistics-audit");
    if(result.research_admitted!==false||result.source_pit_qualified!==false)
      throw new Error("Invalid statistics admission boundary");
    for(const [name,label] of [["settle","Official settlement"],["open_interest","Open interest"],["cleared_volume","Cleared volume"]]){
      const card=document.createElement("div");card.className="family";
      const heading=document.createElement("h3");heading.textContent=label;card.appendChild(heading);
      for(const [title,count] of [["Original dated rows",result.source_rows_by_type[name]],["Final eligible rows",result.final_rows_by_type[name]]]){
        const line=document.createElement("div");line.className="family-line";
        const key=document.createElement("span");key.textContent=title;
        const value=document.createElement("strong");value.textContent=fmt(count);
        line.append(key,value);card.appendChild(line);
      }
      node.appendChild(card);
    }
    status.textContent="PINNED SOURCE VALUE RECONCILIATION | Policy-excluded originals: "
      +fmt(result.excluded_by_policy)+" | Equivalent retransmissions: "
      +fmt(result.excluded_retransmissions)+" | Total source-only: "
      +fmt(result.source_only_occurrences)+" | Final unmatched: "
      +fmt(result.final_unmatched)+" | Eligible conflicts: "
      +fmt(result.conflicting_eligible_values)+" | source SHA-256: "
      +result.source_sha256+" | final SHA-256: "+result.final_sha256
      +" | receipt SHA-256: "+result.receipt_sha256
      +" | SIGNED ADMISSION: NO. "+result.limitations;
    status.style.color="#ffb886";
  }catch(err){status.textContent="STATISTICS EVIDENCE NOT VERIFIED: "+err.message;status.style.color="#ffb886";}
  finally{button.disabled=false;}
}
async function runDefinitionsAudit(){
  const button=$("audit-definitions"),status=$("definitions-result");
  button.disabled=true;status.textContent="Checking complete historical definition values against pinned originals...";
  try{
    const result=await api("/api/definitions-audit");
    const gaps=result.source_only_field_tuples+result.final_only_field_tuples+result.duplicate_final_revision_grains;
    status.textContent=(result.exact?"EXACT FIELD MATCH":"RECONCILIATION FAILED")+
      " | "+fmt(result.source_rows)+" original / "+fmt(result.final_rows)+" final"+
      " | source-only: "+fmt(result.source_only_field_tuples)+
      " | final-only: "+fmt(result.final_only_field_tuples)+
      " | duplicate revision keys: "+fmt(result.duplicate_final_revision_grains)+
      " | fields compared: "+result.compared_fields.join(", ")+
      " | Source SHA-256: "+result.source_sha256+
      " | Final SHA-256: "+result.final_sha256+
      " | CME expiry-derived values remain excluded; owner research admission pending.";
    status.style.color=gaps?"#ffb886":"#67d4ac";
  }catch(err){status.textContent="AUDIT NOT VERIFIED: "+err.message;status.style.color="#ffb886";}
  finally{button.disabled=false;}
}
async function main(){
  tabs();
  $("audit-definitions").addEventListener("click",runDefinitionsAudit);
  $("load-statistics").addEventListener("click",loadStatisticsEvidence);
  $("audit-bars").addEventListener("click",runBarsAudit);
  $("load-v3-full").addEventListener("click",loadV3Evidence);
  $("v3-audit-chart").addEventListener("click",openV3AuditChart);
  for(const id of ["v3-audit-year","v3-audit-rank","v3-audit-metric"])
    $(id).addEventListener("change",renderV3Evidence);
  $("bars-audit-year").addEventListener("change",renderBarsAudit);
  for(let year=2010;year<=2022;year++){
    const option=document.createElement("option");option.value=year;option.textContent=year;
    $("bars-audit-year").appendChild(option);
  }
  for(let rank=1;rank<=12;rank++){
    const option=document.createElement("option");option.value=rank;option.textContent="M"+rank;$("rank").appendChild(option);
    const auditOption=option.cloneNode(true);$("v3-audit-rank").appendChild(auditOption);
  }
  for(let year=2010;year<=2022;year++){
    const option=document.createElement("option");option.value=year;option.textContent=year;
    $("v3-audit-year").appendChild(option);
  }
  $("v3-date").value="2022-12-31";for(let year=2022;year>=2010;year--){const opt=document.createElement("option");opt.value=year;opt.textContent=year;$("year").appendChild(opt);}
  $("year").value="2022";
  $("compare-mode").addEventListener("change",async e=>{setComparison(e.target.value);try{await reloadSeries();}catch(err){showError(err.message);}});
  $("rank").addEventListener("change",async e=>{state.rank=Number(e.target.value);try{await reloadSeries();}catch(err){showError(err.message);}});
  for(const id of ["v3-date","v3-clock","v3-window"])$(id).addEventListener("change",async()=>{try{await reloadSeries();}catch(err){showError(err.message);}});
  $("year").addEventListener("change",async e=>{state.year=Number(e.target.value);$("v3-date").value=state.year+"-12-31";try{await reloadContracts();}catch(err){showError(err.message);}});
  $("contract").addEventListener("change",async e=>{state.id=e.target.value;try{await reloadSeries();}catch(err){showError(err.message);}});
  $("metric").addEventListener("change",async e=>{state.metric=e.target.value;try{await reloadSeries();}catch(err){showError(err.message);}});
  $("scale").addEventListener("change",e=>{state.scale=Number(e.target.value);if(state.series)renderSeries();});
  $("refresh").addEventListener("click",async()=>{try{await reloadContracts();await reloadDecisions();}catch(err){showError(err.message);}});
  document.querySelectorAll("[data-decision]").forEach(b=>b.addEventListener("click",()=>saveDecision(b.dataset.decision)));
  try{const result=await api("/api/meta");state.meta=result.data;state.token=result.review_token;
    $("signing-status").textContent=result.signing_ready?"OWNER SIGNING READY":"APPROVAL CODE NOT COMMISSIONED";
    $("k-source").textContent=fmt(state.meta.source_rows);$("k-final").textContent=fmt(state.meta.final_rows);
    $("source-hash").textContent=state.meta.source_sha256;$("final-hash").textContent=state.meta.final_sha256;
    $("dataset-hash").textContent=state.meta.dataset_content_sha256;
    renderFamilies();
    await reloadContracts();await reloadDecisions();
    await loadStatisticsEvidence();
    await loadV3Evidence();
  }catch(err){showError("The verified dataset could not be opened: "+err.message);}
}
main();
