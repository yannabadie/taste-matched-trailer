/* EDITORIAL_WORKBENCH_START */
// A local edit decision over received material, not another Qloo/model result.
const EditorialWorkbench = (() => {
  const sourceBindings = new WeakMap();
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
  return {build,choose,frameAt};
})();
/* EDITORIAL_WORKBENCH_END */
