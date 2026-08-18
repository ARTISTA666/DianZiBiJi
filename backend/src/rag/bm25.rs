// BM25 词法检索：科研术语同义词扩展、分词与 BM25 评分。

use std::{
    collections::{HashMap, HashSet},
    sync::OnceLock,
};

use regex::Regex;

use super::retrieval::ChunkRow;

/// 科研术语同义词表：将常见缩写/全称互相扩展，提升 BM25 召回率。
static QUERY_SYNONYMS: OnceLock<HashMap<&'static str, Vec<&'static str>>> = OnceLock::new();

fn query_synonyms() -> &'static HashMap<&'static str, Vec<&'static str>> {
    QUERY_SYNONYMS.get_or_init(|| {
        let mut m = HashMap::new();
        // 分子生物学
        m.insert(
            "pcr",
            vec![
                "聚合酶链反应",
                "polymerase chain reaction",
                "rt-pcr",
                "qpcr",
            ],
        );
        m.insert("聚合酶链反应", vec!["pcr", "rt-pcr", "qpcr"]);
        m.insert("rt-pcr", vec!["pcr", "逆转录", "reverse transcription"]);
        m.insert("wb", vec!["western blot", "蛋白质印迹", "免疫印迹"]);
        m.insert("western blot", vec!["wb", "蛋白质印迹", "免疫印迹"]);
        m.insert("elisa", vec!["酶联免疫吸附", "enzyme-linked immunosorbent"]);
        // 细胞生物学
        m.insert("cck8", vec!["cck-8", "细胞活力检测", "cell counting kit"]);
        m.insert("cck-8", vec!["cck8", "细胞活力检测", "cell counting kit"]);
        m.insert("dmem", vec!["培养基", "dulbecco", "细胞培养"]);
        m.insert("fbs", vec!["胎牛血清", "fetal bovine serum", "血清"]);
        m.insert("pbs", vec!["磷酸盐缓冲液", "phosphate buffered saline"]);
        // 组学
        m.insert("rna-seq", vec!["转录组", "rna sequencing", "基因表达"]);
        m.insert("转录组", vec!["rna-seq", "rna sequencing", "基因表达"]);
        m.insert("htseq", vec!["rna-seq", "转录组", "基因计数"]);
        m.insert("geo", vec!["gene expression omnibus", "基因表达数据库"]);
        // 通用实验
        m.insert("od", vec!["光密度", "optical density", "吸光度"]);
        m.insert("光密度", vec!["od", "optical density", "吸光度"]);
        m
    })
}

/// 扩展查询文本：为原始查询添加同义词，提升 BM25 召回率。
/// 仅对 BM25 检索生效，不影响向量检索和 LLM prompt。
pub fn bm25_expansion_terms(query: &str) -> Vec<String> {
    let synonyms = query_synonyms();
    let lower = query.to_lowercase();
    let mut extra_terms = HashSet::new();
    for (term, syns) in synonyms.iter() {
        if lower.contains(term) {
            for syn in syns {
                if !lower.contains(&syn.to_lowercase()) {
                    extra_terms.insert((*syn).to_owned());
                }
            }
        }
    }
    let mut extra_terms = extra_terms.into_iter().collect::<Vec<_>>();
    extra_terms.sort();
    extra_terms
}

pub fn expand_query_for_bm25(query: &str) -> String {
    let extra_terms = bm25_expansion_terms(query);
    if extra_terms.is_empty() {
        query.to_owned()
    } else {
        format!("{} {}", query, extra_terms.join(" "))
    }
}

pub(crate) fn token_regex() -> &'static Regex {
    static TOKEN_REGEX: OnceLock<Regex> = OnceLock::new();
    TOKEN_REGEX.get_or_init(|| Regex::new(r"(?i)[a-z0-9_µ><=./-]+|[\p{Han}]+").unwrap())
}

fn token_frequencies(text: &str) -> HashMap<String, usize> {
    let mut frequencies = HashMap::new();
    for matched in token_regex().find_iter(text) {
        let token = matched.as_str().to_lowercase();
        *frequencies.entry(token.clone()).or_insert(0) += 1;
        if token
            .chars()
            .all(|character| ('\u{4e00}'..='\u{9fff}').contains(&character))
        {
            let chars: Vec<char> = token.chars().collect();
            for window in chars.windows(2) {
                *frequencies.entry(window.iter().collect()).or_insert(0) += 1;
            }
        }
    }
    frequencies
}

pub(crate) fn tokens(text: &str) -> HashSet<String> {
    token_frequencies(text).into_keys().collect()
}

/// 仅被测试与图谱评分实验使用：生产检索已改为候选循环外预计算词集。
#[cfg(test)]
pub(crate) fn exact_token_overlap(query_tokens: &HashSet<String>, text: &str) -> usize {
    let text_tokens = tokens(text);
    query_tokens.intersection(&text_tokens).count()
}

pub(crate) fn bm25_scores(rows: &[ChunkRow], query: &str) -> HashMap<i32, f64> {
    if rows.is_empty() {
        return HashMap::new();
    }
    let query_terms = token_frequencies(query);
    if query_terms.is_empty() {
        return rows.iter().map(|row| (row.id, 0.0)).collect();
    }
    let documents: Vec<HashMap<String, usize>> = rows
        .iter()
        .map(|row| token_frequencies(&row.content))
        .collect();
    let mut document_frequency = HashMap::<String, usize>::new();
    for document in &documents {
        for term in document.keys() {
            *document_frequency.entry(term.clone()).or_insert(0) += 1;
        }
    }
    let average_document_length = documents
        .iter()
        .map(|document| document.values().sum::<usize>() as f64)
        .sum::<f64>()
        / documents.len() as f64;
    let document_count = rows.len() as f64;
    let scores = rows.iter().zip(documents).map(|(row, document)| {
        let document_length = document.values().sum::<usize>() as f64;
        let raw_score = query_terms.keys().fold(0.0, |score, term| {
            let Some(&term_frequency) = document.get(term) else {
                return score;
            };
            let document_frequency = document_frequency.get(term).copied().unwrap_or_default();
            let idf = ((document_count - document_frequency as f64 + 0.5)
                / (document_frequency as f64 + 0.5)
                + 1.0)
                .ln();
            let normalized_length = document_length / average_document_length.max(1.0);
            let denominator = term_frequency as f64 + 1.2 * (1.0 - 0.75 + 0.75 * normalized_length);
            score + idf * (term_frequency as f64 * 2.2) / denominator
        });
        (row.id, raw_score / (raw_score + 1.0))
    });
    scores.collect()
}

#[cfg(test)]
mod tests {
    use super::{
        bm25_expansion_terms, bm25_scores, exact_token_overlap, expand_query_for_bm25, tokens,
    };
    use crate::rag::retrieval::ChunkRow;

    #[test]
    fn test_expand_query_adds_synonyms() {
        let expanded = expand_query_for_bm25("PCR 实验条件");
        assert!(expanded.contains("聚合酶链反应"));
        assert!(expanded.contains("PCR"));
    }

    #[test]
    fn test_expand_query_no_duplicate_synonyms() {
        let expanded = expand_query_for_bm25("已经包含聚合酶链反应的内容");
        // 原文已含同义词，不应重复添加
        assert_eq!(expanded.matches("聚合酶链反应").count(), 1);
    }

    #[test]
    fn test_expand_query_no_match_returns_original() {
        let expanded = expand_query_for_bm25("今天天气怎么样");
        assert_eq!(expanded, "今天天气怎么样");
    }

    #[test]
    fn test_bm25_expansion_terms_are_sorted_and_deduplicated() {
        let terms = bm25_expansion_terms("PCR rt-PCR");
        let mut sorted_unique = terms.clone();
        sorted_unique.sort();
        sorted_unique.dedup();
        assert_eq!(terms, sorted_unique);
        assert_eq!(terms, bm25_expansion_terms("rt-PCR PCR"));
    }

    #[test]
    fn test_bm25_prioritizes_rare_terms_over_common_term_frequency() {
        let rows = vec![
            ChunkRow {
                id: 1,
                file_id: 1,
                filename: "common.txt".to_owned(),
                file_hash: "file-1".to_owned(),
                chunk_index: 0,
                content_hash: "content-1".to_owned(),
                content: "common ".repeat(12),
            },
            ChunkRow {
                id: 2,
                file_id: 2,
                filename: "rare.txt".to_owned(),
                file_hash: "file-2".to_owned(),
                chunk_index: 0,
                content_hash: "content-2".to_owned(),
                content: "common raremarker".to_owned(),
            },
        ];

        let scores = bm25_scores(&rows, "common raremarker");

        assert!(scores[&2] > scores[&1]);
        assert!(scores[&2] <= 1.0);
    }

    #[test]
    fn test_graph_matching_uses_exact_tokens() {
        assert_eq!(exact_token_overlap(&tokens("cell"), "cellular culture"), 0);
        assert_eq!(exact_token_overlap(&tokens("cell"), "cell culture"), 1);
    }
}
