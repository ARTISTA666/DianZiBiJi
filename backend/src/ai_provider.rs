use std::{future::Future, pin::Pin, sync::Arc, time::Duration};

use futures_util::StreamExt;
use reqwest::{Client, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use thiserror::Error;
use tokio::sync::Semaphore;
use tokio_stream::{wrappers::ReceiverStream, Stream};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub struct ProviderCapabilities {
    pub generation: bool,
    pub streaming: bool,
    pub tool_calling: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub input_schema: Value,
}

#[derive(Clone, Debug)]
pub struct GenerationRequest {
    pub system_prompt: String,
    pub user_prompt: String,
    pub temperature: f64,
    pub max_tokens: u32,
    pub tools: Vec<ToolDefinition>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ProviderToolCall {
    pub id: String,
    pub name: String,
    pub arguments: Value,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct UnifiedUsage {
    pub prompt_tokens: Option<u64>,
    pub completion_tokens: Option<u64>,
    pub total_tokens: Option<u64>,
    pub generation_attempts: usize,
}

#[derive(Clone, Debug)]
pub struct GenerationResult {
    pub answer: String,
    pub request_id: Option<String>,
    pub model: String,
    /// Compatibility shape used by existing query/run logs.
    pub usage: Value,
    pub normalized_usage: UnifiedUsage,
    pub tool_calls: Vec<ProviderToolCall>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct GenerationDelta {
    pub content: String,
    pub done: bool,
    pub usage: Option<UnifiedUsage>,
}

pub type GenerationStream =
    Pin<Box<dyn Stream<Item = Result<GenerationDelta, GenerationError>> + Send>>;

#[derive(Debug, Error)]
pub enum GenerationError {
    #[error("{0}")]
    Configuration(String),
    #[error("{0}")]
    Request(String),
}

pub trait AiProvider: Send + Sync {
    fn provider_name(&self) -> &str;
    fn model(&self) -> &str;
    fn capabilities(&self) -> ProviderCapabilities;
    fn generate<'a>(
        &'a self,
        request: GenerationRequest,
    ) -> Pin<Box<dyn Future<Output = Result<GenerationResult, GenerationError>> + Send + 'a>>;
    fn generate_stream<'a>(
        &'a self,
        request: GenerationRequest,
    ) -> Pin<Box<dyn Future<Output = Result<GenerationStream, GenerationError>> + Send + 'a>>;
}

#[derive(Clone)]
pub struct OpenAiCompatibleProvider {
    client: Client,
    provider_name: String,
    base_url: String,
    api_key: String,
    model: String,
    limiter: Arc<Semaphore>,
}

impl OpenAiCompatibleProvider {
    pub fn new(
        client: Client,
        base_url: String,
        api_key: String,
        model: String,
        max_concurrency: usize,
    ) -> Self {
        Self {
            client,
            provider_name: "openai_compatible".to_owned(),
            base_url,
            api_key,
            model,
            limiter: Arc::new(Semaphore::new(max_concurrency)),
        }
    }

    pub fn with_provider_name(mut self, provider_name: String) -> Self {
        if !provider_name.trim().is_empty() {
            self.provider_name = provider_name;
        }
        self
    }

    pub fn capabilities() -> ProviderCapabilities {
        ProviderCapabilities {
            generation: true,
            streaming: true,
            tool_calling: true,
        }
    }

    fn ensure_configured(&self) -> Result<(), GenerationError> {
        if self.api_key.trim().is_empty() {
            return Err(GenerationError::Configuration(
                "AI_API_KEY is not configured".to_owned(),
            ));
        }
        if self.model.trim().is_empty() {
            return Err(GenerationError::Configuration(
                "AI_MODEL is not configured".to_owned(),
            ));
        }
        Ok(())
    }

    fn chat_completions_url(&self) -> String {
        format!("{}/chat/completions", self.base_url.trim_end_matches('/'))
    }

    fn build_payload(model: &str, request: &GenerationRequest) -> Value {
        let mut payload = json!({
            "model": model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt}
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": false
        });
        if !request.tools.is_empty() {
            payload["tools"] = Value::Array(
                request
                    .tools
                    .iter()
                    .map(|tool| {
                        json!({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.input_schema
                            }
                        })
                    })
                    .collect(),
            );
            payload["tool_choice"] = json!("auto");
        }
        payload
    }

    async fn generate_inner(
        &self,
        request: GenerationRequest,
    ) -> Result<GenerationResult, GenerationError> {
        self.ensure_configured()?;
        let url = self.chat_completions_url();
        let payload = Self::build_payload(&self.model, &request);
        let started = std::time::Instant::now();
        let mut last_error = String::new();
        for attempt in 0..3 {
            let permit = self.limiter.acquire().await.map_err(|_| {
                GenerationError::Configuration(
                    "Generation concurrency limiter is unavailable".to_owned(),
                )
            })?;
            let response = self
                .client
                .post(&url)
                .bearer_auth(self.api_key.trim())
                .timeout(Duration::from_secs(180))
                .json(&payload)
                .send()
                .await;
            let mut retry_after_secs = None;
            let should_retry = match response {
                Ok(response) if response.status().is_success() => {
                    let request_id = response
                        .headers()
                        .get("x-request-id")
                        .and_then(|value| value.to_str().ok())
                        .map(str::to_owned);
                    match response.json::<Value>().await {
                        Ok(body) => {
                            match parse_generation_body(body, &self.model, attempt, request_id) {
                                Ok(result) => {
                                    tracing::info!(
                                        provider = %self.provider_name,
                                        model = %result.model,
                                        prompt_tokens = ?result.normalized_usage.prompt_tokens,
                                        completion_tokens = ?result.normalized_usage.completion_tokens,
                                        duration_ms = started.elapsed().as_millis() as u64,
                                        "AI provider request completed"
                                    );
                                    return Ok(result);
                                }
                                Err(error) => {
                                    last_error = error;
                                    true
                                }
                            }
                        }
                        Err(error) => {
                            last_error = format!("AI provider returned invalid JSON: {error}");
                            true
                        }
                    }
                }
                Ok(response) => {
                    retry_after_secs = response
                        .headers()
                        .get("retry-after")
                        .and_then(|value| value.to_str().ok())
                        .and_then(|value| value.parse::<u64>().ok());
                    let status = response.status();
                    let detail = response.text().await.unwrap_or_default();
                    last_error = format!(
                        "AI provider request failed: {status} {}",
                        truncate_error_detail(&detail, 1000)
                    );
                    should_retry_status(status)
                }
                Err(error) => {
                    last_error = format!("AI provider request failed: {error}");
                    true
                }
            };
            drop(permit);
            if !should_retry {
                break;
            }
            if attempt < 2 {
                let delay = retry_after_secs.unwrap_or(1 << attempt).min(30);
                tokio::time::sleep(Duration::from_secs(delay)).await;
            }
        }
        tracing::warn!(
            provider = %self.provider_name,
            model = %self.model,
            duration_ms = started.elapsed().as_millis() as u64,
            "AI provider request failed"
        );
        Err(GenerationError::Request(last_error))
    }

    async fn generate_stream_inner(
        &self,
        request: GenerationRequest,
    ) -> Result<GenerationStream, GenerationError> {
        self.ensure_configured()?;
        let permit = self.limiter.clone().acquire_owned().await.map_err(|_| {
            GenerationError::Configuration(
                "Generation concurrency limiter is unavailable".to_owned(),
            )
        })?;
        let mut payload = Self::build_payload(&self.model, &request);
        payload["stream"] = json!(true);
        payload["stream_options"] = json!({"include_usage": true});
        let response = self
            .client
            .post(self.chat_completions_url())
            .bearer_auth(self.api_key.trim())
            .timeout(Duration::from_secs(180))
            .json(&payload)
            .send()
            .await
            .map_err(|error| {
                GenerationError::Request(format!("AI provider stream failed: {error}"))
            })?;
        if !response.status().is_success() {
            let status = response.status();
            let detail = response.text().await.unwrap_or_default();
            return Err(GenerationError::Request(format!(
                "AI provider stream failed: {status} {}",
                truncate_error_detail(&detail, 1000)
            )));
        }
        let (sender, receiver) = tokio::sync::mpsc::channel(32);
        tokio::spawn(async move {
            let _permit = permit;
            let mut bytes = response.bytes_stream();
            let mut buffer = String::new();
            let mut event_data = String::new();
            while let Some(next) = bytes.next().await {
                match next {
                    Ok(chunk) => buffer.push_str(&String::from_utf8_lossy(&chunk)),
                    Err(error) => {
                        let _ = sender
                            .send(Err(GenerationError::Request(format!(
                                "AI provider stream interrupted: {error}"
                            ))))
                            .await;
                        return;
                    }
                }
                while let Some(newline) = buffer.find('\n') {
                    let line = buffer[..newline].trim().to_owned();
                    buffer.drain(..=newline);
                    if line.is_empty() {
                        // SSE 事件以空行结尾：把累积的 data 行按规范拼接后解析。
                        // 单行 JSON 事件与旧逐行解析行为完全一致，同时兼容
                        // 跨多行发送的事件负载。
                        if forward_stream_event(&sender, &event_data).await {
                            return;
                        }
                        event_data.clear();
                        continue;
                    }
                    if let Some(data) = line.strip_prefix("data:").map(str::trim) {
                        event_data.push_str(data);
                        event_data.push('\n');
                    }
                }
            }
            // 流在空行分隔前就结束：冲刷最后一个未完成事件（部分服务端
            // 发送 `data: [DONE]` 后直接关闭连接）。
            if !event_data.is_empty() && forward_stream_event(&sender, &event_data).await {
                return;
            }
            let _ = sender
                .send(Ok(GenerationDelta {
                    content: String::new(),
                    done: true,
                    usage: None,
                }))
                .await;
        });
        Ok(Box::pin(ReceiverStream::new(receiver)))
    }
}

/// 解析并转发一个完整 SSE 事件；返回 true 表示流已结束（收到 done
/// 标记或接收端已断开），调用方应立即停止。
async fn forward_stream_event(
    sender: &tokio::sync::mpsc::Sender<Result<GenerationDelta, GenerationError>>,
    event_data: &str,
) -> bool {
    let Some(delta) = parse_stream_event(event_data) else {
        return false;
    };
    let done = delta.as_ref().is_ok_and(|item| item.done);
    sender.send(delta).await.is_err() || done
}

impl AiProvider for OpenAiCompatibleProvider {
    fn provider_name(&self) -> &str {
        &self.provider_name
    }

    fn model(&self) -> &str {
        &self.model
    }

    fn capabilities(&self) -> ProviderCapabilities {
        Self::capabilities()
    }

    fn generate<'a>(
        &'a self,
        request: GenerationRequest,
    ) -> Pin<Box<dyn Future<Output = Result<GenerationResult, GenerationError>> + Send + 'a>> {
        Box::pin(self.generate_inner(request))
    }

    fn generate_stream<'a>(
        &'a self,
        request: GenerationRequest,
    ) -> Pin<Box<dyn Future<Output = Result<GenerationStream, GenerationError>> + Send + 'a>> {
        Box::pin(self.generate_stream_inner(request))
    }
}

/// 解析一个完整 SSE 事件的 data 载荷（多个 data 行已按规范拼接）。
/// 返回 `None` 表示空事件或仅含 keep-alive 注释，调用方直接丢弃。
fn parse_stream_event(data: &str) -> Option<Result<GenerationDelta, GenerationError>> {
    let data = data.trim();
    if data.is_empty() {
        return None;
    }
    if data == "[DONE]" {
        return Some(Ok(GenerationDelta {
            content: String::new(),
            done: true,
            usage: None,
        }));
    }
    let body: Value = match serde_json::from_str(data) {
        Ok(body) => body,
        Err(error) => {
            return Some(Err(GenerationError::Request(format!(
                "AI provider returned invalid stream JSON: {error}"
            ))))
        }
    };
    let content = body["choices"][0]["delta"]["content"]
        .as_str()
        .unwrap_or_default()
        .to_owned();
    let usage = body
        .get("usage")
        .filter(|usage| !usage.is_null())
        .map(|usage| UnifiedUsage {
            prompt_tokens: usage["prompt_tokens"].as_u64(),
            completion_tokens: usage["completion_tokens"].as_u64(),
            total_tokens: usage["total_tokens"].as_u64(),
            generation_attempts: 1,
        });
    if content.is_empty() && usage.is_none() {
        None
    } else {
        Some(Ok(GenerationDelta {
            content,
            done: false,
            usage,
        }))
    }
}

fn parse_generation_body(
    body: Value,
    fallback_model: &str,
    attempt: usize,
    request_id: Option<String>,
) -> Result<GenerationResult, String> {
    let message = &body["choices"][0]["message"];
    let answer = message["content"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_owned();
    let tool_calls = message["tool_calls"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|call| {
            let arguments = call["function"]["arguments"]
                .as_str()
                .ok_or_else(|| "AI provider returned tool arguments in an invalid shape".to_owned())
                .and_then(|raw| {
                    serde_json::from_str(raw).map_err(|error| {
                        format!("AI provider returned invalid tool arguments: {error}")
                    })
                })?;
            Ok(ProviderToolCall {
                id: call["id"].as_str().unwrap_or_default().to_owned(),
                name: call["function"]["name"]
                    .as_str()
                    .unwrap_or_default()
                    .to_owned(),
                arguments,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    if answer.is_empty() && tool_calls.is_empty() {
        return Err("AI provider returned an empty completion".to_owned());
    }
    let provider_usage = body.get("usage").cloned().unwrap_or_else(|| json!({}));
    let normalized_usage = UnifiedUsage {
        prompt_tokens: provider_usage["prompt_tokens"].as_u64(),
        completion_tokens: provider_usage["completion_tokens"].as_u64(),
        total_tokens: provider_usage["total_tokens"].as_u64(),
        generation_attempts: attempt + 1,
    };
    let usage = if let Some(mut fields) = provider_usage.as_object().cloned() {
        fields.insert("generation_attempts".to_owned(), json!(attempt + 1));
        Value::Object(fields)
    } else {
        json!({
            "provider_usage": provider_usage,
            "generation_attempts": attempt + 1
        })
    };
    Ok(GenerationResult {
        answer,
        request_id: request_id.or_else(|| body["id"].as_str().map(str::to_owned)),
        model: body["model"].as_str().unwrap_or(fallback_model).to_owned(),
        usage,
        normalized_usage,
        tool_calls,
    })
}

fn truncate_error_detail(detail: &str, max_bytes: usize) -> &str {
    let mut end = detail.len().min(max_bytes);
    while !detail.is_char_boundary(end) {
        end -= 1;
    }
    &detail[..end]
}

fn should_retry_status(status: StatusCode) -> bool {
    matches!(status.as_u16(), 408 | 425 | 429 | 500..=599)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        parse_generation_body, parse_stream_event, AiProvider, GenerationRequest,
        OpenAiCompatibleProvider, ProviderCapabilities, ToolDefinition,
    };

    #[test]
    fn provider_builds_openai_compatible_tool_request() {
        let request = GenerationRequest {
            system_prompt: "system".to_owned(),
            user_prompt: "user".to_owned(),
            temperature: 0.2,
            max_tokens: 512,
            tools: vec![ToolDefinition {
                name: "search_notes".to_owned(),
                description: "Search reviewed notes".to_owned(),
                input_schema: json!({
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]
                }),
            }],
        };

        let payload = OpenAiCompatibleProvider::build_payload("model-a", &request);

        assert_eq!(payload["model"], "model-a");
        assert_eq!(payload["tools"][0]["type"], "function");
        assert_eq!(payload["tools"][0]["function"]["name"], "search_notes");
        assert_eq!(payload["tool_choice"], "auto");
        assert!(payload.get("thinking").is_none());
    }

    #[test]
    fn provider_parses_text_tool_calls_and_usage() {
        let result = parse_generation_body(
            json!({
                "id": "req-1",
                "model": "served-model",
                "choices": [{"message": {
                    "content": "I will search.",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_notes", "arguments": "{\"query\":\"PCR\"}"}
                    }]
                }}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            }),
            "fallback-model",
            1,
            Some("header-request-id".to_owned()),
        )
        .unwrap();

        assert_eq!(result.answer, "I will search.");
        assert_eq!(result.request_id.as_deref(), Some("header-request-id"));
        assert_eq!(result.model, "served-model");
        assert_eq!(result.normalized_usage.total_tokens, Some(15));
        assert_eq!(result.normalized_usage.generation_attempts, 2);
        assert_eq!(result.tool_calls[0].name, "search_notes");
        assert_eq!(result.tool_calls[0].arguments["query"], "PCR");
    }

    #[test]
    fn provider_declares_required_capabilities() {
        assert_eq!(
            OpenAiCompatibleProvider::capabilities(),
            ProviderCapabilities {
                generation: true,
                streaming: true,
                tool_calling: true,
            }
        );
    }

    #[test]
    fn provider_reports_configured_business_name() {
        let provider = OpenAiCompatibleProvider::new(
            reqwest::Client::new(),
            "https://example.invalid".to_owned(),
            "test-key".to_owned(),
            "model-a".to_owned(),
            1,
        )
        .with_provider_name("deepseek".to_owned());

        assert_eq!(provider.provider_name(), "deepseek");
    }

    #[test]
    fn provider_parses_stream_delta_and_done_marker() {
        let delta = parse_stream_event(r#"{"choices":[{"delta":{"content":"片段"}}]}"#)
            .unwrap()
            .unwrap();
        assert_eq!(delta.content, "片段");
        assert!(!delta.done);
        assert!(parse_stream_event("[DONE]").unwrap().unwrap().done);
        assert!(parse_stream_event("").is_none());
    }

    #[test]
    fn provider_joins_multiline_stream_events() {
        // 按 SSE 规范跨行发送的事件：两个 data 行拼接成一个 JSON 载荷。
        let delta = parse_stream_event("{\"choices\":[{\"delta\":{\"content\":\"片段\"}}\n,{}]}")
            .unwrap()
            .unwrap();
        assert_eq!(delta.content, "片段");
    }
}
