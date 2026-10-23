import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import {gardeningSource} from './editorial-fixture.mjs';

const root=new URL('../',import.meta.url),core=fs.readFileSync(new URL('editorial-workbench.js',root),'utf8');
const sandbox=vm.createContext({});vm.runInContext(core+';globalThis.work=EditorialWorkbench;',sandbox);const work=sandbox.work;
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

function browser(){
  const elements=new Map(),downloads=[],blobs=new Map();
  const element=id=>elements.get(id)||elements.set(id,{id,value:'',checked:false,hidden:false,disabled:false,innerHTML:'',textContent:'',className:'',addEventListener(){},appendChild(){}}).get(id);
  const document={getElementById:element,querySelector(){return document.selected || null;},addEventListener(){},body:{appendChild(){}},createElement(){return{remove(){},click(){downloads.push({filename:this.download,blob:blobs.get(this.href)});}};}};
  class LocalURL extends URL{static createObjectURL(blob){const id='blob:test-'+blobs.size;blobs.set(id,blob);return id;}static revokeObjectURL(){}}
  const window={document,location:{origin:'http://localhost',href:'http://localhost/index.html'},addEventListener(){}};
  const context=vm.createContext({document,window,crypto:webcrypto,TextEncoder,TextDecoder,Blob,URL:LocalURL,AbortController,setTimeout(){},console});
  const html=fs.readFileSync(new URL('index.html',root),'utf8');let script=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
  script=script.replace('loadPreset();restorePending();loadConfiguration();viewRecording();','');
  vm.runInContext(script+';globalThis.qa={state,snapshot,renderEditorialWorkbench,chooseEditorialOption,downloadEditorialDecision,invalidate};',context);
  const source=gardeningSource(),raw=JSON.stringify(source);Object.assign(context.qa.state,{bundle:source,displayKind:'recorded',recording:{originalRaw:raw,manifest:{captured_at:'2026-10-20T13:41:27Z'}}});context.qa.state.snapshot=context.qa.snapshot();
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
