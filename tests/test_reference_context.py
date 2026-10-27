"""Prospective reference-context checks, no generation or cultural-quality score."""
from pathlib import Path
import copy
import json
import sys
import unittest

sys.dont_write_bytecode = True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'comparisons'))
from capture_scaffold_inputs import load
from capture_reference_context import capture, CapturedWithoutGeneration, RUN_ID


def no_execution(event,args):
    if event in {'socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'}:
        raise RuntimeError('Reference-context checks forbid network, subprocesses, client and model')


sys.addaudithook(no_execution)
core=load('reference_test_core',ROOT/'taste-matched-trailer/cultural_launch_director.py')
runner=load('reference_test_runner',ROOT/'taste-matched-trailer/guarded_qwen_runner.py')
CASES=json.loads((ROOT/'comparisons/scaffold_cases.json').read_bytes())
DECISION={'id':'synthetic-decision','run_id':RUN_ID,'status':'proposed','claim_origin':'editorial_inference',
          'selected_entity_ids':['synthetic-a','synthetic-b'],
          'evidence_refs':[{'evidence_id':'synthetic-evidence','item_pointer':'/results/0'},
                           {'evidence_id':'synthetic-evidence','item_pointer':'/results/1'}],
          'candidates':[{'entity_id':'synthetic-a','name':'Synthetic A','returned_order':0,'score_field':'synthetic_score','score_value':0.8},
                        {'entity_id':'synthetic-b','name':'Synthetic B','returned_order':1,'score_field':'synthetic_score','score_value':0.7}]}


class DocumentaryReferenceContext(unittest.TestCase):
    def document(self,case=None,decisions=None):
        case=case or CASES['cases'][0]
        validated=core.validate_brief(case['synopsis'],['The Turn of the Screw (book)'],
            {**CASES['common_constraints'],**case['constraints']})
        # These are synthetic documentary sources, not authenticated Qloo data.
        # Complete matching citations are now required even before the stopped writer callback.
        payload={'results':[{'entity_id':'synthetic-a'},{'entity_id':'synthetic-b'}]}
        source={'id':'synthetic-evidence','run_id':RUN_ID,'mode':'fixture','status':'ok',
            'source_type':'synthetic_fixture','authentication_state':'not_checked',
            'payload_redacted':payload,'payload_redacted_sha256':core.sha256_canonical(payload),
            'used_items':[{'entity_id':'synthetic-a','item_pointer':'/results/0'},
                          {'entity_id':'synthetic-b','item_pointer':'/results/1'}]}
        return capture(core,runner,validated,CASES['analysis'],[source],decisions if decisions is not None else [DECISION])

    def test_complete_messages_have_no_positional_assignment_but_keep_source_catalogue(self):
        document=self.document();payload=document['payload'];system,user=document['messages']
        self.assertEqual(json.loads(user['content']),{'role':'role_2_creative_redactor','payload':payload,'context':{}})
        self.assertTrue(all('retained_reference' not in shot for shot in payload['shot_plan']))
        self.assertNotIn('Preserve supplied bindings',payload['creative_contract'])
        self.assertNotIn('Preserve the supplied shot_plan bindings',system['content'])
        self.assertIn('documentary source context only',system['content'])
        self.assertIn('Rank alone assigns neither a shot nor a brief-wide reference',payload['creative_contract'])
        references=payload['retained_references']
        self.assertEqual([r['entity_id'] for r in references],DECISION['selected_entity_ids'])
        self.assertEqual([r['returned_order'] for r in references],[0,1])
        self.assertEqual([r['score_value'] for r in references],[0.8,0.7])
        self.assertEqual([r['evidence_ref'] for r in references],DECISION['evidence_refs'])
        self.assertEqual(document['metadata']['creative_output'],None)
        self.assertEqual(document['metadata']['model_calls'],0)

    def test_reordering_sources_changes_no_shot_directive_and_promotes_no_brief_reference(self):
        original=self.document()
        reversed_decision=copy.deepcopy(DECISION)
        reversed_decision['selected_entity_ids'].reverse();reversed_decision['evidence_refs'].reverse()
        reversed_document=self.document(decisions=[reversed_decision])
        self.assertEqual(original['payload']['shot_plan'],reversed_document['payload']['shot_plan'])
        self.assertEqual(original['payload']['creative_contract'],reversed_document['payload']['creative_contract'])
        self.assertEqual([r['entity_id'] for r in reversed_document['payload']['retained_references']],['synthetic-b','synthetic-a'])
        self.assertNotIn('brief_reference',reversed_document['payload'])
        self.assertNotIn('selected_artistic_reference',reversed_document['payload'])

    def test_canon_timing_audio_assets_and_empty_catalogue_are_not_rewritten(self):
        for case in CASES['cases']:
            with self.subTest(case=case['id']):
                document=self.document(case,[]);payload=document['payload']
                self.assertEqual(payload['synopsis'],case['synopsis'])
                self.assertEqual(payload['user_constraints'],{**CASES['common_constraints'],**case['constraints']})
                self.assertEqual(payload['themes'],CASES['analysis']['themes'])
                self.assertEqual(payload['retained_references'],[])
                self.assertEqual(sum(s['duration_seconds'] for s in payload['shot_plan']),38)
                self.assertTrue(all(s['sound_off']==payload['user_constraints']['sound_off'] for s in payload['shot_plan']))

    def test_native_reply_contract_still_accepts_only_text_not_reference_assignments(self):
        fields={'visual_prompt':'An empty reading table.','voiceover':'','sonic_direction':'',
                'on_screen_text':'Is someone near, or only a feeling?'}
        response={'directions':[{'title':'Synthetic check','angle':'Synthetic fixture, not a received creative result.'}],
                  'shot_overrides':{f'shot_{i:02d}':copy.deepcopy(fields) for i in range(1,5)}}
        checked=runner.validate_role_output('role_2_creative_redactor',response)
        self.assertEqual(len(checked['shot_overrides']),4)
        response['shot_overrides']['shot_03']['retained_reference']='synthetic-b'
        with self.assertRaises(runner.AdapterContractError):runner.validate_role_output('role_2_creative_redactor',response)
        self.assertEqual(runner.ROLE_OUTPUT_CAPS['role_2_creative_redactor'],1200)

    def test_output_links_and_verifier_keep_provenance_without_requiring_an_artistic_use(self):
        # Predetermined fixture text contains no borrowing or reference ID. It
        # exercises the real postprocessor and deterministic validator only.
        document=self.document(CASES['cases'][2])
        validated=core.validate_brief(document['payload']['synopsis'],['The Turn of the Screw (book)'],
                                      document['payload']['user_constraints'])
        fields={'visual_prompt':'An empty reading table.','voiceover':'','sonic_direction':'',
                'on_screen_text':'Is someone near, or only a feeling?'}
        response={'directions':[{'title':'Synthetic check','angle':'Predetermined fixture, no cultural inference.'}],
                  'shot_overrides':{f'shot_{i:02d}':copy.deepcopy(fields) for i in range(1,5)}}
        payload={'results':[{'entity_id':'synthetic-a'},{'entity_id':'synthetic-b'}]}
        evidence={'id':'synthetic-evidence','run_id':RUN_ID,'mode':'fixture','status':'ok',
                  'source_type':'synthetic_fixture','authentication_state':'not_checked',
                  'requested_at':'2026-10-24T00:00:00Z','received_at':'2026-10-24T00:00:00Z',
                  'payload_redacted':payload,'payload_redacted_sha256':core.sha256_canonical(payload),
                  'used_items':[{'entity_id':'synthetic-a','item_pointer':'/results/0'},
                                {'entity_id':'synthetic-b','item_pointer':'/results/1'}]}
        budget=core.make_initial_run_budget(RUN_ID,0,2)
        brief,_=core.llm_role_2_creative_redactor(RUN_ID,'fixture',validated,CASES['analysis'],
            [evidence],[copy.deepcopy(DECISION)],budget,False,lambda role,p:copy.deepcopy(response))
        self.assertEqual(core.validate_contract_links(brief,[DECISION],[evidence],budget),[])
        self.assertEqual([shot['retained_entity_refs'] for shot in brief['shots']],
                         [['synthetic-a'],['synthetic-a'],['synthetic-b'],[]])
        self.assertIn(core.REFERENCE_LINK_LIMITATION,brief['limitations'])
        captured={}
        def stop_verifier(role,payload):
            captured.update(role=role,payload=copy.deepcopy(payload))
            raise CapturedWithoutGeneration()
        with self.assertRaises(CapturedWithoutGeneration):
            core.llm_role_3_verifier(brief,[DECISION],[evidence],budget,stop_verifier)
        context=core.default_qwen_context_provider(captured['role'],captured['payload'])
        messages=runner.build_messages(captured['role'],captured['payload'],context)
        self.assertIn('Check lineage per shot, not by shot number',messages[0]['content'])
        self.assertIn(core.REFERENCE_LINK_LIMITATION,context['brief']['limitations'])
        self.assertEqual(json.loads(messages[1]['content'])['context'],context)
        self.assertEqual(brief['verification']['llm_status'],'not_run')


if __name__=='__main__':unittest.main(verbosity=2)
