// Technical operator comparison over one exact already-public parent.
// The independent programmable-editor recipe is setup, not a built-in editor claim.
// No provider, key, model, package installation or mutable runtime operation.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createHash,webcrypto} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,l)=>i%2?a:a.concat([[v,l[i+1]]]),[]));
if(!args['--parent'] || !args['--out'])throw Error('Use --parent PUBLIC_PARENT_JSON --out PRIVATE_RECEIPTS');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),out=path.resolve(args['--out']);
if(out===root || out.startsWith(root+path.sep))throw Error('Parent-derived output stays outside the source checkout.');
const sha=x=>createHash('sha256').update(x).digest('hex'),copy=x=>JSON.parse(JSON.stringify(x));
const sort=x=>Array.isArray(x)?x.map(sort):x && typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sort(x[k])])):x;
const canon=x=>JSON.stringify(sort(copy(x))),words=x=>String(x || '').trim().split(/\s+/u).filter(Boolean).length;
const lexical=x=>String(x || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
const raw=fs.readFileSync(args['--parent'],'utf8'),source=JSON.parse(raw),parentHash=sha(raw);
if(parentHash!=='53b2f25bdfc431a2567ef7af4f1b9d51282ca62904a7e121dc484e1985c0435d')throw Error('Wrong public parent bytes.');
fs.mkdirSync(out,{recursive:true});
const write=(n,v)=>fs.writeFileSync(path.join(out,n),JSON.stringify(v,null,2)+'\n');
const edit='Une trace matérielle. Une pression contre la réalité.',rejectEdit='Une trace matérielle.';

// Independent editor recipe. It neither imports nor calls the workbench core.
function editorDraft(parentRaw) {
  const p=JSON.parse(parentRaw);let cursor=0;
  return {format:'programmable-json-editor-decision-v1',revision:0,parent_sha256:sha(parentRaw),parent_utf8:parentRaw,
    local_target:{sound_off:true},decision:null,native_derivative_review:'not_executed',semantic_review:'not_verified',
    shots:p.brief.shots.map(s=>{
      const spoken=String(s.voiceover || ''),caption=String(s.on_screen_text || '');
      const gap=Boolean(spoken.trim()) && !lexical(caption).includes(lexical(spoken));
      const start=cursor;cursor+=s.duration_seconds;
      return {id:s.id,visual_prompt:s.visual_prompt,assets:copy(s.assets || []),aspect_ratio:s.aspect_ratio,
        duration_seconds:s.duration_seconds,start_seconds:start,end_seconds:cursor,voiceover:'',sonic_direction:'',
        received_voiceover:spoken,received_caption:caption,spoken_sequence_not_on_screen:gap,
        on_screen_text:gap?[caption,spoken].filter(Boolean).join('\n'):caption || spoken,
        received_lineage:{decision_refs:copy(s.decision_refs || []),evidence_refs:copy(s.evidence_refs || []),retained_entity_refs:copy(s.retained_entity_refs || [])}};
    })};
}
function editorValidate(d,parentRaw) {
  if(sha(parentRaw)!==d.parent_sha256 || d.parent_utf8!==parentRaw)throw Error('The editor decision belongs to different parent bytes.');
  const p=JSON.parse(parentRaw);
  if(d.shots.length!==p.brief.shots.length)throw Error('Shot inventory changed.');
  for(let i=0;i<d.shots.length;i++){
    const s=d.shots[i],old=p.brief.shots[i];
    if(s.id!==old.id || s.visual_prompt!==old.visual_prompt || s.duration_seconds!==old.duration_seconds ||
       s.aspect_ratio!==old.aspect_ratio || canon(s.assets)!==canon(old.assets || []) ||
       s.voiceover!=='' || s.sonic_direction!=='' || typeof s.on_screen_text!=='string')throw Error('Editor recipe changed protected material.');
  }
  if(d.decision && d.decision.caption_identity!==sha(canon(d.shots.map(s=>s.on_screen_text))))throw Error('Edit invalidated the previous editor decision.');
  return {native_review:'not_executed',semantic_review:'not_verified',
    errors:d.shots.filter(s=>!s.on_screen_text.trim() && (s.received_voiceover || s.received_caption)).map(s=>s.id),
    timing_estimates:d.shots.map(s=>({id:s.id,word_count:words(s.on_screen_text),available_seconds:s.duration_seconds,seconds_at_3_words_s:words(s.on_screen_text)/3,may_not_fit:words(s.on_screen_text)/3>s.duration_seconds}))};
}
function editorEdit(d,id,text) {d.shots.find(s=>s.id===id).on_screen_text=text;d.revision++;d.decision=null;}
function editorDecide(d,parentRaw,status) {
  const checks=editorValidate(d,parentRaw);
  if(status==='accept' && checks.errors.length)throw Error('Missing screen text.');
  d.decision={status,caption_identity:sha(canon(d.shots.map(s=>s.on_screen_text))),scope:'Technical operator decision, not author preference or semantic review.'};
  const payload=copy(d),hash=sha(canon(payload));return {payload,payload_sha256:hash,derived_id:'json-editor-'+hash,identity_method:'JSON-normalized recursively sorted keys; not RFC8785'};
}
const baseline=editorDraft(raw),initialGaps=baseline.shots.filter(s=>s.spoken_sequence_not_on_screen).map(s=>s.id);
write('BASELINE-INITIAL-DRAFT.json',baseline);
editorEdit(baseline,'shot_02',edit);const accepted=editorDecide(baseline,raw,'accept');write('BASELINE-ACCEPT.json',accepted);
// A stale accepted file remains historical. The working draft must be decided again.
editorEdit(baseline,'shot_02',rejectEdit);const invalidated=baseline.decision===null;
write('BASELINE-UNDECIDED-AFTER-EDIT.json',baseline);
const rejected=editorDecide(baseline,raw,'reject');write('BASELINE-REJECT.json',rejected);
// Real write/reopen, not an assertion about an imaginary editor session.
const reopenedFile=JSON.parse(fs.readFileSync(path.join(out,'BASELINE-REJECT.json'),'utf8'));
if(sha(canon(reopenedFile.payload))!==reopenedFile.payload_sha256)throw Error('Saved editor file changed.');
const reopened=reopenedFile.payload;editorValidate(reopened,raw);
const resumedCaption=reopened.shots.find(s=>s.id==='shot_02').on_screen_text;
let changedParentRefused=false;
const changedSource=copy(source);changedSource.brief.synopsis+=' [injected technical mutation]';
try{editorValidate(reopened,JSON.stringify(changedSource));}catch{changedParentRefused=true;}
write('BASELINE-REOPENED.json',{source_file:'BASELINE-REJECT.json',payload_sha256:reopenedFile.payload_sha256,shot_02_caption:resumedCaption,decision:reopened.decision.status,hash_validated:true,manual_caption_retyping:0});
write('BASELINE-RESULTS.json',{kind:'technical_recipe_not_human_user_test',parent_hash:parentHash,initial_gaps:initialGaps,
  accepted_exact_caption:accepted.payload.shots[1].on_screen_text===edit,edit_invalidated_decision:invalidated,
  rejected_exact_caption:rejected.payload.shots[1].on_screen_text===rejectEdit,resume_exact_saved_caption:resumedCaption===rejectEdit,
  changed_parent_refused:changedParentRefused,
  recipe_setup:'Independent editorDraft/editorValidate/editorEdit/editorDecide functions in comparisons/run_local_tasks.mjs. This is explicitly prepared programmable-editor assistance, not a stock editor feature or free preparation.',
  semantic_operations:[{task:'inspect gaps and transfer',operations:1,kind:'prepared recipe invocation'},{task:'edit shot2',operations:1,kind:'JSON field edit'},{task:'accept/export',operations:1,kind:'decision+save invocation'},{task:'edit again',operations:1,kind:'JSON field edit'},{task:'reject/export',operations:1,kind:'decision+save invocation'},{task:'reopen saved file and verify',operations:1,kind:'file read+validator invocation'}],
  action_count_limit:'Semantic recipe invocations are not GUI click counts, human time, setup cost or artistic quality. No aggregate speed winner is inferred.'});

// The delivered core is a separate path, with its own source binding and identity.
const core=fs.readFileSync(path.join(root,'editorial-workbench.js'),'utf8'),ctx=vm.createContext({crypto:webcrypto,TextEncoder});
vm.runInContext(core+';globalThis.work=EditorialWorkbench;',ctx);const work=ctx.work;
const context={source_sha256:parentHash,display_kind:'recorded',captured_at:source.brief.created_at};
const draft=work.createSilentDraft(source,context),workGaps=draft.shots.filter(s=>s.transfer.spoken_word_sequence_not_on_screen).map(s=>s.id);
work.setSilentCaption(draft,source,'shot_02',edit);
const appAccept=await work.finalizeSilentDraft(draft,source,raw,'accept','Technical operator comparison; not author preference.','2026-10-23T17:00:00Z');
write('WORKBENCH-CORE-ACCEPT.json',appAccept);
work.setSilentCaption(draft,source,'shot_02',rejectEdit);
const appReject=await work.finalizeSilentDraft(draft,source,raw,'reject','Technical operator comparison; not author preference.','2026-10-23T17:00:01Z');
write('WORKBENCH-CORE-REJECT.json',appReject);
let appChangedRefused=false;try{work.inspectSilentDraft(draft,changedSource);}catch{appChangedRefused=true;}

// Synthetic counterexamples. No new cultural case, writer or provider result.
const controls=[];
const allCaptioned=copy(source);for(const s of allCaptioned.brief.shots)s.on_screen_text=s.voiceover;
const controlDraft=p=>work.createSilentDraft(p,{...context,source_sha256:sha(JSON.stringify(p))});
const cd=controlDraft(allCaptioned),ed=editorDraft(JSON.stringify(allCaptioned));
controls.push({id:'already_caption_complete',synthetic:true,app_gaps:cd.shots.filter(s=>s.transfer.spoken_word_sequence_not_on_screen).length,editor_gaps:ed.shots.filter(s=>s.spoken_sequence_not_on_screen).length});
const tooLong=copy(source);tooLong.brief.user_constraints.timing_locked=true;tooLong.brief.shots[0].voiceover=Array(8).fill(tooLong.brief.shots[0].voiceover).join(' ');
const longApp=controlDraft(tooLong),longRaw=JSON.stringify(tooLong),longEditor=editorDraft(longRaw);
controls.push({id:'fixed_timing_text_too_long',synthetic:true,app_warning:work.inspectSilentDraft(longApp,tooLong).caption_reading_estimates[0].may_not_fit,editor_warning:editorValidate(longEditor,longRaw).timing_estimates[0].may_not_fit,retimed:false});
const degradedApp=work.createSilentDraft(source,context),degradedEditor=editorDraft(raw),bad='A visible monster explains everything.';
work.setSilentCaption(degradedApp,source,'shot_02',bad);editorEdit(degradedEditor,'shot_02',bad);
controls.push({id:'free_edit_breaks_canon',synthetic:true,caption:bad,app_structural_errors:work.inspectSilentDraft(degradedApp,source).errors.length,editor_structural_errors:editorValidate(degradedEditor,raw).errors.length,semantic_review_in_both:'not_verified',warning:'A structurally valid edit can damage the story. No comprehension/canon advantage is established.'});
write('SYNTHETIC-CONTROLS.json',controls);
write('CORE-RESULTS.json',{kind:'actual_source_core_replay_not_UI_or_native_execution',authentic_cultural_cases:1,parent_hash:parentHash,core_sha256:sha(core),
  workbench_gaps:workGaps,baseline_gaps:initialGaps,same_gap_ids:JSON.stringify(workGaps)===JSON.stringify(initialGaps),
  app_accept_exact_caption:appAccept.payload.shots[1].on_screen_text===edit,app_reject_exact_caption:appReject.payload.shots[1].on_screen_text===rejectEdit,
  app_changed_parent_refused:appChangedRefused,baseline_changed_parent_refused:changedParentRefused,
  app_variant_native_status:appAccept.payload.variant_verification.native_status,
  baseline_resume_received_from_real_file:true,app_UI_resume:'not_yet_observed',new_provider_calls:0,new_model_calls:0,run_families:0});

// Network-disabled actual UI replay, from public parent only; no private cache read.
const manifest={captured_at:source.brief.created_at,director_version:source.director_version,
  archive:{sha256:'not_used_public_export_only'},original_export:{sha256:parentHash},
  scope:{public_references:['The Turn of the Screw']},original_reception:{qloo_network_attempts_used:source.run_budget.qloo_network_attempts_used,model_calls_used:source.run_budget.model_calls_used,complete_shots:4}};
let html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const literal=x=>JSON.stringify(x).replaceAll('<','\\u003c');
const marker='loadPreset();restorePending();loadConfiguration();viewRecording();';
if(!html.includes(marker))throw Error('Inspect changed UI startup before replay.');
html=html.replace(marker,`loadPreset();state.bundle=${literal(source)};state.snapshot=snapshot();state.displayKind='recorded';state.recording={originalRaw:${literal(raw)},manifest:${literal(manifest)},apiBase:RECORDING_ORIGIN};state.configurationReady=false;state.apiBase=null;renderBundle();$('connectionStatus').textContent='OFFLINE TECHNICAL COMPARISON. Network blocked. Public parent20Oct; no provider/model/native run.';`);
html=html.replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; connect-src \'none\'; img-src data:; media-src \'none\'">');
html=html.replace('<body>','<body><p class="status warn">LOCAL TECHNICAL COMPARISON · authentic dated public parent; no author study, new generation or rendered film.</p>');
fs.writeFileSync(path.join(out,'OFFLINE-REPLAY.html'),html);
write('SOURCE-INVENTORY.json',{observed_at:new Date().toISOString(),base:'8145ac6708fd05043109aec841e1375cdd6bc671',parent_sha256:parentHash,parent_bytes:Buffer.byteLength(raw),core_sha256:sha(core),frontend_sha256:sha(fs.readFileSync(path.join(root,'index.html'))),recipe_sha256:sha(fs.readFileSync(fileURLToPath(import.meta.url))),offline_replay_sha256:sha(html),external_writes:false,new_Qloo_model_calls:0});
console.log(JSON.stringify({status:'LOCAL_TECHNICAL_TASKS_EXECUTED_UI_PENDING',out,parentHash,workGaps,controls},null,2));
