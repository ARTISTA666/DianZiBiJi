use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize)]
pub struct Paginated<T> {
    pub items: Vec<T>,
    pub total: i64,
    pub skip: i64,
    pub limit: i64,
}

#[derive(Debug, Default, Deserialize)]
pub struct PageQuery {
    pub skip: Option<i64>,
    pub limit: Option<i64>,
}

impl PageQuery {
    pub fn bounds(&self) -> (i64, i64) {
        page_bounds(self.skip, self.limit)
    }
}

pub fn page_bounds(skip: Option<i64>, limit: Option<i64>) -> (i64, i64) {
    (skip.unwrap_or(0).max(0), limit.unwrap_or(50).clamp(1, 200))
}
