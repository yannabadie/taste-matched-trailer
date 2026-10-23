// Read a private dated archive, exercise the delivered editor and write private receipts.
// No network, provider, native model, credential, budget or runtime operation exists here.
import fs from 'node:fs';
import path from 'node:path';
import {createHash,webcrypto} from 'node:crypto';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const args=Object.fromEntries(process.argv.slice(2).reduce((rows,item,i,list)=>i%2?rows:rows.concat([[item,list[i+1]]]),[]));
if(!args['--archive'] || !args['--manifest'] || !args['--out'])throw Error('Use --archive PRIVATE_ARCHIVE --manifest PRIVATE_MANIFEST --out PRIVATE_OUTPUT_DIRECTORY');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),out=path.resolve(args['--out']);
if(out===root || out.startsWith(root+path.sep))throw Error('Authentic response data must stay outside the public checkout.');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const archiveBytes=fs.readFileSync(args['--archive']),manifestBytes=fs.readFileSync(args['--manifest']);
const manifest=JSON.parse(manifestBytes),archive=JSON.parse(archiveBytes),pins=JSON.parse(fs.readFileSync(path.join(root,'runtime/SOURCE-PINS.json'))).recorded_capture;
if(hash(archiveBytes)!==pins.archive_sha256 || hash(manifestBytes)!==pins.manifest_sha256)throw Error('Archive/manifest differ from the preserved source pins.');
const original=manifest.original_export,originalBytes=archiveBytes.subarray(original.byte_offset_in_archive,original.byte_offset_in_archive+original.bytes);
if(hash(originalBytes)!==pins.original_export_sha256 || originalBytes.length!==original.bytes)throw Error('The original UTF-8 export failed its pinned integrity check.');
const raw=originalBytes.toString('utf8'),source=JSON.parse(raw);
if(JSON.stringify(source)!==JSON.stringify(archive.document))throw Error('The original bytes and archived document disagree.');
const core=fs.readFileSync(path.join(root,'editorial-workbench.js'),'utf8'),sandbox=vm.createContext({crypto:webcrypto,TextEncoder});
vm.runInContext(core+';globalThis.work=EditorialWorkbench;',sandbox);const work=sandbox.work;
const result=work.build(source,{source_sha256:hash(originalBytes),display_kind:'recorded',captured_at:archive.captured_at});
if(result.status!=='ready_for_author_choice')throw Error('The received source cannot support these alternatives: '+result.reason);
fs.mkdirSync(out,{recursive:true});
const write=(name,value)=>fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2)+'\n');
write('local-editorial-options.json',result);
for(const choice of ['images_lead','words_lead','tie','neither'])write('scripted-export-'+choice+'.json',{
  ...work.choose(result,source,choice,'Scripted export reception only — not author feedback.',new Date().toISOString(),raw),
  scripted_technical_reception_not_author_preference:true});
const silent=work.createSilentDraft(source,{source_sha256:hash(originalBytes),display_kind:'recorded',captured_at:archive.captured_at});
write('local-silent-draft.json',{draft:silent,local_checks:work.inspectSilentDraft(silent,source),scripted_technical_reception_not_author_feedback:true});
// A controlled local edit uses only the two actual source strings, in a different order.
const editedId=silent.shots[0].id,editedText=[source.brief.shots[0].voiceover,source.brief.shots[0].on_screen_text].filter(Boolean).join('\n');
work.setSilentCaption(silent,source,editedId,editedText);
const silentDecisions=[];
for(const decision of ['accept','reject']){
  const artifact=await work.finalizeSilentDraft(silent,source,raw,decision,'Scripted technical reception only; not author validation.',new Date().toISOString());
  write('scripted-silent-'+decision+'.json',{...artifact,scripted_technical_reception_not_author_feedback:true});
  silentDecisions.push({decision,derived_id:artifact.derived_id,payload_sha256:artifact.payload_sha256,corrected_shot:editedId,exact_corrected_text:editedText,native_variant_verification:artifact.payload.variant_verification});
}
const preserved=result.directions.every(d=>d.shots.every((s,i)=>s.visual_prompt===source.brief.shots[i].visual_prompt && s.voiceover===source.brief.shots[i].voiceover && JSON.stringify(s.evidence_refs)===JSON.stringify(source.brief.shots[i].evidence_refs) && JSON.stringify(s.retained_entity_refs)===JSON.stringify(source.brief.shots[i].retained_entity_refs)));
if(!preserved)throw Error('A source image, story word or evidence binding changed.');
let html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const literal=value=>JSON.stringify(value).replaceAll('<','\\u003c');
const startup=`loadPreset();state.bundle=${literal(source)};state.snapshot=snapshot();state.displayKind='recorded';state.recording={originalRaw:${literal(raw)},manifest:${literal(manifest)},apiBase:RECORDING_ORIGIN};state.configurationReady=false;state.apiBase=null;renderBundle();$('connectionStatus').textContent='OFFLINE REPLAY: network disabled. A dated source was injected by the local receipt tool; no new live request is possible.';$('recordingStatus').textContent='OFFLINE TECHNICAL RECEPTION · original run ${source.run_id} · ${source.brief.created_at}. Local edits are newly calculated, original model output remains dated.';`;
if(!html.includes('loadPreset();restorePending();loadConfiguration();viewRecording();'))throw Error('Frontend startup changed; inspect the replay adapter.');
html=html.replace('loadPreset();restorePending();loadConfiguration();viewRecording();',startup);
html=html.replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; connect-src \'none\'; img-src data:; media-src \'none\'">');
html=html.replace('<body>','<body><p class="status warn" style="margin:1rem">OFFLINE REPLAY · dated genuine source; newly computed local editing proposals. No new Qloo/model call, no received video or author feedback.</p>');
fs.writeFileSync(path.join(out,'OFFLINE-REPLAY.html'),html);
const receipt={status:'OFFLINE_EDITING_DELTA_RECEIVED',observed_at:new Date().toISOString(),
  original_run_id:source.run_id,original_created_at:source.brief.created_at,original_export_sha256:hash(originalBytes),original_export_bytes:originalBytes.length,
  editor_sha256:hash(core),frontend_sha256:hash(fs.readFileSync(path.join(root,'index.html'))),
  new_qloo_requests:0,new_model_calls:0,run_families_reserved:0,no_runtime_or_budget_mutation:true,
  original_run_counters_are_historical:source.run_budget,
  original_shot_durations:source.brief.shots.map(s=>s.duration_seconds),
  alternatives:result.directions.map(d=>({id:d.id,durations:d.shots.map(s=>s.duration_seconds),voice_start_seconds:d.shots.map(s=>s.editorial_delivery.voice_start_seconds),total:d.total_duration_seconds,readiness:d.readiness,warnings:d.warnings})),
  silent_adaptation:{parent_native_sound_off:source.brief.user_constraints.sound_off,parent_native_constraints_unchanged:JSON.stringify(source.brief.user_constraints)===JSON.stringify(JSON.parse(raw).brief.user_constraints),local_constraint_sound_off:true,original_timing_retained:true,
    shots_with_spoken_word_sequence_not_on_screen:silent.shots.filter(s=>s.transfer.spoken_word_sequence_not_on_screen).map(s=>s.id),decisions:silentDecisions},
  visual_prompts_story_words_and_reference_bindings_preserved:preserved,
  same_synopsis_constraints_spoilers_and_offscreen_rule:true,unchanged_shot_order:true,
  limitations:['Two local deterministic edits of one dated native output, not two new Qloo/Qwen generations.','The timing heuristics are not received audio or video.','The scripted exports are not author preferences or a comparative quality result.','The native verifier accepted the original result, not the recompositions.']};
write('REPLAY-RECEIPT.json',receipt);console.log(JSON.stringify(receipt,null,2));
