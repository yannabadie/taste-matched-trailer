import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import {gardeningSource} from './editorial-fixture.mjs';

const root=new URL('../',import.meta.url),core=fs.readFileSync(new URL('editorial-workbench.js',root),'utf8');
const sandbox=vm.createContext({crypto:webcrypto,TextEncoder});vm.runInContext(core+';globalThis.work=EditorialWorkbench;',sandbox);const work=sandbox.work;
const clone=x=>JSON.parse(JSON.stringify(x));
const hash=x=>createHash('sha256').update(x).digest('hex');
function build(source=gardeningSource()){return work.build(source,{source_sha256:hash(JSON.stringify(source)),display_kind:'fixture'});}

test('two complete edits change actual pacing while preserving canon, order, images and lineage',()=>{
  const source=gardeningSource(),before=clone(source),out=build(source);
  assert.equal(out.status,'ready_for_author_choice');assert.equal(out.directions.length,2);
  assert.notDeepEqual(clone(out.directions[0].shots.map(s=>s.duration_seconds)),clone(out.directions[1].shots.map(s=>s.duration_seconds)));
  for(const direction of out.directions){
    assert.equal(direction.shots.reduce((n,s)=>n+Math.round(s.duration_seconds*100),0),3800);
    assert.deepEqual(clone(direction.shots.map(s=>s.id)),source.brief.shots.map(s=>s.id));
    for(let i=0;i<4;i++)for(const key of ['visual_prompt','voiceover','on_screen_text','assets','decision_refs','evidence_refs','retained_entity_refs'])assert.deepEqual(clone(direction.shots[i][key]),source.brief.shots[i][key]);
  }
  assert.deepEqual(source,before);assert.deepEqual(clone(out.preserved.user_constraints),source.brief.user_constraints);
});
test('non-mystery canon remains gardening; no stock mystery imagery or words are invented',()=>{
  const out=build();
  for(const direction of out.directions){
    assert.equal(direction.shots[0].visual_prompt,'A seed tray on a wooden table.');
    assert.ok(!/haunt|unseen presence|narrator doubts|oppressive|shadowy corridor/i.test(JSON.stringify(direction)));
  }
});
test('sound-off adaptation has no active spoken or sonic track; captions use existing words only',()=>{
  const source=gardeningSource();source.brief.user_constraints.sound_off=true;source.brief.shots[1].on_screen_text='';
  const out=build(source);
  for(const direction of out.directions){
    assert.equal(direction.spoken_track_planned,false);
    for(const shot of direction.shots){assert.equal(shot.voiceover,'');assert.equal(shot.sonic_direction,'No soundtrack.');}
    assert.equal(direction.shots[1].on_screen_text,source.brief.shots[1].voiceover);
    assert.equal(direction.shots[1].editorial_delivery.caption_origin,'verbatim_received_narration');
    assert.equal(direction.shots[0].editorial_delivery.source_narration_omitted,false);
  }
  const choice=work.choose(out,source,'images_lead');assert.equal(choice.original_received_document.brief.shots[1].voiceover,'Give each pot a name.');
});
test('fixed individual timing and a silent four-second no-contrast case refuse without invented alternatives',()=>{
  const source=gardeningSource();source.brief.user_constraints.timing_locked=true;
  assert.equal(build(source).status,'unavailable');assert.match(build(source).reason,/fixes individual shot timing/);
  delete source.brief.user_constraints.timing_locked;source.brief.user_constraints.sound_off=true;source.brief.user_constraints.duration_seconds=4;source.brief.total_duration_seconds=4;source.brief.shots.forEach(s=>s.duration_seconds=1);
  assert.equal(build(source).status,'unavailable');assert.match(build(source).reason,/no meaningful contrast/);
});
test('failed, invalidated, empty-word and unverified live sources cannot be repackaged as options',()=>{
  for(const mutate of [s=>s.workflow_status='needs_revision',s=>s.brief.shots[0].line_status='invalidated_by_removed_reference',s=>s.brief.shots.forEach(x=>{x.voiceover='';x.on_screen_text='';}),s=>s.mode='live']){
    const source=gardeningSource();mutate(source);assert.equal(build(source).status,'unavailable');
  }
});
test('long narration reports an explicit timing problem rather than silently accelerating speech',()=>{
  const source=gardeningSource();source.brief.shots[0].voiceover=Array(80).fill('word').join(' ');const out=build(source);
  for(const direction of out.directions){assert.equal(direction.readiness,'needs_timing_review');assert.equal(direction.warnings[0].voice_seconds_estimate,32);assert.equal(direction.shots[0].voiceover,source.brief.shots[0].voiceover);}
});
test('selection, tie and rejection preserve exact original bytes and never assert measured usefulness',()=>{
  const source=gardeningSource(),out=build(source),raw=JSON.stringify(source);
  for(const choice of ['images_lead','words_lead','tie','neither']){
    const decision=work.choose(out,source,choice,'My stated intention','2026-10-23T14:00:00Z',raw);
    assert.equal(decision.choice,choice);assert.equal(decision.original_received_export_utf8,raw);assert.equal(hash(raw),decision.source.source_sha256);
    assert.equal(decision.author_preference_is_not_a_measured_quality_gain,true);
    assert.equal(decision.selected_direction===null,['tie','neither'].includes(choice));
  }
  assert.throws(()=>work.choose(out,source,'automatic'));assert.throws(()=>work.choose(out,source,'images_lead','','','{}'),/do not match/);
  const other=clone(source);other.brief.synopsis+=' Changed canon.';
  assert.throws(()=>work.choose(out,other,'images_lead','','',JSON.stringify(other)),/source changed/);
});
test('both delivered HTML copies contain exactly the tested core and parse without another dependency',()=>{
  const html=fs.readFileSync(new URL('index.html',root),'utf8');assert.equal(html,fs.readFileSync(new URL('taste-matched-trailer/index.html',root),'utf8'));
  assert.equal(html.match(/<script id="editorialWorkbenchCore">\n([\s\S]*?)<\/script>/)[1].trim(),core.trim());
  for(const match of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
});

function browser({realTimers=false,inputSource=null,crypto=webcrypto}={}){
  const elements=new Map(),downloads=[],blobs=new Map();
  const element=id=>elements.get(id)||elements.set(id,{id,value:'',checked:false,hidden:false,disabled:false,innerHTML:'',textContent:'',className:'',listeners:{},addEventListener(type,listener){this.listeners[type]=listener;},appendChild(){}}).get(id);
  const document={getElementById:element,querySelector(){return document.selected || null;},addEventListener(){},body:{appendChild(){}},createElement(){return{remove(){},click(){downloads.push({filename:this.download,blob:blobs.get(this.href)});}};}};
  class LocalURL extends URL{static createObjectURL(blob){const id='blob:test-'+blobs.size;blobs.set(id,blob);return id;}static revokeObjectURL(){}}
  const window={document,location:{origin:'http://localhost',href:'http://localhost/index.html'},addEventListener(){}};
  const context=vm.createContext({document,window,crypto,TextEncoder,TextDecoder,Blob,URL:LocalURL,AbortController,setTimeout(){},setInterval:realTimers?setInterval:()=>1,clearInterval:realTimers?clearInterval:()=>{},performance:realTimers?performance:{now:()=>0},console});
  const html=fs.readFileSync(new URL('index.html',root),'utf8');let script=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
  script=script.replace('loadPreset();restorePending();loadConfiguration();viewRecording();','');
  vm.runInContext(script+';globalThis.qa={state,snapshot,renderCandidate,renderBundle,renderEditorialWorkbench,chooseEditorialOption,downloadEditorialDecision,invalidate,startEditorialPreview,stopEditorialPreview,prepareSilentAdaptation,updateSilentCaption,decideSilentAdaptation,downloadSilentAdaptation,invalidateSilentDecision,resumeSilentDecisionFile,silentImportFailure,prepareShotAmendment,updateShotAmendment,decideShotAmendment,downloadShotAmendment};',context);
  const source=inputSource || gardeningSource(),raw=JSON.stringify(source);Object.assign(context.qa.state,{bundle:source,displayKind:'recorded',recording:{originalRaw:raw,manifest:{captured_at:'2026-10-20T13:41:27Z'}}});context.qa.state.snapshot=context.qa.snapshot();
  return{qa:context.qa,document,element,downloads,raw};
}
test('desk clarity: scores and response positions are readable without changing received data',()=>{
  const b=browser(),candidate={entity_id:'synthetic-film',name:'Synthetic reference',score_value:0.8121439473,score_field:'affinity',returned_order:0},decision={id:'synthetic-decision',selected_entity_ids:['synthetic-film']};
  const before=JSON.stringify({candidate,decision}),html=b.qa.renderCandidate(candidate,decision);
  assert.match(html,/>0\.81<\/div>/);assert.match(html,/title="0\.8121439473"/);assert.match(html,/Position in Qloo's response: 1/);
  assert.equal(JSON.stringify({candidate,decision}),before);
});
test('desk clarity: missing scores and invalid response positions do not become measured zero or position zero',()=>{
  const b=browser(),decision={selected_entity_ids:[]};
  for(const returned_order of [undefined,null,-1,0.5,Number.MAX_SAFE_INTEGER,Number.MAX_SAFE_INTEGER+1]){
    const html=b.qa.renderCandidate({returned_order,score_value:null},decision);
    assert.match(html,/Position in Qloo's response: not supplied/);assert.match(html,/>not supplied<\/div>/);
  }
  assert.match(b.qa.renderCandidate({score_value:0,returned_order:1},decision),/>0\.00<\/div>/);
});
test('desk clarity: editorial translation preserves the French source and ignores inherited object keys',()=>{
  const source=gardeningSource();source.workflow_status='blocked';
  const french='Références culturelles pour une direction créative et un brief — sans promesse de comparables commerciaux, de conversion, de ventes ou de positionnement éditorial validé.';
  source.limitations=[french,'constructor','toString','__proto__','<img src=x onerror=alert(1)>'];
  const b=browser({inputSource:source}),before=JSON.stringify(source);b.qa.state.displayKind='fixture';b.qa.renderBundle();
  const html=b.element('publicLimitations').innerHTML;
  assert.ok(html.includes(french));assert.equal((html.match(/English reading aid:/g)||[]).length,1);
  assert.ok(!html.includes('function Object'));assert.ok(!html.includes('[object Object]'));assert.ok(html.includes('&lt;img'));assert.equal(JSON.stringify(source),before);
});
test('real frontend choice downloads a separate dated recomposition; original bytes remain intact',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();assert.equal(b.qa.state.editorial.status,'ready_for_author_choice');
  b.document.selected={value:'images_lead',parentElement:{textContent:'Let the images lead'}};b.qa.chooseEditorialOption();b.element('editorialReason').value='Give the first image room.';
  await b.qa.downloadEditorialDecision();assert.equal(b.downloads.length,1);const decision=JSON.parse(await b.downloads[0].blob.text());
  assert.equal(decision.choice,'images_lead');assert.equal(decision.source.display_kind,'recorded');assert.equal(decision.original_received_export_utf8,b.raw);assert.equal(decision.reason,'Give the first image room.');
  b.qa.invalidate();assert.equal(b.qa.state.editChoice,null);assert.equal(b.element('exportEditorialBtn').disabled,true);assert.match(b.element('statusNotice').textContent,/earlier local edit decision belongs to its dated source/);
});
test('an input change during source-hash verification blocks download of a stale local choice',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();b.document.selected={value:'words_lead',parentElement:{textContent:'Let the words lead'}};b.qa.chooseEditorialOption();
  const pending=b.qa.downloadEditorialDecision();b.qa.invalidate();await pending;assert.equal(b.downloads.length,0);
});
test('text storyboard follows source timing and distinguishes held image from narration cue',()=>{
  const source=gardeningSource(),out=build(source),a=out.directions[0],b=out.directions[1];
  assert.equal(work.frameAt(a,0).voice_cue,false);assert.equal(work.frameAt(a,.9).visible_text,'');
  assert.equal(work.frameAt(b,0).voice_cue,true);assert.equal(work.frameAt(b,0).visible_text,'Start');
  assert.equal(work.frameAt(a,8).shot_id,'shot_01');assert.equal(work.frameAt(b,8).shot_id,'shot_02');
  assert.equal(work.frameAt(a,38).completed,true);assert.equal(work.frameAt(b,38).completed,true);
});
test('stop, replay and source invalidation manage one local timer without choosing an export',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();b.qa.startEditorialPreview('images_lead');
  assert.equal(b.qa.state.preview.playing,true);assert.equal(b.qa.state.editChoice,null);
  b.qa.stopEditorialPreview(true);assert.equal(b.qa.state.preview.playing,false);assert.equal(b.qa.state.preview.timer,null);
  b.qa.startEditorialPreview('words_lead');assert.equal(b.qa.state.preview.directionId,'words_lead');assert.equal(b.qa.state.preview.events[0].elapsed_seconds,0);
  b.qa.invalidate();assert.equal(b.qa.state.preview,null);assert.equal(b.element('editorialPreview').hidden,true);
});
test('actual wall-clock frontend callbacks show different image and text entries, without media or a model',async()=>{
  const a=browser({realTimers:true}),b=browser({realTimers:true});await Promise.all([a.qa.renderEditorialWorkbench(),b.qa.renderEditorialWorkbench()]);
  const started=performance.now();a.qa.startEditorialPreview('images_lead');b.qa.startEditorialPreview('words_lead');
  try{
    await new Promise(resolve=>setTimeout(resolve,13900));
    const eventsA=clone(a.qa.state.preview.events),eventsB=clone(b.qa.state.preview.events);
    const nextA=eventsA.find(e=>e.shot_id==='shot_02'),nextB=eventsB.find(e=>e.shot_id==='shot_02');
    assert.ok(nextA && nextB);assert.ok(nextB.elapsed_seconds<nextA.elapsed_seconds);
    assert.equal(eventsA[0].event,'image_or_caption_cue');assert.equal(eventsB[0].event,'voice_text_cue');
    assert.ok(eventsA.some(e=>e.shot_id==='shot_01' && e.event==='voice_text_cue' && e.elapsed_seconds>=1));
    console.log('EDITORIAL_CHRONOLOGY_RECEIPT '+JSON.stringify({kind:'actual_wall_clock_frontend_callbacks_isolated_DOM_not_rendered_browser',source:'synthetic_gardening_38_second_control',observed_elapsed_seconds:Math.round((performance.now()-started)/10)/100,images_lead_events:eventsA,words_lead_events:eventsB,no_audio_video_network_or_model:true}));
  }finally{a.qa.stopEditorialPreview(false);b.qa.stopEditorialPreview(false);}
});

function silentCase(){
  const source=gardeningSource();source.brief.shots[0].on_screen_text='A small beginning';
  const raw=JSON.stringify(source),draft=work.createSilentDraft(source,{source_sha256:hash(raw),display_kind:'fixture'});
  return{source,raw,draft};
}
test('silent adaptation exposes words carried by narration and transfers actual text without changing the parent',()=>{
  const {source,raw,draft}=silentCase();assert.equal(draft.shots[0].transfer.spoken_word_sequence_not_on_screen,true);
  assert.equal(draft.shots[0].on_screen_text,'A small beginning\nStart with a seed.');
  assert.equal(draft.local_delivery_constraint.sound_off,true);assert.equal(source.brief.user_constraints.sound_off,false);
  assert.equal(JSON.stringify(source),raw);for(const shot of draft.shots){assert.equal(shot.voiceover,'');assert.equal(shot.sonic_direction,'');}
});
test('silent author correction and decision have their own reproducible hash, exact text and no inherited native verdict',async()=>{
  const {source,raw,draft}=silentCase(),text='  My author correction.\nKeep this line exactly.  ';
  work.setSilentCaption(draft,source,'shot_01',text);
  const artifact=await work.finalizeSilentDraft(draft,source,raw,'accept','Reason, exactly.','2026-10-23T15:00:00Z');
  assert.equal(artifact.payload.shots[0].on_screen_text,text);assert.equal(artifact.payload.shots[0].text_origin,'author_free_edit_unverified');
  assert.equal(artifact.payload.parent.document_sha256,hash(raw));assert.equal(artifact.parent_original_export_utf8,raw);
  assert.equal(hash(work.canonicalJSON(artifact.payload)),artifact.payload_sha256);assert.equal(artifact.derived_id,'local-silent-'+artifact.payload_sha256);
  assert.equal(artifact.payload.variant_verification.native_status,'not_executed');assert.equal(artifact.payload.variant_verification.canon_spoiler_status,'not_verified');
  assert.equal(artifact.payload.local_checks.canon_spoilers_and_understandability,'not_verified');
  assert.equal('verification' in artifact.payload,false);assert.equal('qloo_api_verified' in artifact.payload,false);assert.equal('user_constraints' in artifact.payload,false);
  assert.equal(artifact.parent_original_document.brief.verification.llm_status,'accept');assert.equal(artifact.parent_original_document.brief.user_constraints.sound_off,false);
});
test('silent optional metadata omission keeps the downloaded payload hash reproducible',async()=>{
  const source=gardeningSource();delete source.director_version;for(const shot of source.brief.shots)delete shot.aspect_ratio;
  const raw=JSON.stringify(source),draft=work.createSilentDraft(source,{source_sha256:hash(raw),display_kind:'fixture'});
  const artifact=await work.finalizeSilentDraft(draft,source,raw,'accept');const downloaded=JSON.parse(JSON.stringify(artifact));
  assert.equal('director_version' in downloaded.payload.parent,false);assert.equal('aspect_ratio' in downloaded.payload.shots[0],false);
  assert.equal(hash(work.canonicalJSON(downloaded.payload)),artifact.payload_sha256);assert.equal(artifact.derived_id,'local-silent-'+artifact.payload_sha256);
  assert.equal(work.canonicalJSON({missing:undefined,array:[undefined,2],present:1}),' {"array":[null,2],"present":1}'.trim());
  assert.match(artifact.identity_method,/not RFC8785/);assert.equal(JSON.stringify(source),raw);
});
test('silent missing text prevents local acceptance, while rejection preserves the exact unresolved draft',async()=>{
  const {source,raw,draft}=silentCase();work.setSilentCaption(draft,source,'shot_01','');
  await assert.rejects(()=>work.finalizeSilentDraft(draft,source,raw,'accept'),/no silent text/);
  const rejected=await work.finalizeSilentDraft(draft,source,raw,'reject','This needs reconstruction.');
  assert.equal(rejected.payload.author_decision.use_adaptation,false);assert.equal(rejected.payload.author_decision.status,'reject');
  assert.equal(rejected.payload.shots[0].on_screen_text,'');assert.equal(rejected.payload.local_checks.errors[0].kind,'missing_silent_text');
});
test('silent fixed-timing source keeps every duration and warns rather than inventing extra reading time',async()=>{
  const source=gardeningSource();source.brief.user_constraints.timing_locked=true;const raw=JSON.stringify(source);
  assert.equal(build(source).status,'unavailable');
  const draft=work.createSilentDraft(source,{source_sha256:hash(raw),display_kind:'fixture'});assert.equal(draft.timing_locked_warning,true);
  work.setSilentCaption(draft,source,'shot_01',Array(80).fill('word').join(' '));const artifact=await work.finalizeSilentDraft(draft,source,raw,'accept');
  assert.deepEqual(clone(artifact.payload.shots.map(s=>s.duration_seconds)),[9.5,9.5,9.5,9.5]);
  assert.equal(artifact.payload.local_checks.caption_reading_estimates[0].may_not_fit,true);assert.equal(artifact.payload.variant_verification.understandability_status,'requires_author_review');
});
test('silent parent changes, incorrect original bytes and concurrent corrections fail closed',async()=>{
  let c=silentCase();c.source.brief.synopsis+=' Changed.';
  assert.throws(()=>work.setSilentCaption(c.draft,c.source,'shot_01','New words'),/parent changed/);
  c=silentCase();await assert.rejects(()=>work.finalizeSilentDraft(c.draft,c.source,c.raw+' ','accept'),/bytes\/hash/);
  c=silentCase();let pending=work.finalizeSilentDraft(c.draft,c.source,c.raw,'accept');c.source.brief.synopsis+=' Changed during hash.';await assert.rejects(pending,/parent changed/);
  c=silentCase();pending=work.finalizeSilentDraft(c.draft,c.source,c.raw,'accept');work.setSilentCaption(c.draft,c.source,'shot_01','Changed during hash.');await assert.rejects(pending,/text changed/);
});
test('silent helper refuses changes to image timing, aspect, assets or transfer attribution',()=>{
  for(const mutate of [s=>s.start_seconds=2,s=>s.end_seconds=20,s=>s.aspect_ratio='9:16',s=>s.assets.push('new footage'),s=>s.transfer.proposed_on_screen_text='Invented baseline']){
    const c=silentCase();mutate(c.draft.shots[0]);assert.throws(()=>work.inspectSilentDraft(c.draft,c.source),/draft structure changed/);
  }
});
test('silent frontend correction, acceptance and exact download preserve parent sound mode and free-text attribution',async()=>{
  const source=gardeningSource();source.brief.shots[0].on_screen_text='A beginning';const before=JSON.stringify(source);
  const b=browser({inputSource:source});await b.qa.renderEditorialWorkbench();await b.qa.prepareSilentAdaptation();
  assert.match(b.element('silentShotEditors').innerHTML,/Start with a seed/);
  b.qa.updateSilentCaption('shot_01','Exact author screen text.\nSecond line.');b.element('silentDecisionNote').value='Keep the essential step.';
  await b.qa.decideSilentAdaptation('accept');await b.qa.downloadSilentAdaptation();assert.equal(b.downloads.length,1);
  const artifact=JSON.parse(await b.downloads[0].blob.text());assert.equal(artifact.payload.shots[0].on_screen_text,'Exact author screen text.\nSecond line.');assert.equal(artifact.payload.author_decision.note,'Keep the essential step.');
  assert.equal(artifact.parent_original_export_utf8,b.raw);assert.equal(JSON.stringify(source),before);assert.equal(artifact.payload.variant_verification.native_status,'not_executed');
  b.qa.updateSilentCaption('shot_01','Another local edit.');assert.equal(b.qa.state.silentExport,null);assert.equal(b.element('downloadSilentBtn').disabled,true);await assert.rejects(()=>b.qa.downloadSilentAdaptation(),/Accept or reject/);
});
test('silent frontend can reject and cannot export after a parent change; fixed timing remains adaptable',async()=>{
  const source=gardeningSource();source.brief.user_constraints.timing_locked=true;
  const b=browser({inputSource:source});await b.qa.renderEditorialWorkbench();assert.equal(b.qa.state.editorial.status,'unavailable');
  await b.qa.prepareSilentAdaptation();assert.match(b.element('silentConstraintSummary').textContent,/fixes individual timing/);
  await b.qa.decideSilentAdaptation('reject');await b.qa.downloadSilentAdaptation();assert.equal(JSON.parse(await b.downloads[0].blob.text()).payload.author_decision.status,'reject');
  b.qa.invalidate();assert.equal(b.qa.state.silentDraft,null);assert.equal(b.element('downloadSilentBtn').disabled,true);await assert.rejects(()=>b.qa.downloadSilentAdaptation(),/Accept or reject/);assert.equal(b.downloads.length,1);
});

const localFile=text=>({size:Buffer.byteLength(text),text:async()=>text});
async function savedSilentCase(){
  const c=silentCase();work.setSilentCaption(c.draft,c.source,'shot_02','Exact resumed caption.\nSecond line.');
  c.artifact=await work.finalizeSilentDraft(c.draft,c.source,c.raw,'accept','Exact saved note.','2026-10-23T17:00:00Z');return c;
}
test('silent resume restores only captions and note; a fresh decision is required after a page restart',async()=>{
  const source=gardeningSource(),a=browser({inputSource:source});await a.qa.renderEditorialWorkbench();await a.qa.prepareSilentAdaptation();
  a.qa.updateSilentCaption('shot_02','Exact resumed caption.\nSecond line.');a.element('silentDecisionNote').value='Exact saved note.';
  await a.qa.decideSilentAdaptation('accept');await a.qa.downloadSilentAdaptation();const bytes=await a.downloads[0].blob.text();
  const b=browser({inputSource:source});await b.qa.renderEditorialWorkbench();assert.equal(b.qa.state.silentDraft,null);
  await b.qa.resumeSilentDecisionFile(localFile(bytes));
  assert.equal(b.qa.state.silentDraft.shots[1].on_screen_text,'Exact resumed caption.\nSecond line.');assert.equal(b.element('silentDecisionNote').value,'Exact saved note.');
  assert.equal(b.qa.state.silentExport,null);assert.equal(b.element('downloadSilentBtn').disabled,true);assert.match(b.element('silentStatus').textContent,/UNDECIDED/);
  await assert.rejects(()=>b.qa.downloadSilentAdaptation(),/Accept or reject/);
  await b.qa.decideSilentAdaptation('reject');await b.qa.downloadSilentAdaptation();const resumed=JSON.parse(await b.downloads[0].blob.text());
  assert.equal(resumed.payload.author_decision.status,'reject');assert.equal(resumed.payload.shots[1].on_screen_text,'Exact resumed caption.\nSecond line.');
  assert.equal(resumed.payload.variant_verification.native_status,'not_executed');assert.equal(resumed.parent_original_export_utf8,b.raw);
});
test('silent resume verifies kind identity exact parent and protected fields, even if tampering is rehashed',async()=>{
  const c=await savedSilentCase(),context={source_sha256:hash(c.raw),display_kind:'fixture'};
  for(const mutate of [a=>a.schema='another-export',a=>a.derived_id='local-silent-'+'0'.repeat(64),a=>a.payload.shots[1].on_screen_text='Changed without new hash']){
    const a=clone(c.artifact);mutate(a);await assert.rejects(()=>work.resumeSilentDraft(a,c.source,c.raw,context));
  }
  for(const mutate of [a=>a.payload.shots[1].duration_seconds=11,a=>a.payload.shots[1].assets.push('https://not-fetched.invalid/asset'),a=>a.payload.variant_verification.native_status='accept',a=>a.payload.shots[1].text_origin='native_verified']){
    const a=clone(c.artifact);mutate(a);a.payload_sha256=hash(work.canonicalJSON(a.payload));a.derived_id='local-silent-'+a.payload_sha256;
    await assert.rejects(()=>work.resumeSilentDraft(a,c.source,c.raw,context));
  }
  await assert.rejects(()=>work.resumeSilentDraft(c.artifact,c.source,c.raw+' ',{...context,source_sha256:hash(c.raw+' ')}),/different parent bytes/);
  const changed=clone(c.source);changed.brief.synopsis+=' Different parent.';const changedRaw=JSON.stringify(changed);
  await assert.rejects(()=>work.resumeSilentDraft(c.artifact,changed,changedRaw,{...context,source_sha256:hash(changedRaw)}),/different parent bytes/);
});
test('silent resume invalid oversized or wrong-parent files leave the existing draft and decision intact',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();await b.qa.prepareSilentAdaptation();b.qa.updateSilentCaption('shot_01','Current work must survive.');b.element('silentDecisionNote').value='Current note.';await b.qa.decideSilentAdaptation('reject');
  const before=JSON.stringify(b.qa.state.silentDraft),decision=b.qa.state.silentExport,attempt=b.qa.state.silentAttempt;
  const c=await savedSilentCase(),bad=clone(c.artifact);bad.derived_id='bad';
  for(const file of [localFile('{bad json'),localFile(JSON.stringify(bad)),localFile(JSON.stringify(c.artifact)),{size:1048577,text(){throw Error('Oversized file must not be read.');}}]){
    await assert.rejects(()=>b.qa.resumeSilentDecisionFile(file));
    assert.equal(JSON.stringify(b.qa.state.silentDraft),before);assert.equal(b.qa.state.silentExport,decision);assert.equal(b.qa.state.silentAttempt,attempt);assert.equal(b.element('silentDecisionNote').value,'Current note.');assert.equal(b.element('downloadSilentBtn').disabled,false);
  }
  b.qa.silentImportFailure(Error('Refused test input.'));assert.equal(b.qa.state.silentExport,decision);assert.match(b.element('silentStatus').textContent,/not replaced/);
});
test('silent resume preserves rejected missing text and optional metadata without importing authority or markup',async()=>{
  const c=silentCase();delete c.source.director_version;for(const s of c.source.brief.shots)delete s.aspect_ratio;
  const raw=JSON.stringify(c.source),context={source_sha256:hash(raw),display_kind:'fixture'},draft=work.createSilentDraft(c.source,context);
  work.setSilentCaption(draft,c.source,'shot_02','');const artifact=await work.finalizeSilentDraft(draft,c.source,raw,'reject','<img src=x onerror=alert(1)>');
  const b=browser({inputSource:c.source});await b.qa.renderEditorialWorkbench();await b.qa.resumeSilentDecisionFile(localFile(JSON.stringify(artifact)));
  assert.equal(b.qa.state.silentDraft.shots[1].on_screen_text,'');assert.equal(b.element('silentDecisionNote').value,'<img src=x onerror=alert(1)>');assert.equal(b.element('downloadSilentBtn').disabled,true);
  await assert.rejects(()=>b.qa.decideSilentAdaptation('accept'),/no silent text/);
  await b.qa.decideSilentAdaptation('reject');await b.qa.downloadSilentAdaptation();assert.equal(JSON.parse(await b.downloads[0].blob.text()).payload.variant_verification.native_status,'not_executed');
});
test('silent resume refuses to overwrite a correction made while the selected file is being read',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();await b.qa.prepareSilentAdaptation();await b.qa.decideSilentAdaptation('accept');await b.qa.downloadSilentAdaptation();const bytes=await b.downloads[0].blob.text();
  let release;const file={size:Buffer.byteLength(bytes),text:()=>new Promise(resolve=>{release=()=>resolve(bytes);})};
  const pending=b.qa.resumeSilentDecisionFile(file);b.qa.updateSilentCaption('shot_02','Newer current edit.');release();
  await assert.rejects(pending,/changed during import/);assert.equal(b.qa.state.silentDraft.shots[1].on_screen_text,'Newer current edit.');assert.equal(b.element('downloadSilentBtn').disabled,true);
});

function amendmentCase(){
  const source=gardeningSource(),raw=JSON.stringify(source);
  return{source,raw,draft:work.createShotAmendment(source,{source_sha256:hash(raw),display_kind:'fixture'},'shot_02')};
}
test('single-shot amendment exports exact four-field production texts with parent authority separate',async()=>{
  const c=amendmentCase(),texts={visual_prompt:'An unmarked pot beside its label.',voiceover:'Choose a name before writing it.',on_screen_text:'Which herb will grow here?',sonic_direction:'Quiet room, no music.'};
  work.setShotAmendment(c.draft,c.source,'intention','Keep the planting choice open.');
  for(const [field,text] of Object.entries(texts))work.setShotAmendment(c.draft,c.source,field,text);
  const a=await work.finalizeShotAmendment(c.draft,c.source,c.raw,'amendment','2026-10-26T01:00:00Z');
  assert.equal(a.schema,'local-shot-amendment-v1');assert.equal(a.parent_original_export_utf8,c.raw);assert.equal(JSON.stringify(c.source),c.raw);
  assert.equal(a.payload.parent.document_sha256,hash(c.raw));assert.equal(a.payload.amended_shot_id,'shot_02');
  assert.equal(a.payload.author_decision.intention,'Keep the planting choice open.');
  assert.equal(a.payload.proposed_storyboard.shots.length,4);assert.deepEqual(clone(a.payload.selected_storyboard),clone(a.payload.proposed_storyboard));
  for(let i=0;i<4;i++){
    const shot=a.payload.selected_storyboard.shots[i],parent=c.source.brief.shots[i];
    assert.equal(shot.id,parent.id);assert.equal(shot.duration_seconds,parent.duration_seconds);assert.equal(shot.aspect_ratio,parent.aspect_ratio);
    for(const field of Object.keys(texts))assert.equal(shot[field],i===1?texts[field]:parent[field]);
    for(const field of ['purpose','verification','qloo_api_verified','decision_refs','evidence_refs','retained_entity_refs','interpretation_labels','generation_origin','line_status'])assert.equal(field in shot,false);
  }
  assert.equal(a.payload.review_status.native_status,'not_executed');assert.equal(a.payload.review_status.constraints_status,'requires_author_review');
  assert.equal('verification' in a.payload,false);assert.equal('qloo_api_verified' in a.payload,false);
  assert.equal(hash(work.canonicalJSON(a.payload)),a.payload_sha256);assert.equal(a.derived_id,'local-shot-amendment-'+a.payload_sha256);
  assert.equal(a.parent_original_document.brief.verification.llm_status,'accept');
});
test('single-shot amendment requires intention and explicit choice; original and neither remain valid',async()=>{
  const c=amendmentCase();await assert.rejects(()=>work.finalizeShotAmendment(c.draft,c.source,c.raw,'original'),/intention/);
  work.setShotAmendment(c.draft,c.source,'intention','Retain the practical sequence.');
  await assert.rejects(()=>work.finalizeShotAmendment(c.draft,c.source,c.raw,'automatic'),/Choose/);
  await assert.rejects(()=>work.finalizeShotAmendment(c.draft,c.source,c.raw,'amendment'),/change/);
  work.setShotAmendment(c.draft,c.source,'on_screen_text','An alternative label.');
  const original=await work.finalizeShotAmendment(c.draft,c.source,c.raw,'original');
  assert.equal(original.payload.selected_storyboard.shots[1].on_screen_text,c.source.brief.shots[1].on_screen_text);
  assert.equal(original.payload.proposed_storyboard.shots[1].on_screen_text,'An alternative label.');
  const neither=await work.finalizeShotAmendment(c.draft,c.source,c.raw,'neither');
  assert.equal(neither.payload.selected_storyboard,null);assert.equal(neither.payload.author_decision.adopts_storyboard,false);
  assert.equal(neither.payload.proposed_storyboard.shots.length,4);
});
test('single-shot amendment binds source bytes and revision and rejects protected or asynchronous changes',async()=>{
  let c=amendmentCase();work.setShotAmendment(c.draft,c.source,'intention','Keep the label undecided.');
  assert.throws(()=>work.setShotAmendment(c.draft,c.source,'duration_seconds','12'),/field/);
  await assert.rejects(()=>work.finalizeShotAmendment(c.draft,c.source,c.raw+' ','original'),/bytes|hash/);
  c.draft.shot_id='shot_03';assert.throws(()=>work.inspectShotAmendment(c.draft,c.source),/draft changed/);
  c=amendmentCase();work.setShotAmendment(c.draft,c.source,'intention','Keep the label undecided.');
  let pending=work.finalizeShotAmendment(c.draft,c.source,c.raw,'original');work.setShotAmendment(c.draft,c.source,'voiceover','A newer correction.');
  await assert.rejects(pending,/changed/);
  c=amendmentCase();work.setShotAmendment(c.draft,c.source,'intention','Keep the label undecided.');
  pending=work.finalizeShotAmendment(c.draft,c.source,c.raw,'original');c.source.brief.shots[2].duration_seconds=12;
  await assert.rejects(pending,/parent changed/);
});
test('single-shot amendment frontend compares and downloads one exact correction then invalidates every new edit or parent',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();b.element('amendmentShotSelect').value='shot_02';b.qa.prepareShotAmendment();
  assert.match(b.element('amendmentComparison').innerHTML,/Received original/);assert.match(b.element('amendmentComparison').innerHTML,/Local author draft/);
  b.qa.updateShotAmendment('intention','Keep the planting choice open.');b.qa.updateShotAmendment('visual_prompt','A blank label beside the pot.');
  await b.qa.decideShotAmendment('amendment');await b.qa.downloadShotAmendment();
  assert.equal(b.downloads.length,1);const a=JSON.parse(await b.downloads[0].blob.text());assert.equal(a.payload.selected_storyboard.shots[1].visual_prompt,'A blank label beside the pot.');
  assert.equal(a.parent_original_export_utf8,b.raw);
  b.qa.updateShotAmendment('intention','Leave the choice to the reader.');assert.equal(b.qa.state.amendmentExport,null);assert.equal(b.element('downloadAmendmentBtn').disabled,true);
  await assert.rejects(()=>b.qa.downloadShotAmendment(),/Choose/);
  await b.qa.decideShotAmendment('original');b.element('amendmentShotSelect').value='shot_03';b.qa.prepareShotAmendment();
  assert.equal(b.qa.state.amendmentDraft.shot_id,'shot_03');assert.equal(b.qa.state.amendmentExport,null);assert.equal(b.qa.state.amendmentDraft.intention,'');
  b.qa.updateShotAmendment('intention','Keep the watering step.');await b.qa.decideShotAmendment('neither');
  const pending=b.qa.downloadShotAmendment();b.qa.invalidate();await assert.rejects(pending,/changed/);
  assert.equal(b.downloads.length,1);assert.equal(b.qa.state.amendmentDraft,null);
});
test('single-shot amendment frontend refuses an old async decision after another edit',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();b.element('amendmentShotSelect').value='shot_01';b.qa.prepareShotAmendment();
  b.qa.updateShotAmendment('intention','Keep the first step clear.');
  const pending=b.qa.decideShotAmendment('original');b.qa.updateShotAmendment('on_screen_text','Newer first step.');
  await assert.rejects(pending,/changed/);assert.equal(b.qa.state.amendmentExport,null);assert.equal(b.element('downloadAmendmentBtn').disabled,true);
});
test('single-shot amendment real click handler preserves a newer decision when an older hash rejects late',async()=>{
  let holdNext=false,release;
  const crypto={subtle:{digest(...args){
    if(holdNext){holdNext=false;return new Promise(resolve=>{release=()=>webcrypto.subtle.digest(...args).then(resolve);});}
    return webcrypto.subtle.digest(...args);
  }}};
  const b=browser({crypto});await b.qa.renderEditorialWorkbench();b.element('amendmentShotSelect').value='shot_01';b.element('prepareAmendmentBtn').listeners.click();
  b.qa.updateShotAmendment('intention','Keep the first step clear.');
  holdNext=true;const olderClick=b.element('chooseOriginalBtn').listeners.click();assert.equal(typeof release,'function');
  b.qa.updateShotAmendment('on_screen_text','Newer first step.');await b.element('chooseAmendmentBtn').listeners.click();
  const newer=b.qa.state.amendmentExport,status=b.element('amendmentStatus').textContent;
  assert.equal(newer.payload.author_decision.choice,'amendment');assert.equal(b.element('downloadAmendmentBtn').disabled,false);
  await release();await olderClick;
  assert.equal(b.qa.state.amendmentExport,newer);assert.equal(b.element('downloadAmendmentBtn').disabled,false);assert.equal(b.element('amendmentStatus').textContent,status);
  holdNext=true;const olderDownload=b.element('downloadAmendmentBtn').listeners.click();
  b.qa.updateShotAmendment('on_screen_text','A still newer first step.');await b.element('chooseOriginalBtn').listeners.click();
  const latest=b.qa.state.amendmentExport,latestStatus=b.element('amendmentStatus').textContent;
  await release();await olderDownload;
  assert.equal(b.qa.state.amendmentExport,latest);assert.equal(b.element('downloadAmendmentBtn').disabled,false);assert.equal(b.element('amendmentStatus').textContent,latestStatus);assert.equal(b.downloads.length,0);
  b.qa.updateShotAmendment('intention','');await b.element('chooseOriginalBtn').listeners.click();
  assert.equal(b.qa.state.amendmentExport,null);assert.equal(b.element('downloadAmendmentBtn').disabled,true);assert.match(b.element('amendmentStatus').textContent,/intention/);
});
test('same-shot Compare listener preserves the exact draft and decision; another shot or parent starts undecided',async()=>{
  const b=browser();await b.qa.renderEditorialWorkbench();const source=b.qa.state.bundle;
  let focusCount=0;b.element('amendmentIntention').focus=()=>{focusCount++;};
  b.element('amendmentShotSelect').value='shot_02';b.element('prepareAmendmentBtn').listeners.click();
  const intention='Keep the planting choice open.',texts={visual_prompt:'An unmarked pot beside a blank label.',voiceover:'Which herb belongs here?',on_screen_text:'A choice still open.',sonic_direction:'Quiet room. No contact sound.'};
  b.element('amendmentIntention').value=intention;b.element('amendmentIntention').listeners.input({target:b.element('amendmentIntention')});
  for(const [field,text] of Object.entries(texts)){
    const input=b.element('amendmentText-'+field);input.value=text;input.dataset={amendmentField:field};b.element('amendmentComparison').listeners.input({target:input});
  }
  await b.element('chooseAmendmentBtn').listeners.click();await b.element('downloadAmendmentBtn').listeners.click();
  const draft=b.qa.state.amendmentDraft,before=JSON.stringify(draft),artifact=b.qa.state.amendmentExport,attempt=b.qa.state.amendmentAttempt,exportRevision=b.qa.state.amendmentExportRevision;
  const status=b.element('amendmentStatus').textContent,comparison=b.element('amendmentComparison').innerHTML,focusBefore=focusCount,bytes=await b.downloads[0].blob.text();
  b.element('prepareAmendmentBtn').listeners.click();
  assert.equal(b.qa.state.amendmentDraft,draft);assert.equal(JSON.stringify(b.qa.state.amendmentDraft),before);assert.equal(b.qa.state.amendmentExport,artifact);
  assert.equal(b.qa.state.amendmentAttempt,attempt);assert.equal(b.qa.state.amendmentExportRevision,exportRevision);assert.equal(b.element('downloadAmendmentBtn').disabled,false);
  assert.equal(b.element('amendmentStatus').textContent,status);assert.equal(b.element('amendmentComparison').innerHTML,comparison);assert.equal(b.element('amendmentIntention').value,intention);assert.equal(focusCount,focusBefore+1);
  for(const [field,text] of Object.entries(texts))assert.equal(b.element('amendmentText-'+field).value,text);
  await b.element('downloadAmendmentBtn').listeners.click();assert.equal(await b.downloads[1].blob.text(),bytes);
  b.element('amendmentShotSelect').value='shot_03';b.element('amendmentShotSelect').listeners.change();
  assert.notEqual(b.qa.state.amendmentDraft,draft);assert.equal(b.qa.state.amendmentDraft.shot_id,'shot_03');assert.equal(b.qa.state.amendmentDraft.intention,'');assert.equal(b.qa.state.amendmentDraft.revision,0);assert.equal(b.qa.state.amendmentExport,null);assert.equal(b.element('downloadAmendmentBtn').disabled,true);
  const replacement=gardeningSource();replacement.brief.synopsis+=' This is a different brief with the same synthetic run ID.';
  b.qa.state.bundle=replacement;b.qa.state.recording={originalRaw:JSON.stringify(replacement),manifest:{captured_at:'2026-10-20T13:41:27Z'}};
  await b.qa.renderEditorialWorkbench();assert.equal(b.qa.state.amendmentDraft,null);
  b.element('amendmentShotSelect').value='shot_02';b.element('prepareAmendmentBtn').listeners.click();
  assert.equal(b.qa.state.amendmentDraft.shot_id,'shot_02');assert.equal(b.qa.state.amendmentDraft.intention,'');assert.equal(b.qa.state.amendmentDraft.revision,0);assert.equal(b.qa.state.amendmentExport,null);
  assert.notEqual(b.qa.state.amendmentDraft.parent.document_sha256,artifact.payload.parent.document_sha256);assert.equal(JSON.stringify(source),b.raw);
});
