use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::config::Settings;

#[derive(Clone)]
pub struct EmbeddingService {
    dimensions: usize,
}

#[derive(Debug, Error)]
pub enum EmbeddingError {
    #[error("Unsupported embedding backend: {0}")]
    UnsupportedBackend(String),
}

impl EmbeddingService {
    pub fn new(settings: &Settings) -> Result<Self, EmbeddingError> {
        if settings.embedding_backend != "hash" {
            return Err(EmbeddingError::UnsupportedBackend(
                settings.embedding_backend.clone(),
            ));
        }
        Ok(Self {
            dimensions: settings.embedding_dimension,
        })
    }

    pub async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, EmbeddingError> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }
        Ok(texts
            .iter()
            .map(|text| hash_embedding(text, self.dimensions))
            .collect())
    }
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
    use std::collections::HashMap;

    use super::EmbeddingService;
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
    fn unavailable_fastembed_backend_is_rejected() {
        let result = Settings::from_map(&HashMap::from([(
            "EMBEDDING_BACKEND".to_owned(),
            "fastembed".to_owned(),
        )]));
        assert!(result.is_err());
    }
}
