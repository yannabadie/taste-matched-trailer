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

function browser({realTimers=false,inputSource=null}={}){
  const elements=new Map(),downloads=[],blobs=new Map();
  const element=id=>elements.get(id)||elements.set(id,{id,value:'',checked:false,hidden:false,disabled:false,innerHTML:'',textContent:'',className:'',addEventListener(){},appendChild(){}}).get(id);
  const document={getElementById:element,querySelector(){return document.selected || null;},addEventListener(){},body:{appendChild(){}},createElement(){return{remove(){},click(){downloads.push({filename:this.download,blob:blobs.get(this.href)});}};}};
  class LocalURL extends URL{static createObjectURL(blob){const id='blob:test-'+blobs.size;blobs.set(id,blob);return id;}static revokeObjectURL(){}}
  const window={document,location:{origin:'http://localhost',href:'http://localhost/index.html'},addEventListener(){}};
  const context=vm.createContext({document,window,crypto:webcrypto,TextEncoder,TextDecoder,Blob,URL:LocalURL,AbortController,setTimeout(){},setInterval:realTimers?setInterval:()=>1,clearInterval:realTimers?clearInterval:()=>{},performance:realTimers?performance:{now:()=>0},console});
  const html=fs.readFileSync(new URL('index.html',root),'utf8');let script=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
  script=script.replace('loadPreset();restorePending();loadConfiguration();viewRecording();','');
  vm.runInContext(script+';globalThis.qa={state,snapshot,renderEditorialWorkbench,chooseEditorialOption,downloadEditorialDecision,invalidate,startEditorialPreview,stopEditorialPreview,prepareSilentAdaptation,updateSilentCaption,decideSilentAdaptation,downloadSilentAdaptation,invalidateSilentDecision};',context);
  const source=inputSource || gardeningSource(),raw=JSON.stringify(source);Object.assign(context.qa.state,{bundle:source,displayKind:'recorded',recording:{originalRaw:raw,manifest:{captured_at:'2026-10-20T13:41:27Z'}}});context.qa.state.snapshot=context.qa.snapshot();
  return{qa:context.qa,document,element,downloads,raw};
}
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
