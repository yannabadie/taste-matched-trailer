// Entirely synthetic gardening brief. No Qloo response rows or measured scores.
export function gardeningSource(){
  const images=['A seed tray on a wooden table.','Hands label four pots.','A watering can beside the pots.','The same pots on a bright windowsill.'];
  const words=['Start with a seed.','Give each pot a name.','Water a little at a time.','A small garden begins here.'];
  return {schema_version:'1.0',director_version:'synthetic-test-only',run_id:'synthetic-gardening-control',mode:'fixture',status:'ok',workflow_status:'ok',qloo_api_verified:false,
    brief:{run_id:'synthetic-gardening-control',mode:'fixture',created_at:'2026-10-23T14:00:00Z',synopsis:'A practical, gentle guide to growing herbs indoors. No mystery, danger, invented events or plot reveal.',
      user_constraints:{aspect_ratio:'16:9',duration_seconds:38,no_visible_monster:true,sound_off:false,assets:['four existing still photographs'],spoilers:'Do not add a result or promise absent from these images.'},
      completeness:'complete',qloo_api_verified:false,total_duration_seconds:38,verification:{deterministic_status:'pass',llm_status:'accept',unresolved_claims:[]},
      shots:images.map((image,i)=>({id:'shot_0'+(i+1),purpose:'Gardening step '+(i+1),visual_prompt:image,voiceover:words[i],on_screen_text:words[i],sonic_direction:'Quiet room tone.',duration_seconds:9.5,aspect_ratio:'16:9',assets:['existing still photograph'],line_status:'active',decision_refs:[],evidence_refs:[],retained_entity_refs:[],interpretation_labels:['synthetic_fixture','editorial_inference']}))},
    decisions:[],directions:[],evidence_sources:[],run_budget:{qloo_network_attempts_used:0,llm_calls_used:0},gate_reasons:[],limitations:['Synthetic test fixture, not an API or model execution.']};
}
