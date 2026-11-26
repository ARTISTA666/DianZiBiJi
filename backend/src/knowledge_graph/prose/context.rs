//! Keep the written context of ordinary notebook statements and lists.
use super::{
    asserted_action, excluded, observed_absence, FactType, INSTRUMENT, REAGENT, RESULT, SAMPLE,
};
use regex::Regex;
use std::sync::LazyLock;

pub(in crate::knowledge_graph) struct Line<'a> {
    pub(in crate::knowledge_graph) text: &'a str,
    pub(super) list: Option<FactType>,
}

#[derive(Clone, Copy)]
enum Section {
    Record,
    Excluded,
    Used(FactType),
}

static INVENTORY: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(concat!(
    r"(?i)\b(?:inventory|stock list|in stock|on hand|available equipment|equipment available|",
    r"supplies available|available instruments|spare equipment|stored in the (?:cabinet|store)|",
    r"was available|were available|catalogue|catalog)\b|库存|库房清单|物品清单|备品清单|备选设备|备用器材|在库|仅供选择"
)).expect("valid inventory markers")
});

static BLOCKED_TITLE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(concat!(
        r"(?i)\b(?:manual|handbook|instructions?|protocol|quoted|example|example entry|",
        r"future|next (?:run|session|test)|plans?|planned|to.do|wishlist|proposed)\b|",
        r"手册|引文|引用|说明书|操作说明|待办|拟用|下次|计划|方案示例|示例|待测项目|备用"
    ))
    .expect("valid excluded section titles")
});

static ACTUAL: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(concat!(
    r"(?i)\b(?:actually (?:used|measured|tested|recorded)|(?:in|during|for) this (?:run|test|session)|",
    r"this (?:run|trial) used|(?:actual|observed|measured) (?:results?|observations?|readings?))\b|",
    r"本次(?:实际|使用|测量|观察|检测|检查)|实际(?:使用|观测|测量|记录|结果)|实测"
)).expect("valid completed-run markers")
});

static USED: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
    r"(?i)\b(?:used|tested|consumed|observed|recorded|measured)\b|本次用|使用|用到|所用|耗用|已测|实测|观测"
).expect("valid actual-list declarations")
});

static CONTRAST: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(?:,\s*(?:but|however|whereas)\s+|[，,]\s*(?:但(?:是)?|而(?:本次|实际)))")
        .expect("valid contrast boundaries")
});

fn section(title: &str) -> Section {
    if INVENTORY.is_match(title) || BLOCKED_TITLE.is_match(title) {
        return Section::Excluded;
    }
    if USED.is_match(title) {
        let t = title.to_ascii_lowercase();
        for (kind, words) in [
            (
                INSTRUMENT,
                &[
                    "instrument",
                    "device",
                    "equipment",
                    "tool",
                    "仪器",
                    "设备",
                    "工具",
                ][..],
            ),
            (
                REAGENT,
                &["reagent", "material", "consumable", "试剂", "材料", "耗材"][..],
            ),
            (
                SAMPLE,
                &["sample", "specimen", "样品", "样本", "试样", "标本"][..],
            ),
            (
                RESULT,
                &["result", "observation", "reading", "结果", "观测", "读数"][..],
            ),
        ] {
            if words.iter().any(|w| t.contains(w)) {
                return Section::Used(kind);
            }
        }
    }
    Section::Record
}

pub(super) fn assertion(text: &str) -> &str {
    text.trim_end_matches(['.', '。', '!', '！', ';', '；'])
        .trim()
}

pub(in crate::knowledge_graph) fn candidate_allowed(
    evidence: &str,
    label: &str,
    kind: &str,
) -> bool {
    if is_heading(evidence) || inventory_only(evidence) {
        return false;
    }
    if !excluded(evidence) {
        return true;
    }
    kind == "result"
        && observed_absence(assertion(evidence)).is_some_and(|finding| label.contains(finding))
}

fn inventory_only(text: &str) -> bool {
    let Some(marker) = INVENTORY.find(text) else {
        return false;
    };
    // An inventory can be named as the source of a tool that was actually used.
    // An inventory entry with a tool's name alone never establishes use.
    !(asserted_action(&text[..marker.start()])
        || ACTUAL.is_match(text) && asserted_action(text) && !excluded(text))
}

fn list_item(line: &str) -> bool {
    line.starts_with(['-', '*', '•', '·', '–'])
        || line.split_once(['.', '、']).is_some_and(|(n, _)| {
            !n.is_empty() && n.len() <= 3 && n.bytes().all(|b| b.is_ascii_digit())
        })
}

fn is_heading(line: &str) -> bool {
    line.ends_with([':', '：'])
        || line.starts_with('#')
        || (!line.contains(['.', '。', '!', '！', '?', '？', ';', '；'])
            && line.chars().count() <= 64
            && (BLOCKED_TITLE.is_match(line) || INVENTORY.is_match(line)))
}

fn accept<'a>(raw: &'a str, state: &mut Section, out: &mut Vec<Line<'a>>) {
    let text = raw.trim();
    if text.is_empty() || text.starts_with('>') {
        return;
    }
    let prefix = text.split_once([':', '：']).map(|(a, _)| a).unwrap_or(text);
    // Inventory/plan headers may carry their first item on the same line.
    if (is_heading(text) || text.contains([':', '：']))
        && matches!(section(prefix), Section::Excluded)
    {
        *state = Section::Excluded;
        return;
    }
    if is_heading(text) {
        let next = section(prefix);
        if matches!(state, Section::Excluded)
            && matches!(next, Section::Record)
            && !ACTUAL.is_match(prefix)
        {
            return;
        }
        *state = next;
        out.push(Line { text, list: None });
        return;
    }
    let bullet = list_item(text);
    let completed = asserted_action(text)
        || ACTUAL.is_match(text)
        || observed_absence(assertion(text)).is_some();
    if inventory_only(text) {
        return;
    }
    if matches!(state, Section::Excluded) {
        // Bare names and bullets inherit the heading. A separate, completed act
        // in the record starts a new narrative even without a formal heading.
        if bullet || !completed || excluded(text) && observed_absence(assertion(text)).is_none() {
            return;
        }
        *state = Section::Record;
    }
    let list = match *state {
        Section::Used(kind)
            if !completed
                && !excluded(text)
                && !text.contains([':', '：', '?', '？'])
                && text.chars().count() <= 90
                && (bullet || !text.ends_with(['.', '。', '!', '！'])) =>
        {
            Some(kind)
        }
        _ => None,
    };
    if completed {
        *state = Section::Record;
    }
    out.push(Line { text, list });
}

fn segments<'a>(part: &'a str, state: &mut Section, out: &mut Vec<Line<'a>>) {
    let mut start = 0;
    let mut chars = part.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        let boundary = matches!(c, '\n' | '。' | '！' | '？' | '!' | '?' | ';' | '；')
            || c == '.' && chars.peek().is_none_or(|(_, n)| n.is_whitespace());
        if boundary || chars.peek().is_none() {
            let end = i + c.len_utf8();
            for clause in CONTRAST.split(&part[start..end]) {
                accept(clause, state, out);
            }
            start = end;
        }
    }
}

pub(in crate::knowledge_graph) fn lines<'a>(parts: &[&'a str]) -> Vec<Line<'a>> {
    let mut state = Section::Record;
    let mut open_quote = None;
    let mut out = Vec::new();
    for &part in parts {
        let mut rest = part;
        if let Some(close) = open_quote {
            let Some((_, after)) = rest.split_once(close) else {
                continue;
            };
            rest = after;
            open_quote = None;
        }
        let mut allowed = 0;
        let mut scan = 0;
        while let Some((offset, opener)) = rest[scan..]
            .char_indices()
            .find(|(_, c)| matches!(c, '“' | '"' | '「' | '『'))
        {
            let left = scan + offset;
            let close = match opener {
                '“' => '”',
                '「' => '」',
                '『' => '』',
                _ => '"',
            };
            let inner = left + opener.len_utf8();
            if opener == '"'
                && rest[..left]
                    .chars()
                    .next_back()
                    .is_some_and(|v| v.is_ascii_digit())
            {
                scan = inner;
                continue;
            }
            let Some(end) = rest[inner..].find(close) else {
                segments(&rest[allowed..left], &mut state, &mut out);
                open_quote = Some(close);
                allowed = rest.len();
                break;
            };
            let quoted = &rest[inner..inner + end];
            scan = inner + end + close.len_utf8();
            if asserted_action(quoted)
                || excluded(quoted)
                || quoted.contains(['。', '！', '？', '?', '!', ';', '；', '\n'])
                || quoted.ends_with('.')
                || quoted.split_whitespace().count() > 8
            {
                segments(&rest[allowed..left], &mut state, &mut out);
                allowed = scan;
            }
        }
        segments(&rest[allowed..], &mut state, &mut out);
    }
    out
}

/// Keep original separators between adjacent eligible spans. A removed block
/// becomes a newline so two independent fields cannot be accidentally joined.
pub(in crate::knowledge_graph) fn filtered_prefix_text(original: &str) -> String {
    let mut text = String::new();
    let mut prev = 0;
    for line in lines(&[original]) {
        let start = line.text.as_ptr() as usize - original.as_ptr() as usize;
        let gap = &original[prev..start];
        if gap.chars().all(char::is_whitespace) {
            text.push_str(gap);
        } else {
            text.push('\n');
        }
        text.push_str(line.text);
        prev = start + line.text.len();
    }
    text
}
