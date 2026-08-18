// 引用审计：校验回答中的 [S]/[G] 证据编号，并清洗提示词模板占位符。

use regex::Regex;

use crate::models::RagCitationAuditRead;

pub fn audit_citations(
    answer: &str,
    source_count: usize,
    graph_count: usize,
) -> RagCitationAuditRead {
    let regex = Regex::new(r"(?i)\[([SG])([^\]]*)\]").unwrap();
    let citations: Vec<(String, Option<usize>, String)> = regex
        .captures_iter(answer)
        .map(|capture| {
            let kind = capture[1].to_uppercase();
            let raw_index = capture[2].to_owned();
            let index = raw_index
                .chars()
                .all(|character| character.is_ascii_digit())
                .then(|| raw_index.parse::<usize>().ok())
                .flatten();
            let marker = format!("[{kind}{raw_index}]");
            (kind, index, marker)
        })
        .collect();
    let invalid_citations: Vec<String> = citations
        .iter()
        .filter_map(|(kind, index, marker)| {
            let limit = if kind == "S" {
                source_count
            } else {
                graph_count
            };
            (!index.is_some_and(|index| (1..=limit).contains(&index))).then(|| marker.clone())
        })
        .collect();
    let has_evidence = source_count > 0 || graph_count > 0;
    let passed = invalid_citations.is_empty() && (!citations.is_empty() || !has_evidence);
    let message = if !invalid_citations.is_empty() {
        format!(
            "发现 {} 个不存在的证据编号：{}。",
            invalid_citations.len(),
            invalid_citations.join("、")
        )
    } else if has_evidence && citations.is_empty() {
        "回答没有引用任何已检索证据，需要人工复核。".to_owned()
    } else if !citations.is_empty() {
        format!("引用校验通过，共核对 {} 个证据编号。", citations.len())
    } else {
        "该回答没有可引用的项目证据。".to_owned()
    };
    RagCitationAuditRead {
        passed,
        citation_count: citations.len(),
        invalid_citations,
        has_evidence,
        message,
        repair_attempted: false,
    }
}

pub fn audit_citations_after_repair(
    answer: &str,
    source_count: usize,
    graph_count: usize,
) -> RagCitationAuditRead {
    let mut audit = audit_citations(answer, source_count, graph_count);
    audit.repair_attempted = true;
    audit
}

/// Remove prompt-template citation placeholders such as `[S编号]` / `[G编号]`
/// from a generated answer before citation auditing.
///
/// The prompt uses these bracketed forms to describe the required citation
/// syntax, but a model may echo the placeholder itself in a meta-sentence
/// (for example "未提供对应的 [G编号]"). Such text is not a citation and must
/// not be counted as an invalid evidence marker, otherwise one formatting echo
/// makes an otherwise auditable experiment case fail the whole evidence
/// package. We keep `S编号` / `G编号` as plain text so the sentence remains
/// readable without turning the placeholder into a fake citation.
pub fn strip_citation_template_placeholders(answer: &str) -> String {
    let regex = Regex::new(r"(?i)\[([SG])\s*编号\]").unwrap();
    regex
        .replace_all(answer, |capture: &regex::Captures<'_>| {
            let kind = capture
                .get(1)
                .map(|matched| matched.as_str())
                .unwrap_or_default()
                .to_uppercase();
            format!("{kind}编号")
        })
        .into_owned()
}

#[cfg(test)]
mod tests {
    use super::{
        audit_citations, audit_citations_after_repair, strip_citation_template_placeholders,
    };

    #[test]
    fn test_citation_audit_rejects_overflowing_source_numbers() {
        let audit = audit_citations("Valid [S1], malformed [S999999999999999999999]", 1, 0);

        assert!(!audit.passed);
        assert_eq!(audit.invalid_citations, ["[S999999999999999999999]"]);
    }

    #[test]
    fn test_citation_audit_rejects_malformed_markers() {
        let audit = audit_citations("Valid [S1], malformed [S系统], [S1-S2] and [S+1]", 1, 0);

        assert!(!audit.passed);
        assert_eq!(audit.citation_count, 4);
        assert_eq!(audit.invalid_citations, ["[S系统]", "[S1-S2]", "[S+1]"]);
    }

    #[test]
    fn test_repaired_citation_audit_preserves_attempt_flag() {
        let audit = audit_citations_after_repair("Valid [S1]", 1, 0);

        assert!(audit.passed);
        assert!(audit.repair_attempted);
    }

    #[test]
    fn test_strip_citation_template_placeholders_removes_brackets_only() {
        assert_eq!(
            strip_citation_template_placeholders(
                "知识图谱上下文中未提供与该条记录直接对应的 [G编号]。[S2] 和 [G8] 保留。"
            ),
            "知识图谱上下文中未提供与该条记录直接对应的 G编号。[S2] 和 [G8] 保留。"
        );
        assert_eq!(
            strip_citation_template_placeholders("资料引用写作 [S编号]，图谱引用写作 [G编号]。"),
            "资料引用写作 S编号，图谱引用写作 G编号。"
        );
    }

    #[test]
    fn test_strip_citation_template_placeholders_is_case_insensitive_and_space_tolerant() {
        assert_eq!(
            strip_citation_template_placeholders("使用 [s 编号] 说明来源。"),
            "使用 S编号 说明来源。"
        );
    }

    #[test]
    fn test_stripped_template_placeholder_is_not_counted_as_invalid_citation() {
        let answer = strip_citation_template_placeholders("对应关系未提供 [G编号]。[S1] 有效。");
        let audit = audit_citations(&answer, 1, 0);

        assert!(audit.passed);
        assert_eq!(audit.invalid_citations, Vec::<String>::new());
    }
}
