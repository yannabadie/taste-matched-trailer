import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {initialiseGuardRun,readPhysicalCounter,createPhysicalBudgetFetch} from '../taste-matched-trailer/qloo_fetch_budget_preload.mjs';
import {QlooStdioSession} from '../taste-matched-trailer/qloo_mcp_backend.mjs';

async function guarded(action){
  const parent=fs.mkdtempSync(path.join(os.tmpdir(),'qloo-family-deadline-')),directory=path.join(parent,'run');
  initialiseGuardRun(directory,'run-synthetic-deadline',{maxAttempts:14,activeMs:120000});
  try{await action(directory);}finally{fs.rmSync(parent,{recursive:true,force:true});}
}
test('a family deadline exhausted outside HTTP refuses before reserving a new attempt',()=>guarded(async directory=>{
  let sends=0;const fetch=createPhysicalBudgetFetch({directory,now:()=>10000,phaseDeadlineMs:9999,baseFetch:async()=>{sends++;return new Response('{}');}});
  try{await assert.rejects(()=>fetch('https://hackathon.api.qloo.com/entities'),/FAMILY.*DEADLINE/);assert.equal(sends,0);assert.equal(readPhysicalCounter(directory).state.attempts,0);}finally{await fetch.close();}
}));
test('minimum request spacing cannot exceed the remaining family window',()=>guarded(async directory=>{
  let clock=10000,sends=0;
  const fetch=createPhysicalBudgetFetch({directory,now:()=>clock,phaseDeadlineMs:11000,pause:async ms=>{clock+=ms;},baseFetch:async()=>{sends++;return new Response('{}');}});
  try{await fetch('https://hackathon.api.qloo.com/entities');await assert.rejects(()=>fetch('https://hackathon.api.qloo.com/v2/insights'),/FAMILY.*DEADLINE/);assert.equal(sends,1);assert.equal(readPhysicalCounter(directory).state.attempts,1);}finally{await fetch.close();}
}));
test('an expired MCP family window is rejected before any child starts',async()=>{
  const session=new QlooStdioSession({}, {offlineOnly:true,activeTimeLimitMs:0});let starts=0;
  session.start=()=>{starts++;throw Error('The child must not start');};
  await assert.rejects(()=>session.request('tools/call',{}),/FAMILY.*DEADLINE/);assert.equal(starts,0);
});
test('an in-flight RPC timeout is bounded by the family remainder and terminates its child',async()=>{
  const session=new QlooStdioSession({}, {offlineOnly:true,activeTimeLimitMs:40});let killed=0;
  session.start=()=>{session.proc={stdin:{write(){}},kill(){killed++;}};};
  const started=performance.now();
  await assert.rejects(()=>session.request('tools/call',{},500),/FAMILY.*DEADLINE/);
  assert.ok(performance.now()-started<250);assert.equal(killed,1);assert.equal(session.pending.size,0);
});
