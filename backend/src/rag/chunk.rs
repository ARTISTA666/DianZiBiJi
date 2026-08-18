// 文本切分：按段落/句子边界把文档切成带重叠的 chunk。

pub(crate) fn chunk_text(text: &str, chunk_size: usize, overlap: usize) -> Vec<String> {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    let trimmed = normalized.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    let size = chunk_size.max(200);
    let overlap_chars = overlap.min(size / 2);

    // 先按段落拆分，再将短段落合并到 chunk_size 以内，超长段落按句子边界切分。
    let paragraphs: Vec<&str> = trimmed
        .split("\n\n")
        .map(|p| p.trim())
        .filter(|p| !p.is_empty())
        .collect();
    if paragraphs.is_empty() {
        return Vec::new();
    }

    let mut chunks: Vec<String> = Vec::new();
    let mut current = String::new();

    for para in paragraphs {
        // 段落本身超过 chunk_size：按句子边界切分
        if para.chars().count() > size {
            // 先把已累积的内容输出
            if !current.is_empty() {
                chunks.push(current.trim().to_owned());
                current.clear();
            }
            for sentence_chunk in split_long_text(para, size, overlap_chars) {
                chunks.push(sentence_chunk);
            }
            continue;
        }

        // 合并短段落
        let candidate = if current.is_empty() {
            para.to_owned()
        } else {
            format!("{current}\n\n{para}")
        };
        if candidate.chars().count() > size && !current.is_empty() {
            chunks.push(current.trim().to_owned());
            current = para.to_owned();
        } else {
            current = candidate;
        }
    }
    if !current.is_empty() {
        chunks.push(current.trim().to_owned());
    }

    // 重叠：为每个 chunk 添加前一个 chunk 尾部的 overlap 文本
    if overlap_chars > 0 && chunks.len() > 1 {
        let mut overlapped = Vec::with_capacity(chunks.len());
        overlapped.push(chunks[0].clone());
        for i in 1..chunks.len() {
            let prev_tail: String = chunks[i - 1]
                .chars()
                .rev()
                .take(overlap_chars)
                .collect::<String>()
                .chars()
                .rev()
                .collect();
            overlapped.push(format!("{}\n{}", prev_tail, chunks[i]));
        }
        return overlapped;
    }

    chunks
}

/// 按句子边界切分超长文本。优先在句号/问号/叹号处断开。
fn split_long_text(text: &str, max_size: usize, overlap: usize) -> Vec<String> {
    let sentence_ends: &[char] = &['.', '?', '!', '。', '？', '！', '\n'];
    let chars: Vec<char> = text.chars().collect();
    let mut chunks = Vec::new();
    let mut start = 0;

    while start < chars.len() {
        let ideal_end = (start + max_size).min(chars.len());
        if ideal_end >= chars.len() {
            let chunk: String = chars[start..].iter().collect::<String>().trim().to_owned();
            if !chunk.is_empty() {
                chunks.push(chunk);
            }
            break;
        }
        // 从 ideal_end 向前找句子边界
        let mut end = ideal_end;
        for i in (start..ideal_end).rev() {
            if sentence_ends.contains(&chars[i]) {
                end = i + 1;
                break;
            }
        }
        // 如果找不到句子边界（超长无标点段落），回退到 ideal_end
        if end == start {
            end = ideal_end;
        }
        let chunk: String = chars[start..end]
            .iter()
            .collect::<String>()
            .trim()
            .to_owned();
        if !chunk.is_empty() {
            chunks.push(chunk);
        }
        // 必须保证 start 严格前进：当句子边界恰好落在“窗口起点 + overlap”处时，
        // end - overlap 会等于原 start，导致窗口原地踏步并无限循环（内存无限增长直到 OOM）。
        // 正常情况保留 overlap 语义，极端情况至少前进一个字符。
        start = (end.saturating_sub(overlap)).max(start + 1);
        if start >= chars.len() {
            break;
        }
        // 避免死循环
        if end >= chars.len() {
            break;
        }
    }
    chunks
}

#[cfg(test)]
mod tests {
    use super::{chunk_text, split_long_text};

    #[test]
    fn test_chunk_text_respects_paragraph_boundaries() {
        let text = "第一段内容。\n\n第二段内容。\n\n第三段内容。";
        let chunks = chunk_text(text, 500, 0);
        // 短段落应合并为一个 chunk
        assert_eq!(chunks.len(), 1);
        assert!(chunks[0].contains("第一段"));
        assert!(chunks[0].contains("第三段"));
    }

    #[test]
    fn test_chunk_text_splits_long_paragraphs_at_sentence_boundary() {
        let sentence = "这是一句很长的话。";
        let text = format!(
            "{}{}{}",
            sentence.repeat(20),
            sentence.repeat(20),
            sentence.repeat(20)
        );
        let chunks = chunk_text(&text, 100, 0);
        assert!(chunks.len() > 1);
        // 每个 chunk 应以句子边界结束（以句号结尾或达到末尾）
        for chunk in &chunks {
            assert!(chunk.ends_with('。') || chunk.ends_with('。'));
        }
    }

    #[test]
    fn test_split_long_text_terminates_when_sentence_end_falls_at_window_start() {
        // 回归：当段落中最后一个句子边界恰好位于“窗口起点 + overlap”处时，
        // 旧实现 end - overlap 会等于原 start，窗口原地踏步形成无限循环（OOM）。
        // 首窗口 [0,700) 内最后一个 '.' 位于位置 119 -> end=120 -> start'=120-120=0。
        let segment = format!("{}x.", "x".repeat(118));
        let text = segment.repeat(6) + &"y".repeat(600);
        let chunks = split_long_text(&text, 700, 120);
        assert!(!chunks.is_empty());
        let joined: usize = chunks.iter().map(|chunk| chunk.chars().count()).sum();
        assert!(joined >= text.chars().count());
    }

    #[test]
    fn test_split_long_text_at_sentence_boundaries() {
        let text = "第一句话。第二句话。第三句话。第四句话。第五句话。";
        let chunks = split_long_text(text, 15, 0);
        assert!(chunks.len() > 1);
    }
}
