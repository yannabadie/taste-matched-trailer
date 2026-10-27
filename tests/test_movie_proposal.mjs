import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {buildMovieRecommendArgs,buildMovieProposal,chooseMovieProposal} from '../taste-matched-trailer/movie_proposal.mjs';
import {normalizeHarnessEnvelope,enrichInsightsWithPhysicalEvidence,enrichRankWithPhysicalEvidence} from '../taste-matched-trailer/qloo_mcp_backend.mjs';

// Synthetic protocol inputs only; no captured Qloo response, key or network access.
const seed='a0000000-0000-4000-8000-000000000001';
const ids=[1,2,3].map(n=>'20000000-0000-4000-8000-'+String(n).padStart(12,'0'));
const inputHash='a'.repeat(64);
function response(){return {status:'ok',authentication_state:'authenticated',input_hash:inputHash,run_id:'run-synthetic-proposal',source_payload_sha256:'b'.repeat(64),physical_http_warning_refs:[{attempt:4,response_sha256:'c'.repeat(64),redacted_response_sha256:'d'.repeat(64)}],physical_http_warnings:[],warnings:[],limitations:[],tool_call_provenance:{tool:'qloo_recommend',arguments:buildMovieRecommendArgs([seed]),run_id:'run-synthetic-proposal',input_hash:inputHash,source_payload_sha256:'b'.repeat(64)},results:ids.map((entity_id,i)=>({entity_id,name:'Synthetic film '+i,type:'urn:entity:movie',affinity:[0.2,0.9,0.6][i]}))};}
const propose=(envelope=response())=>buildMovieProposal({seedIds:[seed],inputHash,envelope});

test('recommend arguments use explicit resolved signals and contain no supplied film shortlist',()=>{
  assert.deepEqual(buildMovieRecommendArgs([seed]),{target_type:'movie',signals:[seed],limit:6});
  for(const signals of [[],['Arrival'],[seed,seed],Array(4).fill(seed)])assert.throws(()=>buildMovieRecommendArgs(signals));
});
test('the proposal preserves response order even when affinities are not sorted, and does not choose for the author',()=>{
  const envelope=response(),before=JSON.stringify(envelope),p=propose(envelope);
  assert.equal(p.status,'needs_input');assert.deepEqual(p.candidates.map(x=>x.entity_id),ids);
  assert.deepEqual(p.candidates.map(x=>x.returned_order),[0,1,2]);assert.deepEqual(p.candidates.map(x=>x.score_value),[0.2,0.9,0.6]);
  assert.deepEqual(p.default_proposed_entity_ids,ids.slice(0,2));assert.equal(p.author_choice,null);
  assert.equal(JSON.stringify(envelope),before);assert.equal('structuredContent' in p,false);
});
test('a provider not_found warning cannot turn a popular list into recommendations from the book',()=>{
  const envelope=response();envelope.physical_http_warnings=[{type:'not_found','signal.interests.entities':[seed]}];
  const p=propose(envelope);assert.equal(p.status,'empty');assert.deepEqual(p.candidates,[]);assert.equal(p.author_choice,null);
  assert.match(p.reason,/different public film reference/);
});
test('API errors, absent provenance, missing affinities and invalid or duplicate movie IDs remain unusable',()=>{
  for(const change of [e=>e.status='error',e=>e.authentication_state='not_checked',e=>delete e.source_payload_sha256,e=>e.physical_http_warning_refs=[],e=>e.input_hash='e'.repeat(64),e=>e.results[1].affinity=null,e=>e.results[1].entity_id='invented',e=>e.results[1].entity_id=ids[0],e=>e.results[1].type='urn:entity:artist']){
    const e=response();change(e);const p=propose(e);assert.notEqual(p.status,'needs_input');assert.deepEqual(p.candidates,[]);
  }
});
test('an incomplete MCP list is not qualified after the normalizer silently removes its malformed row',()=>{
  const original=response(),raw={structuredContent:{status:'ok',results:[...original.results,{name:'Missing identity',affinity:null}]}};
  const normalized=Object.assign(normalizeHarnessEnvelope(raw,{hasServerKey:false}),{authentication_state:'authenticated',input_hash:inputHash,run_id:original.run_id,source_payload_sha256:original.source_payload_sha256,physical_http_warning_refs:original.physical_http_warning_refs,physical_http_warnings:[]});
  assert.equal(normalized.status,'invalid_contract');assert.deepEqual(propose(normalized).candidates,[]);
});
test('recommend provenance identifies the exact tool, arguments, execution and response',()=>{
  for(const field of ['wrong_tool','other_signals','other_response','other_execution']){
    const e=response();e.tool_call_provenance={tool:'qloo_recommend',arguments:buildMovieRecommendArgs([seed]),run_id:e.run_id,input_hash:inputHash,source_payload_sha256:e.source_payload_sha256};
    if(field==='wrong_tool')e.tool_call_provenance.tool='qloo_rank';
    if(field==='other_signals')e.tool_call_provenance.arguments.signals=[ids[0]];
    if(field==='other_response')e.tool_call_provenance.source_payload_sha256='e'.repeat(64);
    if(field==='other_execution')e.tool_call_provenance.run_id='run-synthetic-other';
    assert.equal(propose(e).status,'invalid_contract');
  }
});
test('explicit author order and response order are separate; rearranging or choosing a subset does not request rank',()=>{
  const p=propose(),choice=chooseMovieProposal(p,{proposal_id:p.proposal_id,selected_entity_ids:[ids[2],ids[0]]},inputHash);
  assert.equal(choice.status,'ready');assert.deepEqual(choice.author_selected_entity_ids,[ids[2],ids[0]]);
  assert.deepEqual(choice.selected_in_qloo_order,[ids[0],ids[2]]);assert.deepEqual(choice.proposed_in_qloo_order,ids);
  assert.equal(choice.rank_required_now,false);assert.equal(choice.additional_reference,null);
  assert.equal(p.author_choice,null);
});
test('missing explicit choice, unsupplied IDs, duplicate choices and stale proposals fail closed',()=>{
  const p=propose();
  for(const choice of [{proposal_id:p.proposal_id},{proposal_id:p.proposal_id,selected_entity_ids:[]},{proposal_id:p.proposal_id,selected_entity_ids:[seed]},{proposal_id:p.proposal_id,selected_entity_ids:[ids[0],ids[0]]},{proposal_id:'another-proposal',selected_entity_ids:[ids[0]]}])assert.throws(()=>chooseMovieProposal(p,choice,inputHash));
  assert.throws(()=>chooseMovieProposal(p,{proposal_id:p.proposal_id,selected_entity_ids:[ids[0]]},'f'.repeat(64)));
  const modified=structuredClone(p);modified.candidates[0].score_value=1;assert.throws(()=>chooseMovieProposal(modified,{proposal_id:p.proposal_id,selected_entity_ids:[ids[0]]},inputHash));
});
test('one author-supplied title requires resolution before ranking and never receives an invented ID',()=>{
  const p=propose(),choice=chooseMovieProposal(p,{proposal_id:p.proposal_id,selected_entity_ids:[ids[0]],additional_title:'A film named explicitly by the author'},inputHash);
  assert.equal(choice.status,'needs_reference_resolution');assert.equal(choice.rank_required_now,false);
  assert.equal('rank_required_after_resolution' in choice,false,'A typed title can resolve to an already proposed entity; rank cannot yet be required.');
  assert.equal(choice.rank_decision_pending,true);
  assert.deepEqual(choice.additional_reference,{query:'A film named explicitly by the author',entity_id:null,status:'not_resolved'});
});
test('recommend transport preserves physical ignored-signal warnings even when the harness reports ok',()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'qloo-synthetic-insights-'));
  try{
    const body=Buffer.from(JSON.stringify({warnings:[{type:'not_found','signal.interests.entities':[seed]}],results:{entities:response().results}}));
    fs.writeFileSync(path.join(directory,'http-04-response.txt'),body);
    const digest=createHash('sha256').update(body).digest('hex');
    const events=[{path:'/v2/insights',status:200,attempt:4,response_sha256:digest,redacted_response_sha256:digest}];
    const e=response(),raw={structuredContent:{status:'ok',interpretation:{signals:[{entityId:seed,name:'Synthetic book'}]}}};
    const checked=enrichInsightsWithPhysicalEvidence(e,raw,events,directory,[seed.toUpperCase()],'qloo_recommend');
    assert.equal(checked.status,'empty');assert.equal(propose(checked).status,'empty');
    assert.match(checked.limitations.join(' '),/recommendation/);assert.equal(checked.physical_http_warnings[0].type,'not_found');
    assert.throws(()=>enrichInsightsWithPhysicalEvidence(response(),raw,[{...events[0],redacted_response_sha256:'0'.repeat(64)}],directory,[seed],'qloo_recommend'),/PROVENANCE/);
    const legacy=enrichRankWithPhysicalEvidence(response(),raw,events,directory,[seed]);assert.match(legacy.limitations.join(' '),/ranking/);
  }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
