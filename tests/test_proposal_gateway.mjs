// Admission/projection tests only. The internal executor is synthetic, with no provider or model.
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createPublicGateway} from '../taste-matched-trailer/public_gateway.mjs';
const origin='https://yannabadie.github.io',movie='20000000-0000-4000-8000-000000000001';
const proposalId='movie-proposal-'+'a'.repeat(64);
const context=key=>({origin,ip:'127.0.0.1',idempotencyKey:key});
const input={synopsis:'A synthetic story for admission testing.',suggested_public_references:['Synthetic public reference'],mode:'live',reference_workflow:'qloo_proposes',rank_domains:['movie']};
async function run(action){
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'qloo-proposal-gateway-')),calls=[];
  const gateway=createPublicGateway({allowedOrigin:origin,backendOrigin:'http://127.0.0.1:1',stateDirectory:directory,autoStart:false,
    internalPost:async(_route,body)=>{
      calls.push(structuredClone(body));const done=Boolean(body.movie_choice),status=done?'ok':'needs_input';
      const doc={schema_version:'1.0',director_version:'synthetic',run_id:body.explicit_run_id,mode:'live',status,workflow_status:status,qloo_api_verified:done,
        brief:{run_id:body.explicit_run_id,mode:'live',qloo_api_verified:done,shots:[]},candidate_resolution:{gate_status:'ok',confirmed_entity_ids:[]},decisions:[],
        run_budget:{qloo_network_attempts_used:done?6:4,qloo_network_attempt_limit:14,llm_calls_used:done?3:0,llm_call_limit:3},
        movie_proposal:{proposal_id:proposalId,source:{structuredContent:{private:'must be scrubbed'}}},
        movie_selection:done?{submitted_choice:body.movie_choice}:null,genre_tags:[{urn:'urn:tag:genre:book:synthetic',name:'Synthetic genre'}]};
      return {...doc,public_export:doc};
    }});
  try{await action(gateway,calls,()=>JSON.parse(fs.readFileSync(path.join(directory,'jobs.json'))));}
  finally{await gateway.close();fs.rmSync(directory,{recursive:true,force:true});}
}
test('proposed movie choice crosses the gateway without reserving a second family',()=>run(async(gateway,calls,state)=>{
  const first=await gateway.admit(input,context('proposal-first-00000001'));await gateway.pump();assert.equal(gateway.getJob(first.job_id).status,'needs_input');
  const choice={proposal_id:proposalId,selected_entity_ids:[movie]};
  const second=await gateway.admit({...input,parent_job_id:first.job_id,movie_choice:choice},context('proposal-child-00000001'));await gateway.pump();
  assert.equal(gateway.getJob(second.job_id).status,'completed');assert.deepEqual(calls[1].movie_choice,choice);
  assert.equal(calls[1].parent_run_id,calls[0].explicit_run_id);assert.equal(state().reserved.families,1);assert.equal(state().reserved.physical,14);assert.equal(state().reserved.models,3);
  assert.equal(Object.values(state().families)[0].physical_used,6);assert.equal(Object.values(state().families)[0].models_used,3);
  await assert.rejects(()=>gateway.admit({...input,parent_job_id:first.job_id,movie_choice:choice},context('stale-parent-00000001')),error=>error.code==='STALE_PARENT_JOB');
  assert.equal(calls.length,2);assert.equal(state().reserved.families,1);
}));
test('new public fields retain derived provenance while private nested envelopes remain removed',()=>run(async gateway=>{
  const first=await gateway.admit(input,context('proposal-projection-0001'));await gateway.pump();const result=gateway.getJob(first.job_id).bundle;
  assert.equal(result.movie_proposal.proposal_id,proposalId);assert.deepEqual(result.movie_proposal.source,{});assert.equal(result.genre_tags[0].name,'Synthetic genre');
}));
test('unparented, duplicated or unexpected movie-choice inputs allocate nothing',()=>run(async(gateway,calls,state)=>{
  const parent='30000000-0000-4000-8000-000000000001';
  for(const extra of [{movie_choice:{proposal_id:proposalId,selected_entity_ids:[movie]}}, {parent_job_id:parent,movie_choice:{proposal_id:proposalId,selected_entity_ids:[movie,movie]}}, {parent_job_id:parent,movie_choice:{proposal_id:proposalId,selected_entity_ids:[movie],api_key:'not-a-real-key'}}])
    await assert.rejects(()=>gateway.admit({...input,...extra},context('invalid-choice-00000001')),error=>error.code==='MOVIE_CHOICE_INVALID');
  assert.equal(calls.length,0);assert.equal(state().reserved.families,0);
}));
