use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::config::Settings;

#[derive(Clone)]
pub struct EmbeddingService {
    backend: String,
    model: String,
    dimensions: usize,
    api_url: String,
    api_key: String,
    client: reqwest::Client,
}

#[derive(Debug, Error)]
pub enum EmbeddingError {
    #[error("Unsupported embedding backend: {0}")]
    UnsupportedBackend(String),
    #[error("Embedding request failed: {0}")]
    Request(String),
    #[error("Invalid embedding response: {0}")]
    InvalidResponse(String),
}

impl EmbeddingService {
    pub fn new(settings: &Settings) -> Result<Self, EmbeddingError> {
        if !matches!(
            settings.embedding_backend.as_str(),
            "hash" | "openai_compatible"
        ) {
            return Err(EmbeddingError::UnsupportedBackend(
                settings.embedding_backend.clone(),
            ));
        }
        Ok(Self {
            backend: settings.embedding_backend.clone(),
            model: settings.embedding_model.clone(),
            dimensions: settings.embedding_dimension,
            api_url: settings.embedding_api_url.clone(),
            api_key: settings.embedding_api_key.clone(),
            client: reqwest::Client::new(),
        })
    }

    pub async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, EmbeddingError> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }
        match self.backend.as_str() {
            "hash" => Ok(texts
                .iter()
                .map(|text| hash_embedding(text, self.dimensions))
                .collect()),
            "openai_compatible" => self.embed_remote(texts).await,
            backend => Err(EmbeddingError::UnsupportedBackend(backend.to_owned())),
        }
    }

    async fn embed_remote(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, EmbeddingError> {
        let mut request = self.client.post(&self.api_url).json(&json!({
            "model": self.model,
            "input": texts,
        }));
        if !self.api_key.is_empty() {
            request = request.bearer_auth(&self.api_key);
        }
        let response = request
            .send()
            .await
            .map_err(|error| EmbeddingError::Request(error.to_string()))?;
        let status = response.status();
        let payload = response
            .json::<Value>()
            .await
            .map_err(|error| EmbeddingError::InvalidResponse(error.to_string()))?;
        if !status.is_success() {
            return Err(EmbeddingError::Request(
                payload
                    .get("error")
                    .and_then(Value::as_str)
                    .unwrap_or("embedding provider returned an error")
                    .to_owned(),
            ));
        }
        parse_embedding_response(&payload, texts.len(), self.dimensions)
    }
}

fn parse_embedding_response(
    payload: &Value,
    expected_count: usize,
    expected_dimensions: usize,
) -> Result<Vec<Vec<f32>>, EmbeddingError> {
    let items = payload
        .get("data")
        .and_then(Value::as_array)
        .ok_or_else(|| EmbeddingError::InvalidResponse("missing data array".to_owned()))?;
    if items.len() != expected_count {
        return Err(EmbeddingError::InvalidResponse(format!(
            "expected {expected_count} vectors, got {}",
            items.len()
        )));
    }
    let mut vectors: Vec<Option<Vec<f32>>> = vec![None; expected_count];
    for (position, item) in items.iter().enumerate() {
        let index = item
            .get("index")
            .and_then(Value::as_u64)
            .map_or(position, |value| value as usize);
        if index >= expected_count || vectors[index].is_some() {
            return Err(EmbeddingError::InvalidResponse(
                "embedding indexes are missing or duplicated".to_owned(),
            ));
        }
        let values = item
            .get("embedding")
            .and_then(Value::as_array)
            .ok_or_else(|| EmbeddingError::InvalidResponse("missing embedding array".to_owned()))?;
        if values.len() != expected_dimensions {
            return Err(EmbeddingError::InvalidResponse(format!(
                "expected {expected_dimensions} dimensions, got {}",
                values.len()
            )));
        }
        let vector = values
            .iter()
            .map(|value| {
                value.as_f64().map(|number| number as f32).ok_or_else(|| {
                    EmbeddingError::InvalidResponse("embedding contains a non-number".to_owned())
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        vectors[index] = Some(vector);
    }
    vectors
        .into_iter()
        .map(|vector| {
            vector.ok_or_else(|| EmbeddingError::InvalidResponse("missing embedding".to_owned()))
        })
        .collect()
}

fn normalize(vector: &mut [f32]) {
    let norm = vector
        .iter()
        .map(|value| f64::from(*value).powi(2))
        .sum::<f64>()
        .sqrt()
        .max(1e-12) as f32;
    for value in vector {
        *value /= norm;
    }
}

pub fn hash_embedding(text: &str, dimensions: usize) -> Vec<f32> {
    let mut embedding = vec![0.0f32; dimensions.max(1)];
    for token in embedding_tokens(text) {
        let digest = Sha256::digest(token.as_bytes());
        let index = u64::from_be_bytes(digest[..8].try_into().unwrap()) as usize % embedding.len();
        let sign = if digest[8] & 1 == 0 { 1.0 } else { -1.0 };
        embedding[index] += sign;
    }
    normalize(&mut embedding);
    embedding
}

fn embedding_tokens(text: &str) -> Vec<String> {
    let lowercase = text.to_lowercase();
    let mut tokens: Vec<String> = lowercase
        .split(|character: char| !character.is_alphanumeric())
        .filter(|token| !token.is_empty())
        .map(str::to_owned)
        .collect();
    let chinese: Vec<char> = lowercase
        .chars()
        .filter(|character| ('\u{4e00}'..='\u{9fff}').contains(character))
        .collect();
    tokens.extend(chinese.windows(2).map(|pair| pair.iter().collect()));
    if tokens.is_empty() && !lowercase.is_empty() {
        tokens.push(lowercase);
    }
    tokens
}

#[cfg(test)]
mod tests {
    use serde_json::json;
    use std::collections::HashMap;

    use super::{parse_embedding_response, EmbeddingService};
    use crate::config::Settings;

    #[tokio::test]
    async fn hash_backend_is_explicit_deterministic_test_double() {
        let settings = Settings::from_map(&HashMap::from([
            ("EMBEDDING_BACKEND".to_owned(), "hash".to_owned()),
            ("EMBEDDING_DIMENSION".to_owned(), "512".to_owned()),
        ]))
        .unwrap();
        let service = EmbeddingService::new(&settings).unwrap();
        let input = vec!["PCR Taq".to_owned()];
        let first = service.embed(&input).await.unwrap();
        let second = service.embed(&input).await.unwrap();
        assert_eq!(first, second);
        assert_eq!(first[0].len(), 512);
    }

    #[test]
    fn default_embedding_is_the_buildable_hash_backend() {
        let settings = Settings::from_map(&HashMap::new()).unwrap();
        assert_eq!(settings.embedding_backend, "hash");
        assert_eq!(settings.embedding_model, "rust-hash-512-v1");
        assert!(EmbeddingService::new(&settings).is_ok());
    }

    #[test]
    fn openai_compatible_backend_is_constructible() {
        let settings = Settings::from_map(&HashMap::from([
            (
                "EMBEDDING_BACKEND".to_owned(),
                "openai_compatible".to_owned(),
            ),
            ("EMBEDDING_MODEL".to_owned(), "BAAI/bge-m3".to_owned()),
            ("EMBEDDING_DIMENSION".to_owned(), "1024".to_owned()),
            (
                "EMBEDDING_API_URL".to_owned(),
                "http://localhost:8080/v1/embeddings".to_owned(),
            ),
        ]))
        .unwrap();
        assert!(EmbeddingService::new(&settings).is_ok());
    }

    #[test]
    fn unavailable_fastembed_backend_is_rejected() {
        let result = Settings::from_map(&HashMap::from([(
            "EMBEDDING_BACKEND".to_owned(),
            "fastembed".to_owned(),
        )]));
        assert!(result.is_err());
    }

    #[test]
    fn openai_compatible_response_is_parsed_in_input_order() {
        let payload = json!({
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]}
            ]
        });

        let vectors = parse_embedding_response(&payload, 2, 2).unwrap();

        assert_eq!(vectors, vec![vec![1.0, 0.0], vec![0.0, 1.0]]);
    }
}
