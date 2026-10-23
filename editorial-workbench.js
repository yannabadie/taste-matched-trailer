/* EDITORIAL_WORKBENCH_START */
// A local edit decision over received material, not another Qloo/model result.
const EditorialWorkbench = (() => {
  const sourceBindings = new WeakMap();
  const silentBindings = new WeakMap();
  const copy = value => JSON.parse(JSON.stringify(value));
  const words = value => String(value || '').trim().split(/\s+/u).filter(Boolean).length;
  const fail = reason => ({status:'unavailable', reason, directions:[]});
  const profiles = [
    {id:'images_lead', title:'Let the images lead', weights:[34,29,22,15],
      intent:'Give the opening images more time; let the received words enter after the image.',
      voice:'Leave the opening beat unspoken, then read only the received narration. No additional line or character.', delay:1},
    {id:'words_lead', title:'Let the words lead', weights:[18,22,28,32],
      intent:'Start with the received words; build toward longer later beats without changing the story order.',
      voice:'Begin the received narration on the cut. Use a measured, direct reading; no added explanation or claim.', delay:0}
  ];
  function allocate(total, weights) {
    const ticks = Math.round(total * 100), minimum = 100;
    if(ticks < minimum * 4) throw Error('At least four seconds are required.');
    const remaining = ticks - minimum * 4;
    const lengths = weights.map(weight => minimum + Math.floor(remaining * weight / 100));
    for(let n=0;lengths.reduce((a,b)=>a+b,0)<ticks;n++) lengths[n%4]++;
    return lengths.map(value => value/100);
  }
  function build(source, context) {
    if(!context || !/^[a-f0-9]{64}$/.test(context.source_sha256 || '')) return fail('A hash of the received source bytes is required.');
    if(!['recorded','live','recovered','fixture'].includes(context.display_kind)) return fail('Identify this as a dated recording, received live result or synthetic fixture.');
    const brief=source && source.brief, shots=brief && brief.shots, constraints=brief && brief.user_constraints;
    if(!brief || source.workflow_status!=='ok' || brief.completeness!=='complete' || !Array.isArray(shots) || shots.length!==4 || !constraints || typeof constraints!=='object') return fail('A complete, accepted four-shot source is needed. Failed or incomplete results cannot become edit options.');
    if(source.mode!=='fixture' && source.qloo_api_verified!==true) return fail('The source does not carry verified Qloo evidence.');
    if(Object.keys(source.gate_reasons || {}).length || brief.verification?.deterministic_status!=='pass' || brief.verification?.llm_status!=='accept') return fail('Resolve the source result’s coverage or review reasons first.');
    if(constraints.timing_locked || constraints.fixed_shot_durations || constraints.shot_durations) return fail('This brief fixes individual shot timing. These pacing alternatives would violate it; keep the original timing.');
    if(new Set(shots.map(s=>s.id)).size!==4 || shots.some(s=>s.line_status!=='active' || typeof s.visual_prompt!=='string' || !s.visual_prompt.trim() || !Number.isFinite(s.duration_seconds) || s.duration_seconds<=0)) return fail('Each source shot must be active, complete and have a finite positive duration.');
    const total=shots.reduce((sum,s)=>sum+s.duration_seconds,0);
    if(!Number.isFinite(total) || total<4 || total>300 || Math.abs(total-(brief.total_duration_seconds ?? total))>.011 || (constraints.duration_seconds!==undefined && Math.abs(total-constraints.duration_seconds)>.011)) return fail('The received total and duration constraint disagree. Resolve the source timing before recomposing it.');
    const silent=constraints.sound_off===true;
    if(!shots.some(s=>String(s.on_screen_text || s.voiceover || '').trim())) return fail('There are no received words to build a words-led alternative. Add an author-approved text first; this tool will not invent it.');
    const directions=profiles.map(profile=>{
      const durations=allocate(total,profile.weights); let cursor=0; const warnings=[];
      const edited=shots.map((shot,i)=>{
        const duration=durations[i], start=cursor; cursor=Math.round((cursor+duration)*100)/100;
        const caption=String(shot.on_screen_text || (silent ? shot.voiceover || '' : ''));
        const voiceover=silent?'':String(shot.voiceover || '');
        const delay=!silent && voiceover ? Math.min(profile.delay,duration/4) : 0;
        const available=Math.max(.01,duration-delay);
        const voiceEstimate=words(voiceover)/2.5, captionEstimate=words(caption)/3;
        if(voiceEstimate>available || captionEstimate>duration) warnings.push({shot_id:shot.id,kind:'text_may_not_fit',voice_seconds_estimate:Math.round(voiceEstimate*100)/100,voice_seconds_available:Math.round(available*100)/100,caption_seconds_estimate:Math.round(captionEstimate*100)/100,duration_seconds:duration});
        return {...copy(shot), source_shot_id:shot.id, source_duration_seconds:shot.duration_seconds,
          start_seconds:start,end_seconds:cursor,duration_seconds:duration,
          voiceover,on_screen_text:caption,sonic_direction:silent?'No soundtrack.':String(shot.sonic_direction || ''),
          editorial_delivery:{origin:'local_deterministic_edit_not_qloo',voice_start_seconds:Math.round((start+delay)*100)/100,
            voice_direction:silent?'No spoken track.':profile.voice,
            sound_direction:silent?'No soundtrack. Received words may be shown verbatim as captions.':String(shot.sonic_direction || 'No new sound proposed.'),
            caption_origin:shot.on_screen_text?'received_on_screen_text':silent && shot.voiceover?'verbatim_received_narration':'no_caption',
            source_narration_omitted:silent && Boolean(shot.voiceover) && caption!==shot.voiceover,
            image_direction:'Use the received visual composition unchanged. No additional scene, figure, reveal or cutaway.'}};
      });
      return {id:profile.id,title:profile.title,intent:profile.intent,
        readiness:warnings.length?'needs_timing_review':'timing_estimate_only',
        total_duration_seconds:Math.round(total*100)/100,shots:edited,warnings,
        spoken_track_planned:edited.some(shot=>Boolean(shot.voiceover)),
        interpretation_origin:'local_deterministic_recomposition_not_native_writer_output'};
    });
    if(directions[0].shots.every((shot,i)=>shot.duration_seconds===directions[1].shots[i].duration_seconds && shot.editorial_delivery.voice_start_seconds===directions[1].shots[i].editorial_delivery.voice_start_seconds)) return fail('The timing constraint leaves no meaningful contrast between these edits. Keep the original or approve a longer duration.');
    const result={schema:'local-editorial-workbench-v1',status:'ready_for_author_choice',
      source:{run_id:source.run_id,director_version:source.director_version,created_at:brief.created_at,
        source_sha256:context.source_sha256,sha256_scope:'original_received_export_utf8',display_kind:context.display_kind,captured_at:context.captured_at || null},
      preserved:{synopsis:brief.synopsis,user_constraints:copy(constraints),shot_order:shots.map(s=>s.id),
        original_visuals_unchanged:true,used_words_are_verbatim:true,reference_bindings_unchanged:true,
        source_narration_may_be_omitted_in_silent_edit:silent},
      attribution:'Local editorial recomposition of the received result. No new Qloo request, model generation, rendered video or native verification of these edits.',
      timing_method:'Heuristic only: 2.5 spoken words/second and 3 caption words/second. Not measured audio, reading comfort or semantic verification.',
      language:'Received creative words are preserved in their original language. English editing instructions are not a translation.',
      directions};
    sourceBindings.set(result,JSON.stringify(source));
    return result;
  }
  function choose(workbench, source, choice, reason='', decidedAt='', sourceRaw=JSON.stringify(source)) {
    if(workbench.status!=='ready_for_author_choice') throw Error('No usable options are available.');
    if(sourceBindings.get(workbench)!==JSON.stringify(source)) throw Error('The source changed after these options were built. Build current options and choose again.');
    if(!['images_lead','words_lead','tie','neither'].includes(choice)) throw Error('Choose an option, a tie, or neither.');
    if(typeof reason!=='string' || reason.length>2000) throw Error('The choice note must be at most 2000 characters.');
    if(JSON.stringify(JSON.parse(sourceRaw))!==JSON.stringify(source)) throw Error('The original source bytes do not match the displayed document.');
    const selected=workbench.directions.find(d=>d.id===choice) || null;
    return {schema:'author-editorial-decision-v1',choice,reason:reason.trim() || null,decided_at:decidedAt,
      source:copy(workbench.source),attribution:workbench.attribution,
      author_preference_is_not_a_measured_quality_gain:true,
      decision_readiness:selected?selected.readiness:'no_direction_selected',
      selected_direction:copy(selected),alternatives:copy(workbench.directions),
      preserved:copy(workbench.preserved),timing_method:workbench.timing_method,language:workbench.language,
      original_received_document:copy(source),original_received_export_utf8:sourceRaw};
  }
  function frameAt(direction, elapsed) {
    const time=Math.min(direction.total_duration_seconds,Math.max(0,elapsed));
    const index=direction.shots.findIndex(shot=>time<shot.end_seconds);
    if(index<0)return {completed:true,elapsed_seconds:direction.total_duration_seconds,shot_id:null,voice_cue:false,visible_text:'',text_origin:'none'};
    const shot=direction.shots[index],spoken=Boolean(shot.voiceover),cue=spoken?shot.editorial_delivery.voice_start_seconds:shot.start_seconds;
    const text=spoken?shot.voiceover:shot.on_screen_text;
    const cueActive=time>=cue,rate=spoken?2.5:3;
    const shown=cueActive?Math.min(words(text),Math.floor((time-cue)*rate)+1):0;
    return {completed:false,elapsed_seconds:Math.round(time*100)/100,shot_id:shot.id,
      voice_cue:spoken && cueActive,visible_text:String(text || '').trim().split(/\s+/u).filter(Boolean).slice(0,shown).join(' '),
      text_origin:spoken?'received_narration_text_no_audio':'received_caption_text_no_audio'};
  }
  const normalizeWords=text=>String(text || '').toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
  function silentShape(draft) {const shape=copy(draft);delete shape.revision;for(const shot of shape.shots)delete shot.on_screen_text;return JSON.stringify(shape);}
  function createSilentDraft(source, context) {
    const brief=source?.brief,shots=brief?.shots;
    if(!/^[a-f0-9]{64}$/.test(context?.source_sha256 || '') || !['recorded','live','recovered','fixture'].includes(context?.display_kind))throw Error('Identify and hash the received parent before adapting it.');
    if(typeof source.run_id!=='string' || !source.run_id || brief?.run_id!==source.run_id || source.workflow_status!=='ok' || brief?.completeness!=='complete' || !Array.isArray(shots) || shots.length!==4 || !brief.user_constraints || Object.keys(source.gate_reasons || {}).length || brief.verification?.deterministic_status!=='pass' || brief.verification?.llm_status!=='accept')throw Error('A complete accepted parent is required; this local edit cannot repair its qualification.');
    if(source.mode!=='fixture' && source.qloo_api_verified!==true)throw Error('The parent does not carry verified historical Qloo evidence.');
    if(new Set(shots.map(s=>s.id)).size!==4 || shots.some(s=>s.line_status!=='active' || typeof s.visual_prompt!=='string' || !s.visual_prompt.trim() || !Number.isFinite(s.duration_seconds) || s.duration_seconds<=0))throw Error('The parent contains an inactive, incomplete or invalid shot.');
    const total=shots.reduce((sum,s)=>sum+s.duration_seconds,0);
    if(total<4 || total>300 || Math.abs(total-(brief.total_duration_seconds ?? total))>.011 || (brief.user_constraints.duration_seconds!==undefined && Math.abs(total-brief.user_constraints.duration_seconds)>.011))throw Error('Resolve the parent duration error before making a silent adaptation.');
    if(!shots.some(s=>String(s.voiceover || s.on_screen_text || '').trim()))throw Error('No received narration or caption can be transferred. Supply author-approved material first.');
    let cursor=0;
    const draft={schema:'local-silent-draft-v1',revision:0,
      parent:{run_id:source.run_id,director_version:source.director_version,created_at:brief.created_at,document_sha256:context.source_sha256,display_kind:context.display_kind,captured_at:context.captured_at || null},
      local_delivery_constraint:{sound_off:true,origin:'local_author_adaptation_not_native_user_constraints'},
      original_timing_retained:true,
      timing_locked_warning:Boolean(brief.user_constraints.timing_locked || brief.user_constraints.fixed_shot_durations || brief.user_constraints.shot_durations),
      shots:shots.map(shot=>{
        const spoken=String(shot.voiceover || ''),caption=String(shot.on_screen_text || '');
        const notOnScreen=Boolean(spoken.trim()) && !normalizeWords(caption).includes(normalizeWords(spoken));
        const proposed=notOnScreen?[caption,spoken].filter(s=>s.trim()).join('\n'):caption || spoken;
        const start=cursor;cursor=Math.round((cursor+shot.duration_seconds)*1000)/1000;
        return {id:shot.id,parent_shot_id:shot.id,visual_prompt:shot.visual_prompt,aspect_ratio:shot.aspect_ratio,assets:copy(shot.assets || []),
          start_seconds:start,end_seconds:cursor,duration_seconds:shot.duration_seconds,voiceover:'',sonic_direction:'',on_screen_text:proposed,
          transfer:{parent_spoken_text:spoken,parent_on_screen_text:caption,spoken_word_sequence_not_on_screen:notOnScreen,proposed_on_screen_text:proposed,
            detection_scope:'Text comparison only. The image may carry information; comprehension is not assessed.'},
          historical_parent_lineage:{decision_refs:copy(shot.decision_refs || []),evidence_refs:copy(shot.evidence_refs || []),retained_entity_refs:copy(shot.retained_entity_refs || [])}};
      })};
    silentBindings.set(draft,{sourceJSON:JSON.stringify(source),parentHash:context.source_sha256,shape:silentShape(draft)});
    return draft;
  }
  function silentBinding(draft,source) {
    const binding=silentBindings.get(draft);
    if(!binding || binding.sourceJSON!==JSON.stringify(source) || draft.parent.document_sha256!==binding.parentHash)throw Error('The parent changed after this adaptation was prepared. Load its current result and adapt again.');
    if(silentShape(draft)!==binding.shape || !Number.isInteger(draft.revision) || draft.revision<0)throw Error('Only the local on-screen text can be corrected; prepare again if the draft structure changed.');
    return binding;
  }
  function inspectSilentDraft(draft,source) {
    silentBinding(draft,source);const errors=[],estimates=[];
    if(draft.shots.length!==4)throw Error('The local shot inventory changed. Prepare a new adaptation.');
    for(let i=0;i<4;i++){
      const shot=draft.shots[i],original=source.brief.shots[i];
      if(shot.id!==original.id || shot.visual_prompt!==original.visual_prompt || shot.duration_seconds!==original.duration_seconds || shot.voiceover!=='' || shot.sonic_direction!=='' || JSON.stringify(shot.historical_parent_lineage)!==JSON.stringify({decision_refs:original.decision_refs || [],evidence_refs:original.evidence_refs || [],retained_entity_refs:original.retained_entity_refs || []}))throw Error('Only the local on-screen text may change; images, timing, silent audio fields and historical lineage must remain intact.');
      if(typeof shot.on_screen_text!=='string' || shot.on_screen_text.length>6000)throw Error('Each local caption must be text of at most 6000 characters.');
      if(!shot.on_screen_text.trim() && (original.voiceover || original.on_screen_text))errors.push({shot_id:shot.id,kind:'missing_silent_text'});
      const seconds=words(shot.on_screen_text)/3;estimates.push({shot_id:shot.id,word_count:words(shot.on_screen_text),seconds_estimate:Math.round(seconds*100)/100,available_seconds:shot.duration_seconds,may_not_fit:seconds>shot.duration_seconds});
    }
    return {scope:'Local structural checks and declared text-rate estimate only; no semantic verdict.',
      silent_audio_fields_empty:true,original_visuals_and_timing_unchanged:true,parent_native_user_constraints_unchanged:true,
      errors,caption_reading_estimates:estimates,timing_locked_warning:draft.timing_locked_warning,
      canon_spoilers_and_understandability:'not_verified',native_variant_verification:'not_executed'};
  }
  function setSilentCaption(draft,source,shotId,text) {
    silentBinding(draft,source);
    if(typeof text!=='string' || text.length>6000)throw Error('Use at most 6000 characters per local caption.');
    const shot=draft.shots.find(s=>s.id===shotId);if(!shot)throw Error('Select an existing parent shot.');
    shot.on_screen_text=text;draft.revision++;return inspectSilentDraft(draft,source);
  }
  function canonicalJSON(value) {
    if(Array.isArray(value))return '['+value.map(canonicalJSON).join(',')+']';
    if(value && typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonicalJSON(value[key])).join(',')+'}';
    return JSON.stringify(value);
  }
  async function digestText(text) {
    return Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(n=>n.toString(16).padStart(2,'0')).join('');
  }
  async function finalizeSilentDraft(draft,source,sourceRaw,decision,note='',decidedAt='') {
    const binding=silentBinding(draft,source),revision=draft.revision,snapshot=JSON.stringify(draft),checks=inspectSilentDraft(draft,source);
    if(!['accept','reject'].includes(decision))throw Error('Explicitly accept or reject this local adaptation.');
    if(typeof note!=='string' || note.length>2000)throw Error('Use at most 2000 characters for the decision note.');
    if(decision==='accept' && checks.errors.length)throw Error('A shot still has no silent text for its received words. Correct it or reject the adaptation.');
    if(JSON.stringify(JSON.parse(sourceRaw))!==binding.sourceJSON || await digestText(sourceRaw)!==binding.parentHash)throw Error('The original parent bytes/hash do not match this adaptation.');
    silentBinding(draft,source);
    if(draft.revision!==revision || JSON.stringify(draft)!==snapshot)throw Error('The local text changed during verification. Decide again on the current draft.');
    const payload={parent:copy(draft.parent),transformation:{kind:'local_sound_off_adaptation',author:'deterministic received-text transfer plus explicitly attributed local author corrections',base:'original_received_timing',revision},
      local_delivery_constraint:copy(draft.local_delivery_constraint),
      author_decision:{status:decision,note,decided_at:decidedAt,use_adaptation:decision==='accept',scope:'Local author decision, not a native or independent canon/spoiler verdict.'},
      shots:copy(draft.shots).map(shot=>({...shot,text_origin:shot.on_screen_text===shot.transfer.proposed_on_screen_text?'deterministic_verbatim_parent_text_transfer':'author_free_edit_unverified'})),
      local_checks:checks,
      variant_verification:{native_status:'not_executed',canon_spoiler_status:'not_verified',understandability_status:'requires_author_review'},
      historical_qloo_evidence_scope:'Parent only. These edits and free author text have no new Qloo or model validation.'};
    const hash=await digestText(canonicalJSON(payload));silentBinding(draft,source);
    if(draft.revision!==revision || JSON.stringify(draft)!==snapshot)throw Error('The local text changed during identity calculation. Decide again.');
    return {schema:'local-silent-adaptation-v1',derived_id:'local-silent-'+hash,payload_sha256:hash,
      identity_method:'SHA-256 of canonical sorted compact JSON of payload; parent original bytes are linked by payload.parent.document_sha256.',
      payload,parent_original_document:copy(source),parent_original_export_utf8:sourceRaw,
      parent_attachment_scope:'Unchanged historical parent. Its verification and Qloo flags apply only to it, never to this derivative.'};
  }
  return {build,choose,frameAt,createSilentDraft,setSilentCaption,inspectSilentDraft,finalizeSilentDraft,canonicalJSON};
})();
/* EDITORIAL_WORKBENCH_END */
