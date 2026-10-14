#!/usr/bin/env python3
"""Frozen retrospective encoding and content-token-budget controls; no thesis writes."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
from pathlib import Path
from typing import Callable

import run_t114_rust_retest_v2 as old

ARMS = ("same_facts_text", "same_facts_triples", "budget_ordered", "budget_query_ranked")


def canonical_facts(notes: list[dict]) -> list[dict]:
    """Use every source field, never select facts from answer references."""
    facts = []
    for note in sorted(notes, key=lambda n: n["note_id"]):
        subject = note["fixed_fields_json"]["source_accession"]
        source = {"note_id": note["note_id"], "note_version_id": note["id"],
                  "version_number": note["version_number"], "snapshot_sha256": old.digest(old.json_bytes(note))}
        fields = {**note["fixed_fields_json"], "record_text": note["content_json"]["text"]}
        for field, value in sorted(fields.items()):
            values = value if isinstance(value, list) else [value]
            for index, item in enumerate(values):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("all canonical values must be nonempty strings")
                facts.append({"id": f"N{note['note_id']}-{field}-{index}", "subject": subject,
                              "predicate": field, "object": item, "source": source})
    if len({f["id"] for f in facts}) != len(facts):
        raise ValueError("duplicate canonical fact identity")
    return facts


def fact_text(fact: dict, representation: str) -> str:
    # JSON strings preserve exact values, including quotes, punctuation and newlines.
    value = json.dumps(fact["object"], ensure_ascii=False)
    if representation == "text":
        return f"{fact['subject']} 的 {fact['predicate']} 字段为 {value}。"
    if representation == "triples":
        return f"({fact['subject']}, {fact['predicate']}, {value})"
    raise ValueError("unknown representation")


def render(documents: list[dict], facts: list[dict], representation: str) -> tuple[str, list[dict]]:
    evidence = [{**d, "type": "document"} for d in documents]
    evidence += [{"type": "canonical_fact", "fact_id": f["id"], "source": f["source"],
                  "subject": f["subject"], "predicate": f["predicate"], "object": f["object"],
                  "text": fact_text(f, representation)} for f in facts]
    return "\n\n".join(f"[E{i}] {e['text']}" for i, e in enumerate(evidence, 1)), evidence


def messages(question: str, text: str) -> list[dict]:
    return [{"role": "system", "content": old.SYSTEM_PROMPT},
            {"role": "user", "content": old.USER_TEMPLATE.format(question=question, context=text)}]


def content_tokens(msgs: list[dict], count: Callable[[str], int]) -> int:
    return sum(count(m["content"]) for m in msgs)


def query_order(facts: list[dict], question: str) -> list[dict]:
    def terms(text: str) -> set[str]:
        normalized = old.normalize(text)
        ascii_words = set(re.findall(r"[a-z0-9_]+", text.casefold()))
        chinese = set(re.findall(r"[\u4e00-\u9fff]{2}", normalized))
        return ascii_words | chinese
    query = terms(question)
    return sorted(facts, key=lambda f: (-len(query & terms(f"{f['subject']} {f['predicate']} {f['object']}")), f["id"]))


def build_context(question: str, documents: list[dict], facts: list[dict], representation: str,
                  count: Callable[[str], int], budget: int | None = None) -> dict:
    chosen = list(facts) if budget is None else []
    base, _ = render(documents, [], representation)
    if budget is not None:
        if content_tokens(messages(question, base), count) > budget:
            raise ValueError("common document base plus prompt exceeds budget")
        for fact in facts:
            candidate, _ = render(documents, [*chosen, fact], representation)
            if content_tokens(messages(question, candidate), count) <= budget:
                chosen.append(fact)
    text, evidence = render(documents, chosen, representation)
    msgs = messages(question, text)
    return {"messages": msgs, "prompt_sha256": old.digest(old.json_bytes(msgs)), "evidence": evidence,
            "canonical_fact_ids": [f["id"] for f in chosen], "estimated_message_content_tokens": content_tokens(msgs, count),
            "content_token_cap": budget, "document_base_sha256": old.digest(old.json_bytes(documents))}


def common_documents(raw: list[dict], count: Callable[[str], int], budget: int) -> list[dict]:
    selected = []
    for doc in raw:
        candidate = {**doc, "original_content_sha256": doc.get("content_sha256", old.digest(doc["text"].encode()))}
        # Clip a common document once before branching, never in response to a reference answer.
        available = budget - sum(count(d["text"]) for d in selected)
        if available <= 0:
            break
        text = candidate["text"]
        if count(text) > available:
            low, high = 0, len(text)
            while low < high:
                mid = (low + high + 1) // 2
                if count(text[:mid]) <= available:
                    low = mid
                else:
                    high = mid - 1
            text = text[:low]
            # Recheck because token counts need not be monotonic at every character boundary.
            while text and count(text) > available:
                text = text[:-1]
        if text:
            candidate.update(text=text, content_sha256=old.digest(text.encode()), clipped=text != doc["text"])
            selected.append(candidate)
    return selected


def prepare(source: Path, tokenizer: Path, protocol: Path, output: Path, *, budget: int = 1536,
            document_budget: int = 400, seed: int = 20261012148, repetitions: int = 1) -> dict:
    from tokenizers import Tokenizer
    old.verify_freeze(source)
    if output.exists():
        raise ValueError("new batch directory required; refuse to overwrite")
    if budget <= document_budget or document_budget <= 0 or repetitions < 1:
        raise ValueError("invalid budget or repetitions")
    counter = Tokenizer.from_file(str(tokenizer))
    count = lambda text: len(counter.encode(text, add_special_tokens=False).ids)
    questions_value = old.load_json(source / "questions.json")
    questions = old.validate_questions(questions_value)
    facts = canonical_facts(old.load_json(source / "approved-note-versions.json"))
    previous = old.load_json(source / "contexts.json")
    contexts = {}
    for q in questions:
        docs = common_documents(previous[q["id"]]["document_rag"]["evidence"], count, document_budget)
        contexts[q["id"]] = {
            "same_facts_text": build_context(q["question"], docs, facts, "text", count),
            "same_facts_triples": build_context(q["question"], docs, facts, "triples", count),
            "budget_ordered": build_context(q["question"], docs, facts, "triples", count, budget),
            "budget_query_ranked": build_context(q["question"], docs, query_order(facts, q["question"]), "triples", count, budget),
        }
    cases = [{"question_id": q["id"], "question": q["question"], "arm": arm, "repetition": r,
              "case_id": f"{q['id']}-{arm}-r{r}"} for q in questions for arm in ARMS for r in range(1, repetitions + 1)]
    random.Random(seed).shuffle(cases)
    for i, case in enumerate(cases, 1):
        case["execution_order"] = i
    generation = old.generation_config("https://api.deepseek.com", "deepseek-v4-flash")
    preparation = {"case_plan": cases, "generation": generation, "repetitions": repetitions, "random_seed": seed,
                   "source_freeze_sha256": old.file_hash(source / "freeze-manifest.json"),
                   "content_token_cap": budget, "common_document_content_budget": document_budget,
                   "token_count_method": "official V4 offline tokenizer; sum of message content only, excludes provider chat framing; estimate, API usage authoritative",
                   "primary_comparison": "same_facts_triples minus same_facts_text (encoding only, unequal token counts)",
                   "secondary_comparison": "budget_query_ranked minus budget_ordered (same estimated content-token cap, actual lengths differ)",
                   "metric": "auxiliary lexical alias coverage only; no semantic or topology-causal claim",
                   "evidence_level": "retrospective development control using previously frozen public GEO-derived records; no independent held-out claim"}
    output.mkdir(parents=True)
    for name, value in (("questions.json", questions_value), ("facts.json", facts), ("contexts.json", contexts), ("preparation.json", preparation)):
        old.save_json(output / name, value, exclusive=True)
    inputs = [source / "freeze-manifest.json", source / "freeze.sha256", source / "questions.json",
              source / "approved-note-versions.json", source / "contexts.json", tokenizer, protocol,
              Path(__file__), Path(old.__file__), *[output / f for f in ("questions.json", "facts.json", "contexts.json", "preparation.json")]]
    manifest = {"status": "FROZEN_BEFORE_GENERATION", "finalized_at": old.utc_now(), "preparation": preparation,
                "input_files": [{"path": str(p.resolve()), "sha256": old.file_hash(p)} for p in inputs],
                "independent_confirmatory_claim": False, "thesis_sync": False}
    old.save_json(output / "freeze-manifest.json", manifest, exclusive=True)
    (output / "freeze.sha256").write_text(old.file_hash(output / "freeze-manifest.json") + "\n")
    return {"planned_cases": len(cases), "facts": len(facts), "freeze_sha256": old.file_hash(output / "freeze-manifest.json")}


def execute(output: Path, key_env: str, workers: int) -> dict:
    manifest = old.verify_freeze(output)
    key = os.environ.get(key_env)
    if not key:
        raise ValueError("configured generation key is missing")
    contexts = old.load_json(output / "contexts.json")
    # Exclusive creation: partial/failed records are retained; resume requires a new explicit design.
    rows = []
    with (output / "results.jsonl").open("x", encoding="utf-8") as handle, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(old.generate_case, c, contexts[c["question_id"]][c["arm"]], manifest["preparation"]["generation"], key) for c in manifest["preparation"]["case_plan"]]
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            rows.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            print(json.dumps({"persisted": len(rows), "planned": len(futures), "status": row["status"]}), flush=True)
    old.verify_freeze(output)
    return {"persisted": len(rows), "successful": sum(r["status"] == "completed" for r in rows)}


def analyze(output: Path) -> dict:
    manifest = old.verify_freeze(output)
    preparation = manifest["preparation"]
    questions = {q["id"]: q for q in old.validate_questions(old.load_json(output / "questions.json"))}
    contexts = old.load_json(output / "contexts.json")
    rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines() if line.strip()]
    plan = {c["case_id"]: c for c in preparation["case_plan"]}
    seen, scores, grouped = set(), [], {}
    for row in rows:
        if row["case_id"] in seen or row["case_id"] not in plan:
            raise ValueError("duplicate or unplanned result")
        seen.add(row["case_id"])
        case = plan[row["case_id"]]
        if any(row[k] != case[k] for k in ("question_id", "arm", "repetition", "execution_order")) or row["prompt_sha256"] != contexts[case["question_id"]][case["arm"]]["prompt_sha256"]:
            raise ValueError("result differs from frozen plan or prompt")
        if row["status"] == "completed":
            score = old.score_answer(row["answer"], questions[row["question_id"]])
            scores.append({"case_id": row["case_id"], **score})
            grouped.setdefault((row["question_id"], row["arm"]), []).append(score["required_fact_coverage"])
    comparisons = {}
    for a, b in ((ARMS[1], ARMS[0]), (ARMS[3], ARMS[2])):
        eligible = [q for q in questions if len(grouped.get((q, a), [])) == preparation["repetitions"] and len(grouped.get((q, b), [])) == preparation["repetitions"]]
        diffs = [sum(grouped[q, a]) / preparation["repetitions"] - sum(grouped[q, b]) / preparation["repetitions"] for q in eligible]
        comparisons[f"{a}_minus_{b}"] = {"paired_question_ids": eligible, **old.paired_stats(diffs, preparation["random_seed"])}
    summary = {"analyzed_at": old.utc_now(), "planned_cases": len(plan), "persisted_cases": len(rows), "successful_cases": len(scores),
               "failed_cases": len(rows) - len(scores), "not_run_cases": sorted(set(plan) - seen), "unit": "question", "comparisons": comparisons,
               "semantic_primary_outcome_computed": False, "thesis_sync": False, "evidence_level": preparation["evidence_level"],
               "arm_summary": {a: {"mean_lexical_coverage": sum(x for (q, arm), v in grouped.items() if arm == a for x in v) / max(1, sum(len(v) for (q, arm), v in grouped.items() if arm == a)),
                                    "successful_cases": sum(len(v) for (q, arm), v in grouped.items() if arm == a),
                                    "estimated_content_tokens": [contexts[q][a]["estimated_message_content_tokens"] for q in questions],
                                    "provider_prompt_tokens": [(r.get("usage") or {}).get("prompt_tokens") for r in rows if r["arm"] == a]} for a in ARMS},
               "limits": ["Alias coverage does not verify semantic entailment, sample binding or citation correctness", "Budget is offline estimated message content; API counts include framing and may differ", "Equal cap does not imply equal consumed tokens", "Encoding comparison preserves all canonical facts but token lengths differ", "Prior questions and snapshots reused; no independent generalization", "One run does not establish repeatability; repeated cases never increase question n", "No graph topology causal claim and no human evaluation"]}
    old.save_json(output / "fact-score-traces.json", scores, exclusive=True)
    old.save_json(output / "analysis.json", summary, exclusive=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--tokenizer", type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--budget", type=int, default=1536)
    p.add_argument("--document-budget", type=int, default=400)
    p = sub.add_parser("run")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--key-env", default="DEEPSEEK_API_KEY")
    p.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    p.add_argument("--execute", action="store_true")
    p = sub.add_parser("analyze")
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.source.resolve(), args.tokenizer.resolve(), args.protocol.resolve(), args.output.resolve(), budget=args.budget, document_budget=args.document_budget)
    elif args.command == "run":
        if not args.execute:
            parser.error("external public-data generation requires --execute")
        result = execute(args.output.resolve(), args.key_env, args.workers)
    else:
        result = analyze(args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
