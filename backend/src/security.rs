use std::time::{SystemTime, UNIX_EPOCH};

use base64::{
    engine::general_purpose::{STANDARD_NO_PAD, URL_SAFE_NO_PAD},
    Engine,
};
use hmac::{Hmac, Mac};
use pbkdf2::pbkdf2;
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use subtle::ConstantTimeEq;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SecurityError {
    #[error("Password hashing failed: {0}")]
    Password(#[from] bcrypt::BcryptError),
    #[error("Token format is invalid")]
    TokenFormat,
    #[error("Token algorithm is unsupported")]
    TokenAlgorithm,
    #[error("Token signature is invalid")]
    TokenSignature,
    #[error("Token has expired")]
    TokenExpired,
    #[error("Token JSON is invalid: {0}")]
    TokenJson(#[from] serde_json::Error),
    #[error("System clock is before the Unix epoch")]
    Clock,
}

#[derive(Debug, Serialize, Deserialize)]
struct JwtClaims {
    sub: String,
    #[serde(default)]
    ver: i32,
    exp: u64,
}

#[derive(Debug, Serialize, Deserialize)]
struct JwtHeader {
    alg: String,
    #[serde(default)]
    typ: Option<String>,
}

#[derive(Debug, PartialEq, Eq)]
pub struct TokenClaims {
    pub subject: String,
    pub auth_version: i32,
}

pub fn hash_password(password: &str) -> Result<String, SecurityError> {
    Ok(bcrypt::hash(password, bcrypt::DEFAULT_COST)?)
}

pub fn verify_password(password: &str, password_hash: &str) -> bool {
    if password_hash.starts_with("$2") {
        return bcrypt::verify(password, password_hash).unwrap_or(false);
    }
    verify_passlib_pbkdf2(password, password_hash)
}

fn verify_passlib_pbkdf2(password: &str, password_hash: &str) -> bool {
    let fields: Vec<_> = password_hash.split('$').collect();
    if fields.len() != 5 || fields[1] != "pbkdf2-sha256" {
        return false;
    }
    let Ok(rounds) = fields[2].parse::<u32>() else {
        return false;
    };
    let decode = |value: &str| STANDARD_NO_PAD.decode(value.replace('.', "+")).ok();
    let (Some(salt), Some(expected)) = (decode(fields[3]), decode(fields[4])) else {
        return false;
    };
    let mut actual = vec![0; expected.len()];
    if pbkdf2::<Hmac<Sha256>>(password.as_bytes(), &salt, rounds, &mut actual).is_err() {
        return false;
    }
    actual.ct_eq(&expected).into()
}

pub fn create_access_token(
    subject: &str,
    auth_version: i32,
    secret: &str,
    expires_minutes: i64,
) -> Result<String, SecurityError> {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| SecurityError::Clock)?
        .as_secs() as i64;
    let exp = now.saturating_add(expires_minutes.saturating_mul(60));
    let claims = JwtClaims {
        sub: subject.to_owned(),
        ver: auth_version,
        exp: u64::try_from(exp).map_err(|_| SecurityError::TokenFormat)?,
    };
    let header = JwtHeader {
        alg: "HS256".to_owned(),
        typ: Some("JWT".to_owned()),
    };
    let header = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&header)?);
    let claims = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&claims)?);
    let signing_input = format!("{header}.{claims}");
    let signature = sign_hs256(signing_input.as_bytes(), secret)?;
    Ok(format!(
        "{signing_input}.{}",
        URL_SAFE_NO_PAD.encode(signature)
    ))
}

pub fn decode_access_token(token: &str, secret: &str) -> Result<TokenClaims, SecurityError> {
    if token.len() > 8_192 {
        return Err(SecurityError::TokenFormat);
    }
    let mut segments = token.split('.');
    let (Some(header), Some(claims), Some(signature), None) = (
        segments.next(),
        segments.next(),
        segments.next(),
        segments.next(),
    ) else {
        return Err(SecurityError::TokenFormat);
    };
    if header.is_empty() || claims.is_empty() || signature.is_empty() {
        return Err(SecurityError::TokenFormat);
    }

    let header_segment = header;
    let header_bytes = decode_canonical_segment(header_segment)?;
    let decoded_header: JwtHeader = serde_json::from_slice(&header_bytes)?;
    if decoded_header.alg != "HS256"
        || decoded_header
            .typ
            .as_deref()
            .is_some_and(|typ| typ != "JWT")
    {
        return Err(SecurityError::TokenAlgorithm);
    }

    let supplied_signature = decode_canonical_segment(signature)?;
    let signing_input = format!("{header_segment}.{claims}");
    let mut mac = Hmac::<Sha256>::new_from_slice(secret.as_bytes())
        .map_err(|_| SecurityError::TokenFormat)?;
    mac.update(signing_input.as_bytes());
    mac.verify_slice(&supplied_signature)
        .map_err(|_| SecurityError::TokenSignature)?;

    let claims_bytes = decode_canonical_segment(claims)?;
    let claims: JwtClaims = serde_json::from_slice(&claims_bytes)?;
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| SecurityError::Clock)?
        .as_secs();
    if claims.exp <= now {
        return Err(SecurityError::TokenExpired);
    }
    if claims.sub.is_empty() {
        return Err(SecurityError::TokenFormat);
    }
    Ok(TokenClaims {
        subject: claims.sub,
        auth_version: claims.ver,
    })
}

fn decode_canonical_segment(segment: &str) -> Result<Vec<u8>, SecurityError> {
    let decoded = URL_SAFE_NO_PAD
        .decode(segment)
        .map_err(|_| SecurityError::TokenFormat)?;
    if URL_SAFE_NO_PAD.encode(&decoded) != segment {
        return Err(SecurityError::TokenFormat);
    }
    Ok(decoded)
}

fn sign_hs256(input: &[u8], secret: &str) -> Result<Vec<u8>, SecurityError> {
    let mut mac = Hmac::<Sha256>::new_from_slice(secret.as_bytes())
        .map_err(|_| SecurityError::TokenFormat)?;
    mac.update(input);
    Ok(mac.finalize().into_bytes().to_vec())
}

#[cfg(test)]
mod tests {
    use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};

    use super::{
        create_access_token, decode_access_token, hash_password, sign_hs256, verify_password,
        SecurityError,
    };

    const PASSLIB_PBKDF2: &str =
        "$pbkdf2-sha256$29000$Q2hyaXN0bWFz$e2B6CqfNW/EH/aGSmtmMK6b2zHWrBRUU0y6bp/8JsmA";

    #[test]
    fn test_password_hash_roundtrip() {
        let hash = hash_password("correct horse battery staple").unwrap();

        assert!(verify_password("correct horse battery staple", &hash));
        assert!(!verify_password("wrong", &hash));
    }

    #[test]
    fn test_password_verifier_accepts_passlib_pbkdf2_format() {
        assert!(verify_password("swordfish", PASSLIB_PBKDF2));
        assert!(!verify_password("wrong", PASSLIB_PBKDF2));
    }

    #[test]
    fn test_access_token_roundtrip_and_version() {
        let token = create_access_token("42", 7, "test-secret", 60).unwrap();

        let claims = decode_access_token(&token, "test-secret").unwrap();

        assert_eq!(claims.subject, "42");
        assert_eq!(claims.auth_version, 7);
    }

    #[test]
    fn test_access_token_rejects_expired_token() {
        let token = create_access_token("42", 7, "test-secret", -1).unwrap();

        assert!(matches!(
            decode_access_token(&token, "test-secret"),
            Err(SecurityError::TokenExpired)
        ));
    }

    #[test]
    fn test_access_token_rejects_algorithm_confusion() {
        let token = signed_token(
            r#"{"alg":"none","typ":"JWT"}"#,
            r#"{"sub":"42","ver":7,"exp":4102444800}"#,
            "test-secret",
        );

        assert!(matches!(
            decode_access_token(&token, "test-secret"),
            Err(SecurityError::TokenAlgorithm)
        ));
    }

    #[test]
    fn test_access_token_rejects_malformed_or_noncanonical_segments() {
        let token = create_access_token("42", 7, "test-secret", 60).unwrap();

        assert!(decode_access_token(&format!("{token}.extra"), "test-secret").is_err());
        assert!(decode_access_token(&format!("{token}="), "test-secret").is_err());
        assert!(decode_access_token("header..signature", "test-secret").is_err());
    }

    #[test]
    fn test_access_token_rejects_malformed_claim_types_and_empty_subject() {
        let wrong_exp = signed_token(
            r#"{"alg":"HS256","typ":"JWT"}"#,
            r#"{"sub":"42","ver":7,"exp":"4102444800"}"#,
            "test-secret",
        );
        let empty_subject = signed_token(
            r#"{"alg":"HS256","typ":"JWT"}"#,
            r#"{"sub":"","ver":7,"exp":4102444800}"#,
            "test-secret",
        );

        assert!(matches!(
            decode_access_token(&wrong_exp, "test-secret"),
            Err(SecurityError::TokenJson(_))
        ));
        assert!(matches!(
            decode_access_token(&empty_subject, "test-secret"),
            Err(SecurityError::TokenFormat)
        ));
    }

    fn signed_token(header: &str, claims: &str, secret: &str) -> String {
        let header = URL_SAFE_NO_PAD.encode(header.as_bytes());
        let claims = URL_SAFE_NO_PAD.encode(claims.as_bytes());
        let input = format!("{header}.{claims}");
        let signature = sign_hs256(input.as_bytes(), secret).unwrap();
        format!("{input}.{}", URL_SAFE_NO_PAD.encode(signature))
    }

    /// Shared vectors also executed by the Python backend
    /// (backend/tests/test_security_vectors.py); both suites must stay green.
    #[test]
    fn test_shared_security_vectors_match_rust_implementation() {
        let vectors: serde_json::Value =
            serde_json::from_str(include_str!("../tests/security_vectors.json")).unwrap();

        for vector in vectors["password_vectors"].as_array().unwrap() {
            let name = vector["name"].as_str().unwrap();
            let matches = verify_password(
                vector["password"].as_str().unwrap(),
                vector["hash"].as_str().unwrap(),
            );
            assert_eq!(matches, vector["matches"].as_bool().unwrap(), "{name}");
        }

        let secret = vectors["jwt_secret"].as_str().unwrap();
        for vector in vectors["jwt_vectors"].as_array().unwrap() {
            let name = vector["name"].as_str().unwrap();
            let claims = decode_access_token(vector["token"].as_str().unwrap(), secret);
            if vector["valid"].as_bool().unwrap() {
                let claims = claims.unwrap_or_else(|error| panic!("{name}: {error}"));
                assert_eq!(
                    claims.subject,
                    vector["subject"].as_str().unwrap(),
                    "{name}"
                );
                assert_eq!(
                    i64::from(claims.auth_version),
                    vector["auth_version"].as_i64().unwrap(),
                    "{name}"
                );
            } else {
                assert!(claims.is_err(), "{name}");
            }
        }
    }
}
