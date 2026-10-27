/** Pure proposal/choice contract, not yet wired to the live adapter.
 * Transport and physical receipts stay with the owner; these functions make no API/model call. */
import {createHash} from 'node:crypto';

const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const SHA=/^[a-f0-9]{64}$/;
const isHash=value=>typeof value==='string'&&SHA.test(value);
const key=id=>id.toLowerCase();
const stable=value=>JSON.stringify(value,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
const identity=proposal=>'movie-proposal-'+createHash('sha256').update(stable(proposal)).digest('hex');
function ids(values,max=3){
  if(!Array.isArray(values)||values.length<1||values.length>max||values.some(v=>typeof v!=='string'||!UUID.test(v))||new Set(values.map(key)).size!==values.length)throw Error('Explicit, distinct resolved entity IDs are required.');
  return [...values];
}
export function buildMovieRecommendArgs(seedIds){
  return {target_type:'movie',signals:ids(seedIds),limit:6};
}

export function buildMovieProposal({seedIds,inputHash,envelope}){
  const args=buildMovieRecommendArgs(seedIds);
  if(!isHash(inputHash))throw Error('A current brief hash is required.');
  const unavailable=(status,reason)=>({status,reason,candidates:[],author_choice:null});
  if(!envelope||typeof envelope!=='object')return unavailable('invalid_contract','The recommendation response is missing.');
  if(envelope.status!=='ok')return unavailable(['empty','needs_input','partial','degraded','error'].includes(envelope.status)?envelope.status:'invalid_contract','No complete Qloo recommendation result was received.');
  const refs=envelope.physical_http_warning_refs;
  if(envelope.authentication_state!=='authenticated'||envelope.input_hash!==inputHash||!isHash(envelope.source_payload_sha256)||typeof envelope.run_id!=='string'||!/^run-[a-z0-9_-]{4,64}$/i.test(envelope.run_id)||
      !Array.isArray(refs)||!refs.length||refs.some(r=>!r||!Number.isSafeInteger(r.attempt)||r.attempt<1||!isHash(r.response_sha256)||!isHash(r.redacted_response_sha256))||!Array.isArray(envelope.physical_http_warnings)){
    return unavailable('invalid_contract','Matching physical provenance and input are required before proposing films.');
  }
  const call=envelope.tool_call_provenance;
  if(!call||call.tool!=='qloo_recommend'||stable(call.arguments)!==stable(args)||call.source_payload_sha256!==envelope.source_payload_sha256||call.run_id!==envelope.run_id||call.input_hash!==inputHash){
    return unavailable('invalid_contract','The acquisition must match the exact recommendation operation, arguments, response and execution.');
  }
  const ignored=new Set(envelope.physical_http_warnings.flatMap(w=>w&&typeof w==='object'&&w.type==='not_found'&&Array.isArray(w['signal.interests.entities'])?w['signal.interests.entities'].filter(x=>typeof x==='string').map(key):[]));
  if(args.signals.every(id=>ignored.has(key(id))))return unavailable('empty','Qloo did not recognize the supplied signal. Choose a different public film reference; no replacement was made.');
  if(envelope.physical_http_warnings.length||(Array.isArray(envelope.warnings)&&envelope.warnings.length))return unavailable('degraded','Qloo warned about the supplied input. No complete proposal is qualified.');
  const rows=Array.isArray(envelope.results)?envelope.results:envelope.results?.entities;
  if(!Array.isArray(rows)||!rows.length)return unavailable('empty','Qloo supplied no film recommendations.');
  if(rows.length>args.limit)return unavailable('invalid_contract','The result exceeded the bounded proposal size.');
  const candidates=[],seen=new Set();
  for(const [returned_order,row] of rows.entries()){
    const entity_id=row?.entity_id??row?.id,score=row?.affinity??row?.query?.affinity;
    if(typeof entity_id!=='string'||!UUID.test(entity_id)||seen.has(key(entity_id))||!['movie','urn:entity:movie'].includes(row?.type)||typeof row?.name!=='string'||!row.name.trim()||row.name.length>500||typeof score!=='number'||!Number.isFinite(score)){
      return unavailable('invalid_contract','A recommendation is missing a distinct movie ID, name or measured affinity.');
    }
    seen.add(key(entity_id));
    candidates.push({entity_id,name:row.name,entity_type:'urn:entity:movie',score_field:typeof row.affinity==='number'?'affinity':'query.affinity',score_value:score,returned_order});
  }
  const proposal={schema:'movie-proposal/1',status:'needs_input',input_hash:inputHash,seed_entity_ids:args.signals,
    candidates,default_proposed_entity_ids:candidates.slice(0,2).map(c=>c.entity_id),author_choice:null,
    source:{tool:call.tool,arguments:structuredClone(call.arguments),run_id:envelope.run_id,source_payload_sha256:envelope.source_payload_sha256,
      physical_response_refs:refs.map(r=>({attempt:r.attempt,response_sha256:r.response_sha256,redacted_response_sha256:r.redacted_response_sha256}))},
    limitation:'Relative Qloo affinities propose references; the author must explicitly choose before a brief is written.'};
  return {...proposal,proposal_id:identity(proposal)};
}

/** Pass only the server-owned proposal; the client submits IDs, never replacement result rows. */
export function chooseMovieProposal(proposal,selection,currentInputHash){
  if(!proposal||proposal.schema!=='movie-proposal/1'||proposal.status!=='needs_input')throw Error('No open movie proposal.');
  const {proposal_id,...original}=proposal;
  if(proposal_id!==identity(original)||proposal.input_hash!==currentInputHash)throw Error('The proposal or brief changed; request its current version.');
  if(!selection||typeof selection!=='object'||Array.isArray(selection)||Object.keys(selection).some(k=>!['proposal_id','selected_entity_ids','additional_title'].includes(k))||selection.proposal_id!==proposal_id)throw Error('The explicit choice must identify its proposal.');
  const title=selection.additional_title===undefined?'':selection.additional_title;
  if(typeof title!=='string'||title.length>180)throw Error('At most one bounded additional film title is accepted.');
  const extra=title.trim(),selected=selection.selected_entity_ids;
  if(!Array.isArray(selected)||selected.length+(extra?1:0)<1||selected.length+(extra?1:0)>3)throw Error('Explicitly choose one to three movie references.');
  if(selected.length)ids(selected);
  const supplied=new Map(proposal.candidates.map(c=>[key(c.entity_id),c]));
  if(selected.some(id=>!supplied.has(key(id))))throw Error('The choice contains a movie that Qloo did not propose.');
  const picked=selected.map(id=>supplied.get(key(id)).entity_id),chosen=new Set(picked.map(key));
  return {status:extra?'needs_reference_resolution':'ready',proposal_id,input_hash:currentInputHash,
    seed_entity_ids:[...proposal.seed_entity_ids],choice_origin:'explicit_submission',
    proposed_in_qloo_order:proposal.candidates.map(c=>c.entity_id),author_selected_entity_ids:picked,
    selected_in_qloo_order:proposal.candidates.filter(c=>chosen.has(key(c.entity_id))).map(c=>c.entity_id),
    selected_candidates:proposal.candidates.filter(c=>chosen.has(key(c.entity_id))).map(c=>structuredClone(c)),
    additional_reference:extra?{query:extra,entity_id:null,status:'not_resolved'}:null,
    // A typed title may resolve to a film already proposed: compare resolved IDs before requesting rank.
    rank_required_now:false,rank_decision_pending:Boolean(extra)};
}
