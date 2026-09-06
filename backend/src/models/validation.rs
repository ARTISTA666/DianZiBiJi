use regex::Regex;
use std::sync::OnceLock;

pub fn validate_username(value: &str) -> Result<(), &'static str> {
    static USERNAME: OnceLock<Regex> = OnceLock::new();
    let length = value.chars().count();
    if !(3..=64).contains(&length) {
        return Err("Username must contain between 3 and 64 characters");
    }
    if !USERNAME
        .get_or_init(|| Regex::new(r"^[A-Za-z0-9_.-]+$").unwrap())
        .is_match(value)
    {
        return Err("Username contains unsupported characters");
    }
    Ok(())
}

pub fn validate_password(value: &str) -> Result<(), &'static str> {
    if !(8..=128).contains(&value.chars().count()) {
        return Err("Password must contain between 8 and 128 characters");
    }
    if !value.chars().any(|c| c.is_uppercase()) {
        return Err("密码必须至少包含一个大写字母");
    }
    if !value.chars().any(|c| c.is_lowercase()) {
        return Err("密码必须至少包含一个小写字母");
    }
    if !value.chars().any(|c| c.is_ascii_digit()) {
        return Err("密码必须至少包含一个数字");
    }
    Ok(())
}

pub fn validate_email(value: &str) -> Result<(), &'static str> {
    static EMAIL: OnceLock<Regex> = OnceLock::new();
    if value.len() <= 255
        && EMAIL
            .get_or_init(|| Regex::new(r"^[^\s@]+@[^\s@]+\.[^\s@]+$").unwrap())
            .is_match(value)
    {
        Ok(())
    } else {
        Err("Invalid email address")
    }
}

#[cfg(test)]
mod tests {
    use super::{validate_email, validate_password, validate_username};

    #[test]
    fn test_user_input_validation_matches_existing_contract() {
        assert!(validate_username("alice.smith-1").is_ok());
        assert!(validate_username("ab").is_err());
        assert!(validate_username("alice smith").is_err());
        assert!(validate_password("Password1").is_ok());
        assert!(validate_password("12345678").is_err());
        assert!(validate_password("short").is_err());
        assert!(validate_password("alllowercase1").is_err());
        assert!(validate_password("ALLUPPERCASE1").is_err());
        assert!(validate_password("NoDigitsHere").is_err());
        assert!(validate_email("alice@example.com").is_ok());
        assert!(validate_email("not-an-email").is_err());
    }
}
