//! Local extraction of explicitly asserted facts in the approved note body.
//! Each rule captures an original label and the sentence that supports it.
pub(super) mod context;
use super::{term, ExtractedTerm};
use regex::Regex;
use serde_json::Value;
use std::sync::OnceLock;

type FactType = (&'static str, &'static str);
const INSTRUMENT: FactType = ("instrument", "uses_instrument");
const REAGENT: FactType = ("reagent", "uses_reagent");
const SAMPLE: FactType = ("sample", "uses_sample");
const RESULT: FactType = ("result", "produces_result");

struct Rule {
    fact_type: FactType,
    pattern: Regex,
}

// Only traverse note-body containers; structured values and attachment metadata
// have independent semantics and must not be treated as recorded observations.
pub(super) fn narrative<'a>(value: &'a Value, out: &mut Vec<&'a str>) {
    match value {
        Value::String(s) => out.push(s),
        Value::Array(items) => items.iter().for_each(|v| narrative(v, out)),
        Value::Object(map) => {
            for key in [
                "text",
                "body",
                "markdown",
                "paragraphs",
                "content",
                "blocks",
                "children",
            ] {
                if let Some(v) = map.get(key) {
                    narrative(v, out);
                }
            }
        }
        _ => {}
    }
}

fn rules() -> &'static [Rule] {
    static RULES: OnceLock<Vec<Rule>> = OnceLock::new();
    RULES.get_or_init(|| {
        // Type-bearing noun heads disambiguate "used an instrument" from e.g.
        // "used a different method". Unknown names can still use explicit fields.
        let instrument = r"(?:microscopes?|thermometers?|spectrometers?|calorimeters?|photometers?|balances?|analy[sz]ers?|scanners?|sensors?|cameras?|detectors?|centrifuges?|incubators?|pipettes?|oscilloscopes?|multimeters?|voltmeters?|manometers?|meters?|pumps?|ovens?|furnaces?|readers?|mixers?)";
        let material = r"(?:solutions?|buffers?|solvents?|reagents?|dyes?|stains?|resins?|adhesives?|lubricants?|calibrants?)";
        let phrase = |head: &str| format!(r"(?:[a-z0-9][a-z0-9/-]*[ \t]+){{0,4}}?{head}\b");
        let model_id = r"(?:[ \t]+(?-i:[A-Z][A-Za-z0-9_-]{0,14}\d[A-Za-z0-9_-]{0,8}))?";
        let instrument_name = format!("{}{model_id}", phrase(instrument));
        let det = r"(?:(?:a|an|the|our)[ \t]+)?";
        let amount = r"(?:\d+(?:\.\d+)?[ \t]*(?:[µμumk]?l|[µμumk]?g|mol)[ \t]+(?:of[ \t]+)?)?";
        let sample = r"(?i:samples?|specimens?)[ \t]+(?:[A-Z][A-Z0-9_-]*\d[A-Z0-9_-]*|[A-Z]|\d+[A-Za-z]?)\b";
        let zh_device = r"(?:显微镜|温度计|光谱仪|分析仪|天平|相机|传感器|扫描仪|离心机|压力计|万用表|示波器|测量仪|烘箱|检测仪|分光光度计)";
        let zh_material = r"(?:溶液|缓冲液|试剂|溶剂|染料|清洗液|指示剂|粘合剂|润滑油|树脂)";
        let specimen_action = r"(?:tested|measured|examined|inspected|weighed|collected|scanned|analyzed|analysed)";
        let specimen_head = r"(?:coupons?|specimens?|samples?)";
        let material_specimen = format!(r"(?:[a-z0-9][a-z0-9/-]*[ \t]+){{1,4}}?{specimen_head}\b");
        // Retain the metric with its reading. A number on its own has no useful identity.
        let metric = r"(?:temperature|pressure|length|width|mass|voltage|current|resistance|frequency|intensity|speed|humidity|diameter|thickness|density)";
        let quantity = r"[-+−]?\d+(?:[.,]\d+)?[ \t]*(?:[kMmunµμ]?(?:Pa|V|A|Hz|g|m|N|W)|°[CF]|%|Ω)";
        let quotes = r#"["“](?P<label>[^"”\r\n]{1,70})["”]"#;
        let patterns = [
            (
                INSTRUMENT,
                format!(r"(?i)\b(?:used|using|with|under|on|in|operated)[ \t]+{det}(?P<label>{instrument_name})"),
            ),
            (
                INSTRUMENT,
                format!(r"(?i)\b(?:used|operated)[ \t]+{det}(?:instrument|device)[ \t]+(?:named|called)[ \t]+{quotes}"),
            ),
            (
                INSTRUMENT,
                format!(r"(?i)^(?:{det})(?P<label>{instrument_name})[ \t]+(?:was|were)[ \t]+(?:used|operated)\b"),
            ),
            (
                INSTRUMENT,
                format!(r"(?:使用|采用|借助|用)(?:了)?\s*(?:一[台支个])?\s*(?P<label>[\p{{Han}}A-Za-z0-9-]{{0,15}}?{zh_device}{model_id})"),
            ),
            (
                REAGENT,
                format!(r"(?i)\b(?:added|mixed with|rinsed with|washed with|diluted with|used|using)[ \t]+{amount}{det}(?P<label>{})", phrase(material)),
            ),
            (
                REAGENT,
                format!(r"(?i)^{det}(?P<label>{})[ \t]+(?:was|were)[ \t]+(?:added|used)\b", phrase(material)),
            ),
            (
                REAGENT,
                format!(r"(?:加入|添加|混入|使用|用)(?:了)?\s*(?P<label>[\p{{Han}}A-Za-z-]{{0,12}}?{zh_material})"),
            ),
            (
                SAMPLE,
                format!(r"(?i)\b{specimen_action}[ \t]+{det}(?P<label>{material_specimen})"),
            ),
            (
                SAMPLE,
                format!(r"(?i)^{det}(?P<label>{material_specimen})[ \t]+(?:was|were)[ \t]+{specimen_action}\b"),
            ),
            (
                SAMPLE,
                r"(?:对|将|把)\s*(?P<label>(?:样本|样品|试样|标本)\s*(?:[A-Za-z][A-Za-z0-9_-]*|\d+[A-Za-z]?))\s*(?:进行(?:了)?|做了)?(?:检测|测量|检查|观察|称量)".to_owned(),
            ),
            (
                SAMPLE,
                format!(r"(?i:\b(?:tested|measured|examined|inspected|weighed|collected|scanned|analyzed|analysed|used)[ \t]+{det})(?P<label>{sample})"),
            ),
            (
                SAMPLE,
                format!(r"^(?i:{det})(?P<label>{sample})(?i:[ \t]+(?:was|were)[ \t]+(?:tested|examined|measured|weighed|scanned)\b)"),
            ),
            (
                SAMPLE,
                r"(?:检测|测量|检查|观察|取用|称量|使用|取)(?:了)?\s*(?P<label>(?:样品|样本|试样|标本)\s*(?:[A-Za-z][A-Za-z0-9_-]*|\d+[A-Za-z]?))".to_owned(),
            ),
            (
                RESULT,
                r"(?i)\b(?:we|i)[ \t]+(?:observed|obtained|recorded|found)[ \t]+(?:that[ \t]+)?(?P<label>[^;!?。！？]{2,120})$".to_owned(),
            ),
            (
                RESULT,
                r"(?:观察到|测得|测量结果显示|检测结果显示)\s*(?P<label>[^；;。！？!?]{2,90})$".to_owned(),
            ),
            (
                RESULT,
                format!(r"(?i)(?P<label>\b(?:the[ \t]+)?{metric}[ \t]+(?:reached|rose to|fell to|stabili[sz]ed at|increased to|decreased to)[ \t]+{quantity})(?:$|[ ,])"),
            ),
            (
                RESULT,
                format!(r"(?P<label>(?:温度|压力|长度|宽度|质量|电压|电流|频率|强度|速度|湿度|直径|厚度|密度)(?:上升到|升至|降至|稳定在|达到)\s*{quantity})"),
            ),
        ];
        patterns
            .into_iter()
            .map(|(fact_type, pattern)| Rule {
                fact_type,
                pattern: Regex::new(&pattern).expect("valid prose extraction rule"),
            })
            .collect()
    })
}

fn asserted_action(sentence: &str) -> bool {
    static ACTION: OnceLock<Regex> = OnceLock::new();
    // A preposition or participle alone can describe inventory, instructions, or a method.
    let regex = ACTION.get_or_init(|| Regex::new(concat!(
        r"(?i)(?:^|\b(?:i|we|they|he|she|team|operator|technician|researcher|run|trial|was|were|and|then)[ \t]+)",
        r"(?:(?:also|then|subsequently|carefully)[ \t]+)?",
        r"(?:used|operated|tested|measured|examined|inspected|weighed|collected|scanned|analy[sz]ed|added|mixed|rinsed|washed|diluted|observed|obtained|recorded|found|monitored|checked|imaged|prepared|processed)\b",
        r"|使用|采用|借助|用|加入|添加|混入|检测|测量|检查|观察|称量|取样|取试样|取标本|测得|实测"
    )).expect("valid action assertion"));
    regex.is_match(sentence)
}

fn labeled_field(sentence: &str) -> bool {
    static FIELD: OnceLock<Regex> = OnceLock::new();
    FIELD.get_or_init(||Regex::new(r"(?i)^\s*(?:reagents?|instruments?|samples?|results?|试剂|材料|药品|仪器|设备|样本|样品|结果|观察|结论)\s*[:：]").expect("valid field marker")).is_match(sentence)
}

fn excluded(sentence: &str) -> bool {
    static NON_FACT: OnceLock<Regex> = OnceLock::new();
    NON_FACT
        .get_or_init(|| Regex::new(concat!(
            r"(?i)\b(?:no|not|never|without|cannot|failed|failure|",
            r"plan|plans|planned|planning|intend|intends|intended|proposed|",
            r"would|could|might|should|may|will|if|unless|whether|expected|protocol|",
            r"recommended|reported|suggested|tried|attempted|told|requested|imagined|",
            r"mentioned|wrote|said|claimed|quoted|manual|literature|instructions?|example|catalog(?:ue)?)\b",
            r"|n['’]t\b|[?？]",
            r"|手册|示例|范例|说明书|写道|要求|引用|请|将使用|将用|将采用|将加入|将添加",
            r"|未|没有|并非|并不|无需|不曾|不使用|不再|不得|不应|不能|不宜|无法|失败",
            r"|拟|计划|预计|预期|打算|将要|准备使用|建议|可能|如果|若|假如|是否|据称|文献"
        )).expect("valid non-assertion markers"))
        .is_match(sentence)
}

fn plausible_label(label: &str) -> bool {
    static BOUNDARY: OnceLock<Regex> = OnceLock::new();
    !BOUNDARY
        .get_or_init(|| {
            Regex::new(concat!(
                r"(?i)\b(?:and|or|but|the|with|from|to|for|on|of|in|was|were|",
                r"we|they|then|used|using|did|our|some|no|not|any)\b",
                r"|使用|加入|之后|并且|以及|但是|然后|或者|改用|未|没有|需要|是否|[，,]"
            ))
            .expect("valid phrase boundaries")
        })
        .is_match(label)
}

fn observed_absence(assertion: &str) -> Option<&str> {
    static ABSENCE: OnceLock<Regex> = OnceLock::new();
    let pattern = ABSENCE.get_or_init(|| Regex::new(concat!(
        r"(?i)^(?:we|i)[ \t]+(?:observed|found|recorded|saw)[ \t]+(?P<en>no[ \t]+[^,;!?。；，！？]+)$",
        r"|^(?P<passive>no[ \t]+[^,;!?。；，！？]+?)[ \t]+(?:was|were)[ \t]+(?:detected|observed|found)$",
        r"|^(?:本次(?:检测|检查|测量)|实际(?:检测|检查))?(?P<zh>未(?:发现|见|检测到|观察到)[^,;!?。；，！？]+)$"
    )).expect("valid observed absence"));
    let m = pattern.captures(assertion)?;
    let label = m
        .name("en")
        .or_else(|| m.name("passive"))
        .or_else(|| m.name("zh"))?
        .as_str();
    let rest = label.strip_prefix('未').unwrap_or_else(|| &label[2..]);
    (!excluded(rest)).then_some(label)
}

fn push_fact(fact_type: FactType, label: &str, sentence: &str, out: &mut Vec<ExtractedTerm>) {
    let mut item = term(fact_type.0, fact_type.1, label.to_owned(), None);
    item.method = "local_prose";
    item.evidence = Some(sentence.to_owned());
    out.push(item);
}

pub(super) fn collect(parts: &[&str], out: &mut Vec<ExtractedTerm>) {
    for line in context::lines(parts) {
        let sentence = line.text;
        if sentence.len() > 9_600 || labeled_field(sentence) {
            continue;
        }
        let assertion = context::assertion(sentence);
        if let Some(kind) = line.list {
            let label = assertion
                .trim_start_matches(['-', '*', '•', '·', '–'])
                .trim();
            if !label.is_empty() {
                push_fact(kind, label, sentence, out);
            }
            continue;
        }
        if excluded(sentence) {
            if let Some(label) = observed_absence(assertion) {
                push_fact(RESULT, label, sentence, out);
            }
            continue;
        }
        let completed = asserted_action(assertion);
        let mut found_outcome = false;
        for rule in rules() {
            if (rule.fact_type != RESULT && !completed)
                || (rule.fact_type == RESULT && found_outcome)
            {
                continue;
            }
            for m in rule.pattern.captures_iter(assertion) {
                let label = m["label"].trim();
                if label.is_empty() || (rule.fact_type != RESULT && !plausible_label(label)) {
                    continue;
                }
                push_fact(rule.fact_type, label, sentence, out);
                found_outcome |= rule.fact_type == RESULT;
            }
        }
    }
}
