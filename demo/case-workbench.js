/* Guided local entry. No model, SQL, source fetching or browser persistence. */
(() => {
 "use strict";
 let mode="create",revision=0,prepared=null,base=null,scope=null,updateRecord=null;
 let dirty=false,opener=null;
 const savedDrafts=new Map();
 const metadataIds=["draftCaseId","draftTitle","draftQuestion","draftClock"];
 const editor=$("caseEditor"),rows=$("sourceRows");
 const field=(row,key)=>row.querySelector('[data-field="'+key+'"]');
 const isOpen=()=>!editor.hidden;
 const clearPreview=()=>{
  ++revision;prepared=null;$("draftReviewed").checked=false;$("draftReviewed").disabled=true;
  $("adoptDraft").disabled=true;$("previewDraft").disabled=false;
  $("draftPreview").replaceChildren();$("draftErrors").replaceChildren();
  for(const input of editor.querySelectorAll('[aria-invalid]')){
   input.removeAttribute("aria-invalid");input.removeAttribute("aria-describedby");
  }
 };
 function reset(){
  clearPreview();editor.hidden=true;base=null;scope=null;savedDrafts.clear();dirty=false;
 }
 function synchronizeRows(){
  const all=[...rows.children],limit=mode==="append"?12-base.sources.length:12;
  all.forEach((row,index)=>{
   row.querySelector("legend").textContent="Draft source "+(index+1);
   row.querySelector('[data-action="remove-source"]').disabled=all.length===1;
   for(const label of row.querySelectorAll('[data-clock]'))
    label.hidden=label.dataset.clock!==field(row,"clock_type").value;
  });
  $("addSourceRow").disabled=all.length>=limit;
 }
 function addRow(seed={}){
  const row=$("sourceRowTemplate").content.firstElementChild.cloneNode(true);
  const offset=field(row,"utc_offset_minutes");
  for(let minutes=-720;minutes<=840;minutes+=15){
   const sign=minutes<0?"−":"+",abs=Math.abs(minutes);
   const text="UTC"+sign+String(Math.floor(abs/60)).padStart(2,"0")+":"+String(abs%60).padStart(2,"0");
   offset.append(new Option(text,String(minutes)));
  }
  const previous=rows.lastElementChild;
  const defaults={source_id:"SOURCE-"+(base?base.sources.length+rows.children.length+1:rows.children.length+1),
   claim_key:previous?field(previous,"claim_key").value:"CLAIM_1",
   issuer_family:previous?field(previous,"issuer_family").value:"ISSUER_1",
   unit:previous?field(previous,"unit").value:"units",
   source_type:previous?field(previous,"source_type").value:"government_original"};
  for(const [key,value] of Object.entries({...defaults,...seed}))if(field(row,key))field(row,key).value=value;
  row.querySelector('[data-action="remove-source"]').addEventListener("click",()=>{
   if(rows.children.length===1)return;dirty=true;row.remove();clearPreview();synchronizeRows();
  });
  rows.append(row);synchronizeRows();
 }
 function scrollTo(target){
  target.scrollIntoView({block:"start",behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});
 }
 function grow(input){
  if(input?.tagName!=="TEXTAREA")return;
  input.style.height="auto";input.style.height=input.scrollHeight+2+"px";
 }
 function focusFirstInput(){
  [...editor.querySelectorAll("input:not([disabled])")].find(input=>input.getClientRects().length)?.focus({preventScroll:true});
 }
 let editorWidth=0;
 new ResizeObserver(entries=>{
  const width=entries[0].contentRect.width;
  if(!width||width===editorWidth)return;
  editorWidth=width;
  for(const input of editor.querySelectorAll("textarea"))if(input.getClientRects().length)grow(input);
 }).observe(editor);
 function open(kind,claimKey){
  if($("run").disabled)return;
  if(kind==="append"&&(!casePack||!lastInvestigation))return;
  opener=document.activeElement;
  const saved=savedDrafts.get(kind);dirty=false;
  mode=kind;clearPreview();rows.replaceChildren();
  base=kind==="append"?structuredClone(casePack):null;
  scope=kind==="append"?{as_of_utc:lastInvestigation.why.as_of_utc,
   strict:lastInvestigation.why.policy==="STRICT_AS_OF_2024",
   search_depth:lastInvestigation.resilience.requested_search_depth}:null;
  if(base&&base.sources.length>=12){
   $("error").textContent="This case already has 12 sources. Create a separate case to review more.";return;
  }
  editor.hidden=false;$("draftMetadata").hidden=kind==="append";
  $("editorHeading").textContent=kind==="append"?"Add evidence to the current case":"Create a case from source entries";
  $("editorContext").textContent=kind==="append"?
   "Original records stay intact. Compare at "+scope.as_of_utc+" under "+(scope.strict?"Strict":"reported-date")+
    " policy. This is an operator addition; no autonomous collection occurs.":
   "Enter the quantities and dates you read in each source. Nothing is fetched from a URL. The adopted case below stays unchanged until you use a reviewed preview.";
  $("adoptDraft").textContent=kind==="append"?"Use reviewed evidence":"Use reviewed case";
  let seed={};
  if(base){
   const rule=base.rules.find(rule=>rule.key===claimKey)||base.rules[0];
   seed={claim_key:rule.key,issuer_family:rule.issuer_family,unit:rule.unit,
    source_type:base.sources.every(row=>row.record_kind==="SYNTHETIC_CAPACITY")?"fictional":"government_original"};
  }else{
   for(const id of ["draftCaseId","draftTitle","draftQuestion","draftClock"])$(id).value="";
  }
  if(saved){
   for(const [id,value] of Object.entries(saved.metadata))$(id).value=value;
   for(const source of saved.sources)addRow(source);
   dirty=saved.dirty;
   $("editorContext").textContent+=" Your previous draft entries were restored. Review the claim groups and preview again at this boundary.";
  }else addRow(seed);
  setBusy(false);
  for(const input of editor.querySelectorAll("textarea"))if(input.getClientRects().length)grow(input);
  scrollTo(editor);focusFirstInput();
 }
 function entries(){
  return [...rows.children].map(row=>{
   const output={};
   for(const key of ["source_id","claim_key","issuer_family","unit","value","publisher","locator","excerpt","source_type","clock_type"])
    output[key]=field(row,key).value;
   if(output.clock_type==="precise")output.issued_at=field(row,"issued_at").value;
   else{
    output.local_day=field(row,"local_day").value;
    const offset=field(row,"utc_offset_minutes").value;
    output.utc_offset_minutes=offset===""?null:Number(offset);
   }
   return output;
  });
 }
 function showIssues(issues){
  const labels={issued_at:"Reported issue time",as_of_utc:"Review as-of",local_day:"Printed date",
   utc_offset_minutes:"Source UTC offset",value:"Quantity",source_id:"Source ID",claim_key:"Claim group",
   issuer_family:"Issuing organization ID",unit:"Unit ID",locator:"Source reference",excerpt:"Excerpt",case:"Case"};
  const messages={
   DRAFT_AWARE_ISO_CLOCK_REQUIRED:"Include a valid date, time and timezone, such as 2025-02-04T08:00:00Z.",
   DRAFT_WHOLE_NUMBER_0_TO_100000000:"Enter a whole number from 0 to 100,000,000.",
   DRAFT_TEXT_REQUIRED_OR_TOO_LONG:"Complete this field within its displayed length limit.",
   DRAFT_IDENTIFIER_INVALID:"Use a short ID starting with a letter; letters, numbers, underscores, dots and hyphens are accepted.",
   DRAFT_CLAIM_ISSUER_OR_UNIT_CONFLICT:"This claim group already uses a different issuing organization or unit. Keep them consistent or use a new claim group.",
   DRAFT_DUPLICATE_SOURCE_ID:"Give each draft source a different ID.",
   DRAFT_ADDITION_MUST_HAVE_NEW_SOURCE_ID:"This source ID is already in the adopted case. Give the new record a new ID.",
   DRAFT_SAFE_SOURCE_LOCATOR_REQUIRED:"Use an HTTPS reference without embedded credentials, or a synthetic:// reference for an exercise.",
   DRAFT_ORIGINAL_REQUIRES_HTTPS_REFERENCE:"An original publication needs an HTTPS source reference.",
   DRAFT_LOCAL_DAY_INVALID:"Enter a valid printed date.",
   DRAFT_EXPLICIT_UTC_OFFSET_REQUIRED:"Choose the source's UTC offset on that date.",
   DRAFT_SOURCE_COUNT_1_TO_12:"Enter between 1 and 12 sources.",CASE_RECORD_COUNTS_REFUSED:"The combined case must have at most 12 sources and 12 claim groups.",
   DRAFT_BYTES_LIMIT_60000:"Reduce the excerpts; the draft must fit within 60,000 UTF-8 bytes.",
   CASE_BYTES_LIMIT_60000:"Reduce the excerpts; the prepared case must fit within 60,000 UTF-8 bytes.",
   SOURCE_IDENTITY_ALIAS_REFUSED:"Check for repeated source IDs, references or identical excerpts.",
   PREVIEW_UNAVAILABLE_NO_DRAFT_APPLIED:"The local preview could not be completed. Keep your entries and try again.",
   REQUEST_REFUSED:"The local server refused this draft. Check the source count and excerpt sizes."};
  $("draftErrors").append(node("p","","Preview refused. Correct the listed entries, then preview again. The adopted case is unchanged."));
  let firstInvalid=null;
  for(const [index,issue] of issues.entries()){
   const location=issue.row?"Source "+issue.row:"Case";
   const message=node("p","",location+" · "+(labels[issue.field]||issue.field)+": "+
    (messages[issue.code]||"The declaration did not pass the case consistency checks. Review the source fields before trying again."));
   message.id="draft-issue-"+index;$("draftErrors").append(message);
   const row=rows.children[Number(issue.row)-1];
   const target=row?[...row.querySelectorAll('[data-field]')].find(input=>input.dataset.field===issue.field):
    ({case_id:$("draftCaseId"),title:$("draftTitle"),question:$("draftQuestion"),as_of_utc:$("draftClock")})[issue.field];
   target?.setAttribute("aria-invalid","true");
   target?.setAttribute("aria-describedby",message.id);
   if(target&&!firstInvalid)firstInvalid=target;
  }
  if(firstInvalid)firstInvalid.focus();
  else{$("draftErrors").tabIndex=-1;$("draftErrors").focus();}
 }
 function renderPreview(result){
  $("draftPreview").append(node("h3","","Review prepared source entries"),
   node("p","muted","Hashes and pins were generated from your entries. No source was fetched or independently verified."));
  for(const source of result.preview_sources){
   const box=node("div","preview-source");
   box.append(node("b","",source.source_id+" · "+source.declared_value+" "+source.unit+
     (source.fictional?" · FICTIONAL":" · unverified original reference")),
    node("p","muted",(source.admitted_at_requested_policy?"Admitted":"Excluded")+
     " at this policy. Admission clock: "+source.admission_clock_utc+" · "+source.clock_basis),
    node("p","muted",source.publisher+" · "+source.locator),node("p","",source.excerpt));
   $("draftPreview").append(box);
  }
  const report=mode==="append"?result.after:result.investigation;
  const summary=Object.entries(report.why.selected_claims).map(([key,claim])=>key+": "+value(claim));
  $("draftPreview").append(node("p","",summary.length?"Prepared conclusion: "+summary.join("; "):
   "Prepared conclusion: ABSTAIN — no admissible selected claim."));
  if(mode==="append"){
   const effects=node("div");putEffects(effects,result.comparison.changed_claims);$("draftPreview").append(effects);
  }
 }
 async function preview(event){
  event.preventDefault();clearPreview();
  const current=revision,mainGeneration=generation,kind=mode;
  $("previewDraft").disabled=true;
  const body=kind==="append"?{case:base,sources:entries(),...scope}:
   {draft:{case_id:$("draftCaseId").value,title:$("draftTitle").value,
    question:$("draftQuestion").value,as_of_utc:$("draftClock").value,sources:entries()}};
  try{
   const response=await fetch(kind==="append"?"/case-evidence":"/case-draft",{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
   const result=await response.json();
   if(current!==revision||mainGeneration!==generation||!isOpen())return;
   if(!response.ok){
    showIssues(Array.isArray(result.issues)?result.issues:[{field:"case",code:"REQUEST_REFUSED"}]);return;
   }
   const report=kind==="append"?result.after:result.investigation;
   if(result.kind!==(kind==="append"?"EVIDENCETRAIL_OPERATOR_EVIDENCE_UPDATE_V1":"EVIDENCETRAIL_CASE_DRAFT_PREVIEW_V1")||
     result.model_or_sponsor_called!==false||report?.kind!=="EVIDENCETRAIL_OPEN_CASE_INVESTIGATION_V1"||
     report.model_or_sponsor_called!==false||report.external_source_authentication_performed!==false||
     report.trust_basis!=="OPERATOR_DECLARED_NOT_EXTERNALLY_VERIFIED")throw Error();
   prepared={result,kind,revision:current};renderPreview(result);$("draftReviewed").disabled=false;
   scrollTo($("draftPreview"));
  }catch{
   if(current===revision&&mainGeneration===generation&&isOpen())
    showIssues([{field:"case",code:"PREVIEW_UNAVAILABLE_NO_DRAFT_APPLIED"}]);
  }finally{if(current===revision)$("previewDraft").disabled=false;}
 }
 async function adopt(){
  if(!prepared||prepared.revision!==revision||!$("draftReviewed").checked)return;
  const {result,kind}=prepared;reset();
  if(kind==="create"){
   const current=++generation;await loadCase(result.case_pack,current);return;
  }
  ++generation;clearView();casePack=result.case_pack;withdrawals=new Set();setCaseControls(true);
  $("caseClock").value=result.comparison.as_of_utc;
  $("mode").value=result.comparison.policy==="STRICT_AS_OF_2024"?"strict":"reported";
  $("searchDepth").value=String(result.after.resilience.requested_search_depth);
  render(result.after.why);renderInvestigation(result.after,casePack);
  updateRecord=result;$("updatePanel").hidden=false;
  $("updateSummary").textContent="Operator added "+result.new_source_ids.join(", ")+"; "+
   result.new_admitted_source_ids.length+" admitted out of "+result.new_source_ids.length+
   ". Compared at the same "+result.comparison.as_of_utc+" · "+result.comparison.policy+". "+
   (result.comparison.value_or_availability_changed?"Claim value or availability changed.":"Claim values unchanged.");
  $("updateChanges").replaceChildren();putEffects($("updateChanges"),result.comparison.changed_claims);
  $("updateTrace").replaceChildren();
  for(const step of result.execution_trace)$("updateTrace").append(node("li","muted",JSON.stringify(step)));
  $("removed").disabled=false;$("status").textContent="Verified local source-pinned replay";
  setBusy(false);$("updatePanel").scrollIntoView({block:"start",behavior:"smooth"});
 }
 function onResult(report){
  $("nextEvidencePanel").hidden=false;$("nextEvidenceList").replaceChildren();
  const needs=report.why.evidence_needed;
  for(const need of needs){
   const section=node("div","preview-source");
   section.append(node("b","",need.claim_key+" · "+need.reason_code),node("p","muted",need.next_action));
   const button=node("button","secondary","Add a source for "+need.claim_key);button.type="button";
   button.addEventListener("click",()=>open("append",need.claim_key));section.append(button);
   $("nextEvidenceList").append(section);
  }
  if(!needs.length)$("nextEvidenceList").append(node("p","muted",
   "A declared claim is selected. Check source withdrawal groups, or add a separately reviewed source to test whether the conclusion survives."));
 }
 function download(data,name){
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));
  const link=document.createElement("a");link.href=url;link.download=name;document.body.append(link);
  link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 window.caseWorkbench={reset,isOpen,onResult,clearResult:()=>{updateRecord=null;}};
 $("createCase").addEventListener("click",()=>open("create"));
 $("addEvidence").addEventListener("click",()=>open("append"));
 $("addSourceRow").addEventListener("click",()=>{if(!$("addSourceRow").disabled){dirty=true;clearPreview();addRow();rows.lastElementChild.querySelector("input")?.focus();}});
 $("cancelDraft").addEventListener("click",()=>{
  const sources=[...rows.children].map(row=>Object.fromEntries(
   [...row.querySelectorAll('[data-field]')].map(input=>[input.dataset.field,input.value])));
  savedDrafts.set(mode,{metadata:Object.fromEntries(metadataIds.map(id=>[id,$(id).value])),sources,dirty});
  clearPreview();editor.hidden=true;setBusy(false);
  $("status").textContent="Drafts kept on this page. Reopen their editor to continue; preview and review again. Replacing the active case clears drafts.";
  if(opener?.isConnected&&!opener.disabled)opener.focus();
 });
 $("draftForm").addEventListener("input",event=>{dirty=true;clearPreview();synchronizeRows();grow(event.target);});
 $("draftForm").addEventListener("change",event=>{
  if(event.target===$("draftReviewed"))return;dirty=true;clearPreview();synchronizeRows();
 });
 // The review checkbox is outside the source data; it must not erase its own preview.
 $("draftReviewed").addEventListener("input",event=>event.stopPropagation());
 $("draftReviewed").addEventListener("change",()=>{
  $("adoptDraft").disabled=!prepared||prepared.revision!==revision||!$("draftReviewed").checked;
 });
 $("draftForm").addEventListener("submit",preview);$("adoptDraft").addEventListener("click",adopt);
 window.addEventListener("beforeunload",event=>{
  if((dirty&&isOpen())||[...savedDrafts.values()].some(draft=>draft.dirty)){event.preventDefault();event.returnValue="";}
 });
 $("exportEvidenceRequest").addEventListener("click",()=>{
  if(!casePack||!lastInvestigation)return;
  download({kind:"EVIDENCETRAIL_ANALYST_EVIDENCE_REQUEST_V1",case_id:casePack.case_id,
   as_of_utc:lastInvestigation.why.as_of_utc,policy:lastInvestigation.why.policy,
   questions:lastInvestigation.why.evidence_needed,suggested_checks_not_executed:true,
   source_withdrawal_search:lastInvestigation.resilience,
   notice:"An analyst plan, not an executed source query or independent source attestation."},"evidencetrail-evidence-request.json");
 });
 $("exportInvestigation").addEventListener("click",()=>{
  if(!casePack||!lastInvestigation)return;
  download({kind:"EVIDENCETRAIL_OPERATOR_INVESTIGATION_RECORD_V1",case_pack:casePack,
   investigation:lastInvestigation,latest_operator_update:updateRecord,
   external_source_authentication_performed:false,independent_human_participants:0},"evidencetrail-investigation.json");
 });
})();
