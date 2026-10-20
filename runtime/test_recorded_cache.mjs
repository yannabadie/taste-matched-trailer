/** Fixed local response archive only. Fake HTTP objects, no listener/network/model. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {Readable} from 'node:stream';
import {createPublicGateway,RECORDED_CAPTURE} from '../taste-matched-trailer/public_gateway.mjs';
const root=fs.mkdtempSync(path.join(os.tmpdir(),'qloo-private-recording-test-'));
const archive=path.join(root,'archive');fs.mkdirSync(archive,{mode:0o700});
const source=path.join(os.homedir(),'Library/Application Support/Agentique/qloo-hackathon-private/jury-runtime-20261020/recorded-c481');
for(const name of [RECORDED_CAPTURE.manifest,RECORDED_CAPTURE.archive])fs.copyFileSync(path.join(source,name),path.join(archive,name));
for(const name of fs.readdirSync(archive))fs.chmodSync(path.join(archive,name),0o600);
const origin='https://yannabadie.github.io';const groups=[];let backendCalls=0;
const directory=path.join(root,'state');
const options={allowedOrigin:origin,backendOrigin:'http://127.0.0.1:1',stateDirectory:directory,recordedDirectory:archive,autoStart:false,
  internalReady:async()=>{backendCalls++;return false;},internalPost:async()=>{backendCalls++;throw Error('must not POST');}};
const invoke=async(gateway,url,declaredOrigin=origin,method='GET')=>{
 const req=Readable.from([]);req.url=url;req.method=method;req.headers={origin:declaredOrigin};req.socket={remoteAddress:'203.0.113.10'};
 const response={writeHead(code,headers){this.status=code;this.headers=headers;},end(bytes){this.bytes=Buffer.from(bytes||'');}};
 await gateway.handle(req,response);return response;
};
let gateway=createPublicGateway(options);
const stateFile=path.join(directory,'jobs.json');const exactState=fs.readFileSync(stateFile);
for(const [route,name,sha] of [['manifest',RECORDED_CAPTURE.manifest,RECORDED_CAPTURE.manifestSha256],['archive',RECORDED_CAPTURE.archive,RECORDED_CAPTURE.archiveSha256]]){
 const response=await invoke(gateway,'/api/director/recorded/'+route);
 assert.equal(response.status,200);assert.equal(response.headers['Access-Control-Allow-Origin'],origin);assert.equal(response.headers['Cache-Control'],'no-store');
 assert.equal(response.headers['X-Recorded-Captured-At'],RECORDED_CAPTURE.capturedAt);
 assert.equal(crypto.createHash('sha256').update(response.bytes).digest('hex'),sha);
 assert.equal(response.bytes.equals(fs.readFileSync(path.join(archive,name))),true);
}
assert.equal(backendCalls,0);assert.equal(fs.readFileSync(stateFile).equals(exactState),true);
groups.push({name:'fixed GETs return exact bytes without checking/calling absent backend or allocating budget',status:'pass'});
const denied=await invoke(gateway,'/api/director/recorded/archive','https://third-party.invalid');assert.equal(denied.status,403);assert.equal(denied.headers['Access-Control-Allow-Origin'],undefined);
const arbitrary=await invoke(gateway,'/api/director/recorded/jobs.json');assert.equal(arbitrary.status,404);
groups.push({name:'third-party Origin and arbitrary filenames refused',status:'pass'});
const expired=createPublicGateway({...options,stateDirectory:path.join(root,'expired'),now:()=>Date.parse(RECORDED_CAPTURE.expiresAt)});
const expiredResponse=await invoke(expired,'/api/director/recorded/archive');assert.equal(expiredResponse.status,410);await expired.close();
groups.push({name:'expired capture is refused honestly',status:'pass'});
const original=fs.readFileSync(path.join(archive,RECORDED_CAPTURE.archive));
fs.appendFileSync(path.join(archive,RECORDED_CAPTURE.archive),' ');
assert.equal((await invoke(gateway,'/api/director/recorded/manifest')).status,503);
assert.equal((await invoke(gateway,'/api/director/recorded/archive')).status,503);
fs.writeFileSync(path.join(archive,RECORDED_CAPTURE.archive),original);
fs.renameSync(path.join(archive,RECORDED_CAPTURE.manifest),path.join(archive,'missing-manifest'));
assert.equal((await invoke(gateway,'/api/director/recorded/archive')).status,503);
fs.renameSync(path.join(archive,'missing-manifest'),path.join(archive,RECORDED_CAPTURE.manifest));
groups.push({name:'missing or altered pair never served, no fallback/simulation',status:'pass'});
const pausedLease=path.join(root,'paused.json');fs.writeFileSync(pausedLease,JSON.stringify({schema_version:1,accepting:false,expires_at:new Date(Date.now()+60000).toISOString()}));
const paused=createPublicGateway({...options,stateDirectory:path.join(root,'paused-state'),admissionFile:pausedLease});
assert.equal((await invoke(paused,'/api/director/recorded/archive')).status,200);await paused.close();
fs.chmodSync(path.join(archive,RECORDED_CAPTURE.archive),0o644);
assert.equal((await invoke(gateway,'/api/director/recorded/archive')).status,503);
groups.push({name:'private capture remains readable during live pause; nonprivate permissions rejected',status:'pass'});
assert.equal(backendCalls,0);assert.equal(fs.readFileSync(stateFile).equals(exactState),true);
await gateway.close();
console.log(JSON.stringify({status:'PRIVATE_CACHE_PURE_ONLY',groups,backend_calls:backendCalls,qloo_calls:0,model_calls:0,listener_started:false,state_bytes_unchanged:true},null,2));
fs.rmSync(root,{recursive:true,force:true});
