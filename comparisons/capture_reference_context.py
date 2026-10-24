"""Capture the real prospective Role2 document and complete native messages.

No model, tokenizer, client, subprocess or network. Dated cultural context is
reused only as input; no received artistic result is changed or regenerated.
Provider-derived captures must stay outside the source checkout.
"""
from __future__ import annotations
import argparse
import copy
import difflib
import hashlib
import json
from pathlib import Path
import sys
from capture_scaffold_inputs import canonical, diff_paths, load

ACTIVE_CORE_SHA = '17481743204c75b04a1c82886364c3340b83e5b779fad51723db694b511c0d63'
ACTIVE_RUNNER_SHA = '8e37963a6e1915e23f1b9b0cc7aec1cbd0c7c31d68e5cda11ba2f51da8284736'
PARENT_NATIVE_SHA = '40b640c022bccadb8ef66308cb69d7c61159073621afa67db2410a7fc8fe9f0a'
RUN_ID = 'run-reference-context-input-20261024'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


class CapturedWithoutGeneration(Exception):
    pass


def capture(core, runner, validated, analysis, evidences, decisions):
    document = {}
    budget = core.make_initial_run_budget(RUN_ID, 0, 1)
    def stop(role, payload):
        document.update(role=role, payload=copy.deepcopy(payload))
        raise CapturedWithoutGeneration()
    try:
        core.llm_role_2_creative_redactor(RUN_ID, 'recorded_live', copy.deepcopy(validated),
            copy.deepcopy(analysis), copy.deepcopy(evidences), copy.deepcopy(decisions), budget, False, stop)
    except CapturedWithoutGeneration:
        pass
    else:
        raise AssertionError('Real Role2 must stop before generation')
    context = core.default_qwen_context_provider(document['role'], document['payload'])
    document['messages'] = runner.build_messages(document['role'], document['payload'], context)
    document['metadata'] = {'function_executed':'llm_role_2_creative_redactor',
        'messages_builder_executed':'guarded_qwen_runner.build_messages',
        'context_provider_executed':'default_qwen_context_provider',
        'prospective_input_only':True, 'creative_output':None, 'model_calls':0, 'Qloo_calls':0,
        'tokenizer_or_client_created':False, 'persistent_quota_changed':False,
        'in_memory_callback_reservation':budget['llm_calls_used'],
        'counter_scope':'Application increments before capture exception, not a model call.'}
    return document


def capture_parent(core, runner, parent):
    return capture(core, runner, parent['validated_brief'], parent['role_1_analysis'],
                   parent['evidences'], parent['decisions'])


def compare(before, after):
    a, b = before['payload'], after['payload']
    for field in ['run_id','mode','synopsis','themes','user_constraints','retained_references']:
        assert a[field] == b[field], field
    assert [{k:v for k,v in plan.items() if k!='retained_reference'} for plan in a['shot_plan']] == b['shot_plan']
    assert all('retained_reference' not in plan for plan in b['shot_plan'])
    assert 'Preserve supplied bindings' in a['creative_contract']
    assert 'Preserve supplied bindings' not in b['creative_contract']
    assert 'Preserve the supplied shot_plan bindings' in before['messages'][0]['content']
    assert 'Preserve the supplied shot_plan bindings' not in after['messages'][0]['content']
    assert json.loads(after['messages'][1]['content']) == {'role':after['role'],'payload':b,'context':{}}
    wanted = ['/creative_contract'] + [f'/shot_plan/{i}/retained_reference' for i in range(4)]
    assert diff_paths(a,b) == wanted
    return {'changed_payload_paths':wanted,'canon_constraints_themes_unchanged':True,
            'catalogue_order_values_provenance_unchanged':True,
            'shot_timing_assets_purposes_unchanged':True,
            'complete_SYSTEM_and_USER_captured':True,
            'constraint_removed_not_replaced_by_brief_wide_reference':True,
            'new_model_calls':0,'new_Qloo_calls':0,'new_families':0,
            'scope':'Prompt correction only. Existing output source links remain compatibility provenance, not artistic causality.'}


def write_capture(out, label, document):
    raw = (json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode()
    (out/(label+'-DOCUMENT.json')).write_bytes(raw)
    for message in document['messages']:
        (out/(label+'-'+message['role'].upper()+'.txt')).write_text(message['content'])
    # Separators are for human inspection; each message string is unchanged.
    (out/(label+'-PROMPT-COMPLETE.txt')).write_text('SYSTEM\n'+document['messages'][0]['content']+
        '\n\nUSER\n'+document['messages'][1]['content']+'\n')
    return {'document_sha256':sha(raw),'messages_sha256':sha(canonical(document['messages']).encode()),
        'SYSTEM_sha256':sha(document['messages'][0]['content'].encode()),
        'USER_sha256':sha(document['messages'][1]['content'].encode())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-directory',type=Path,required=True)
    parser.add_argument('--native-parent',type=Path,required=True)
    parser.add_argument('--first-before-capture',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if args.out.resolve().is_relative_to(root):
        raise ValueError('Keep provider-derived context outside source checkout')
    before_core=args.before_directory/'cultural_launch_director.py'
    before_runner=args.before_directory/'guarded_qwen_runner.py'
    assert sha(before_core.read_bytes())==ACTIVE_CORE_SHA
    assert sha(before_runner.read_bytes())==ACTIVE_RUNNER_SHA
    parent_raw=args.native_parent.read_bytes();assert sha(parent_raw)==PARENT_NATIVE_SHA
    parent=json.loads(parent_raw)
    core=load('reference_context_candidate',root/'taste-matched-trailer/cultural_launch_director.py')
    runner=load('reference_context_runner',root/'taste-matched-trailer/guarded_qwen_runner.py')
    before=capture_parent(load('reference_context_before',before_core),
                          load('reference_context_before_runner',before_runner),parent)
    after=capture_parent(core,runner,parent)
    first=json.loads(args.first_before_capture.read_bytes())
    assert before['payload']==first['payload'] and before['messages']==first['messages']
    checks=compare(before,after)
    args.out.mkdir(parents=True,exist_ok=False)
    captures={label:write_capture(args.out,label,document) for label,document in [('BEFORE',before),('AFTER',after)]}
    texts=[json.dumps({'SYSTEM':d['messages'][0]['content'],'USER':json.loads(d['messages'][1]['content'])},
                     ensure_ascii=False,indent=2).splitlines(keepends=True) for d in [before,after]]
    diff=''.join(difflib.unified_diff(*texts,fromfile='active2.6.4-message',tofile='candidate-message'))
    (args.out/'PROMPT-DIFF.txt').write_text(diff)
    receipt={'status':'REAL_WRITER_INPUT_CAPTURED_BEFORE_AFTER_NO_GENERATION','checks':checks,'captures':captures,
        'sources':{'before_core':ACTIVE_CORE_SHA,'before_runner':ACTIVE_RUNNER_SHA,
                   'candidate_core':sha((root/'taste-matched-trailer/cultural_launch_director.py').read_bytes()),
                   'candidate_runner':sha((root/'taste-matched-trailer/guarded_qwen_runner.py').read_bytes()),
                   'capture_tool':sha(Path(__file__).read_bytes()),'parent_native':PARENT_NATIVE_SHA},
        'first_observation_preserved_and_exact':True,'diff_sha256':sha(diff.encode()),
        'parent_original_run_id':parent['run_id'],'source_context':'Dated received context only, original output unchanged.',
        'no_creative_quality_or_native_qualification':True}
    (args.out/'CAPTURE-RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'checks':checks,'captures':captures,
        'receipt':str(args.out/'CAPTURE-RECEIPT.json'),'sha256':sha((args.out/'CAPTURE-RECEIPT.json').read_bytes())},indent=2))


if __name__=='__main__':
    sys.dont_write_bytecode=True
    def no_execution(event,args):
        if event in {'socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'}:
            raise RuntimeError('Prompt capture forbids network, subprocess, client and model')
    sys.addaudithook(no_execution)
    main()
