// A simple mock AI provider used for testing without external calls.
use std::{future::Future, pin::Pin, sync::Arc};
use serde_json::json;
use thiserror::Error;

use crate::ai_provider::{AiProvider, GenerationRequest, GenerationResult, GenerationError, ProviderCapabilities, ProviderToolCall, UnifiedUsage};

#[derive(Clone)]
pub struct MockAiProvider;

impl MockAiProvider {
    pub fn new() -> Self {
        Self {}
    }
}

impl AiProvider for MockAiProvider {
    fn provider_name(&self) -> &str { "mock" }
    fn model(&self) -> &str { "mock-model" }
    fn capabilities(&self) -> ProviderCapabilities { ProviderCapabilities { generation: true, streaming: false, tool_calling: false } }
    fn generate<'a>(&'a self, request: GenerationRequest) -> Pin<Box<dyn Future<Output = Result<GenerationResult, GenerationError>> + Send + 'a>> {
        let result = GenerationResult {
            answer: format!("Mock answer to: {}", request.user_prompt),
            request_id: None,
            model: self.model().to_owned(),
            usage: json!({}),
            normalized_usage: UnifiedUsage { prompt_tokens: Some(1), completion_tokens: Some(1), total_tokens: Some(2), generation_attempts: 1 },
            tool_calls: Vec::new(),
        };
        Box::pin(async move { Ok(result) })
    }
    fn generate_stream<'a>(&'a self, _request: GenerationRequest) -> Pin<Box<dyn Future<Output = Result<crate::ai_provider::GenerationStream, GenerationError>> + Send + 'a>> {
        // Streaming not supported in mock.
        Box::pin(async move { Err(GenerationError::Configuration("Streaming not supported in mock".to_owned())) })
    }
}
