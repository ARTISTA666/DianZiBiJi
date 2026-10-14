import json
import pytest

import run_t148_rag_fair_compare as fair


def note():
    return {"id": 21, "note_id": 7, "version_number": 3,
            "fixed_fields_json": {"source_accession": "GSM1", "reagents": ['A, B；C', '中文试剂'], "result": "7 µg"},
            "content_json": {"text": "原始来源正文"}}


def test_array_values_remain_atomic_and_serializations_preserve_source_facts():
    facts = fair.canonical_facts([note()])
    assert [f['object'] for f in facts if f['predicate']=='reagents'] == ['A, B；C', '中文试剂']
    a = fair.build_context('问题', [], facts, 'text', len)
    b = fair.build_context('问题', [], facts, 'triples', len)
    assert a['canonical_fact_ids'] == b['canonical_fact_ids']
    for left, right in zip(a['evidence'], b['evidence']):
        for key in ('fact_id', 'source', 'subject', 'predicate', 'object'):
            assert left[key] == right[key]
    assert all(e['source']['note_version_id']==21 for e in a['evidence'])
    assert a['prompt_sha256'] != b['prompt_sha256']


def test_budget_measures_final_messages_and_never_splits_fact():
    facts = fair.canonical_facts([note()])
    base = fair.build_context('q', [{'text':'共同文档', 'source_id':1}], [], 'triples', len)
    cap = base['estimated_message_content_tokens'] + 95
    value = fair.build_context('q', [{'text':'共同文档', 'source_id':1}], facts, 'triples', len, cap)
    assert value['estimated_message_content_tokens'] <= cap
    assert 0 < len(value['canonical_fact_ids']) < len(facts)
    assert value['document_base_sha256'] == base['document_base_sha256']
    originals = {f['id']:f['object'] for f in facts}
    assert all(e['object']==originals[e['fact_id']] for e in value['evidence'][1:])
    with pytest.raises(ValueError, match='exceeds budget'):
        fair.build_context('q', [{'text':'文档'}], facts, 'triples', len, 1)


def test_ranker_uses_question_and_source_only_and_preserves_set():
    facts = fair.canonical_facts([note()])
    ranked = fair.query_order(facts, 'GSM1 reagents 中文试剂')
    assert {f['id'] for f in ranked} == {f['id'] for f in facts}
    assert ranked == fair.query_order(facts, 'GSM1 reagents 中文试剂')
    assert ranked[0]['predicate'] == 'reagents'


def test_document_clipping_keeps_common_source_and_original_hash():
    raw = [{'text':'abcdef', 'source_id':123, 'filename':'public.txt', 'content_sha256':'original'}]
    value = fair.common_documents(raw, len, 3)
    assert value[0]['text']=='abc'
    assert value[0]['original_content_sha256']=='original'
    assert value[0]['clipped'] and value[0]['source_id']==123
    assert raw[0]['text']=='abcdef'


def test_analysis_rejects_prompt_drift_and_reports_missing_cases(tmp_path, monkeypatch):
    case = {'case_id':'Q-same_facts_text-r1','question_id':'Q','arm':'same_facts_text','repetition':1,'execution_order':1}
    prep = {'case_plan':[case], 'repetitions':1, 'random_seed':1, 'evidence_level':'retrospective'}
    monkeypatch.setattr(fair.old,'verify_freeze',lambda p:{'preparation':prep})
    fair.old.save_json(tmp_path/'questions.json',[{'id':'Q','question':'q','facts':[{'aliases':['x']}]}])
    fair.old.save_json(tmp_path/'contexts.json',{'Q':{a:{'prompt_sha256':'correct','estimated_message_content_tokens':3} for a in fair.ARMS}})
    (tmp_path/'results.jsonl').write_text(json.dumps({**case,'status':'failed','prompt_sha256':'wrong'})+'\n')
    with pytest.raises(ValueError,match='frozen plan or prompt'):
        fair.analyze(tmp_path)
    (tmp_path/'results.jsonl').write_text('')
    result=fair.analyze(tmp_path)
    assert result['not_run_cases']==[case['case_id']]
    assert result['semantic_primary_outcome_computed'] is False
