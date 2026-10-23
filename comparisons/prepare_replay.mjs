// Prepare only a network-disabled browser replay from an exact public export.
// Output contains parent data and must remain outside this source checkout.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,l)=>i%2?a:a.concat([[v,l[i+1]]]),[]));
if(!args['--parent'] || !args['--out'])throw Error('Use --parent PUBLIC_PARENT --out PRIVATE_FOLDER');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),out=path.resolve(args['--out']),sha=x=>createHash('sha256').update(x).digest('hex');
if(out===root || out.startsWith(root+path.sep))throw Error('Keep generated parent data outside the public checkout.');
const bytes=fs.readFileSync(args['--parent']),raw=bytes.toString('utf8'),source=JSON.parse(raw);
if(sha(bytes)!=='53b2f25bdfc431a2567ef7af4f1b9d51282ca62904a7e121dc484e1985c0435d')throw Error('Expected exact already-public parent928.');
const manifest={captured_at:source.brief.created_at,director_version:source.director_version,
  archive:{sha256:'not_used_public_export_only'},original_export:{sha256:sha(bytes)},
  scope:{public_references:['The Turn of the Screw']},original_reception:{qloo_network_attempts_used:source.run_budget.qloo_network_attempts_used,model_calls_used:source.run_budget.llm_calls_used,complete_shots:4}};
const literal=x=>JSON.stringify(x).replaceAll('<','\\u003c');let html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const marker='loadPreset();restorePending();loadConfiguration();viewRecording();';if(!html.includes(marker))throw Error('Inspect changed UI startup.');
html=html.replace(marker,`loadPreset();state.bundle=${literal(source)};state.snapshot=snapshot();state.displayKind='recorded';state.recording={originalRaw:${literal(raw)},manifest:${literal(manifest)},apiBase:RECORDING_ORIGIN};state.configurationReady=false;state.apiBase=null;renderBundle();$('connectionStatus').textContent='OFFLINE RESUME RECEPTION. Public parent20Oct; network blocked, no provider/model/native run.';`);
html=html.replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; connect-src \'none\'; img-src data:; media-src \'none\'">');
html=html.replace('<body>','<body><p class="status warn">LOCAL RESUME RECEPTION · authentic dated public parent. No author study, new generation or rendered film.</p>');
fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'OFFLINE-REPLAY.html'),html);
fs.writeFileSync(path.join(out,'REPLAY-SOURCE-INVENTORY.json'),JSON.stringify({observed_at:new Date().toISOString(),parent_sha256:sha(bytes),core_sha256:sha(fs.readFileSync(path.join(root,'editorial-workbench.js'))),frontend_sha256:sha(fs.readFileSync(path.join(root,'index.html'))),replay_sha256:sha(html),new_provider_calls:0,new_model_calls:0,native_execution:false},null,2)+'\n');
console.log(path.join(out,'OFFLINE-REPLAY.html'));
