use std::{
    io::Read,
    path::{Path, PathBuf},
    time::Duration,
};

use flate2::read::GzDecoder;
use image::{imageops, GrayImage, ImageFormat, Luma};
use thiserror::Error;
use tokio::{process::Command, time::timeout};
use uuid::Uuid;

use crate::config::Settings;

const TEXT_EXTENSIONS: &[&str] = &[
    "txt", "csv", "tsv", "soft", "md", "json", "xml", "html", "log", "yaml", "yml",
];
const IMAGE_EXTENSIONS: &[&str] = &["png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp"];
const PREPROCESS_MODES: &[&str] = &[
    "none",
    "grayscale_autocontrast",
    "grayscale_otsu",
    "crop_autocontrast",
    "crop_otsu",
];

#[derive(Clone, Debug)]
pub struct OcrSource {
    pub file_id: i32,
    pub original_filename: String,
    pub storage_path: String,
}

#[derive(Clone, Debug)]
pub struct ExtractedText {
    pub text: String,
    pub character_count: i32,
    pub truncated: bool,
    pub extraction_method: String,
}

#[derive(Debug, Error)]
pub enum OcrError {
    #[error("{0}")]
    NotFound(String),
    #[error("{0}")]
    Unsupported(String),
    #[error("{0}")]
    Internal(String),
}

pub async fn extract_text(
    settings: &Settings,
    source: &OcrSource,
) -> Result<ExtractedText, OcrError> {
    let path = PathBuf::from(&source.storage_path);
    if tokio::fs::metadata(&path).await.is_err() {
        return Err(OcrError::NotFound(format!(
            "Stored file not found at {}",
            source.storage_path
        )));
    }
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_lowercase();
    let max_chars = settings.document_text_max_chars.max(1);
    let (text, method) = if extension == "pdf" {
        (extract_pdf(&path).await?, "pdf_text".to_owned())
    } else if extension == "gz" {
        (
            extract_gzip(&path, &source.original_filename, max_chars).await?,
            "gzip_text".to_owned(),
        )
    } else if IMAGE_EXTENSIONS.contains(&extension.as_str()) {
        extract_image(settings, &path).await?
    } else if TEXT_EXTENSIONS.contains(&extension.as_str()) {
        let bytes = tokio::fs::read(&path)
            .await
            .map_err(|error| OcrError::Internal(error.to_string()))?;
        (
            String::from_utf8_lossy(&bytes).into_owned(),
            "plain_text".to_owned(),
        )
    } else {
        return Err(OcrError::Unsupported(format!(
            "Unsupported file type: {}",
            if extension.is_empty() {
                "[no extension]".to_owned()
            } else {
                format!(".{extension}")
            }
        )));
    };
    let (text, truncated) = limit_text(&text, max_chars);
    let character_count = i32::try_from(text.chars().count())
        .map_err(|error| OcrError::Internal(error.to_string()))?;
    Ok(ExtractedText {
        text,
        character_count,
        truncated,
        extraction_method: method,
    })
}

async fn extract_gzip(
    path: &Path,
    original_filename: &str,
    max_chars: usize,
) -> Result<String, OcrError> {
    let without_gzip = Path::new(original_filename)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    let inner_extension = Path::new(without_gzip)
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_lowercase();
    if !TEXT_EXTENSIONS.contains(&inner_extension.as_str()) {
        return Err(OcrError::Unsupported(format!(
            "Unsupported gzip payload: {}",
            if inner_extension.is_empty() {
                "[no extension]".to_owned()
            } else {
                format!(".{inner_extension}")
            }
        )));
    }
    let path = path.to_owned();
    tokio::task::spawn_blocking(move || {
        let file =
            std::fs::File::open(path).map_err(|error| OcrError::Internal(error.to_string()))?;
        let mut decoder = GzDecoder::new(file);
        let mut bytes = Vec::new();
        decoder
            .by_ref()
            .take((max_chars.saturating_mul(4).saturating_add(4096)) as u64)
            .read_to_end(&mut bytes)
            .map_err(|error| OcrError::Unsupported(format!("Invalid gzip file: {error}")))?;
        Ok(String::from_utf8_lossy(&bytes).into_owned())
    })
    .await
    .map_err(|error| OcrError::Internal(error.to_string()))?
}

async fn extract_pdf(path: &Path) -> Result<String, OcrError> {
    let mut command = Command::new("pdftotext");
    command.arg(path).arg("-").kill_on_drop(true);
    match timeout(Duration::from_secs(120), command.output()).await {
        Ok(Ok(output)) if output.status.success() => {
            Ok(String::from_utf8_lossy(&output.stdout).into_owned())
        }
        Ok(Err(error)) if error.kind() == std::io::ErrorKind::NotFound => {
            let bytes = tokio::fs::read(path)
                .await
                .map_err(|read_error| OcrError::Internal(read_error.to_string()))?;
            let ascii: String = bytes
                .into_iter()
                .take(5000)
                .filter(|byte| (32..127).contains(byte))
                .map(char::from)
                .collect();
            Ok(format!("{ascii}\n[PDF text extraction requires pdftotext]"))
        }
        Ok(Ok(output)) => Err(OcrError::Unsupported(format!(
            "PDF text extraction failed: {}",
            last_error_line(&output.stderr)
        ))),
        Ok(Err(error)) => Err(OcrError::Internal(error.to_string())),
        Err(_) => Err(OcrError::Unsupported(
            "PDF text extraction timed out after 120 seconds".to_owned(),
        )),
    }
}

async fn extract_image(settings: &Settings, path: &Path) -> Result<(String, String), OcrError> {
    let languages = list_tesseract_languages().await?;
    let requested: Vec<String> = settings
        .ocr_languages
        .replace(',', "+")
        .split('+')
        .map(str::trim)
        .filter(|language| !language.is_empty())
        .map(str::to_owned)
        .collect();
    if requested.is_empty() {
        return Err(OcrError::Unsupported("OCR_LANGUAGES is empty".to_owned()));
    }
    let missing: Vec<&str> = requested
        .iter()
        .map(String::as_str)
        .filter(|language| !languages.iter().any(|available| available == language))
        .collect();
    if !missing.is_empty() {
        return Err(OcrError::Unsupported(format!(
            "Tesseract language data is missing: {}",
            missing.join(", ")
        )));
    }
    let preprocessing = settings.ocr_preprocessing.trim();
    if !PREPROCESS_MODES.contains(&preprocessing) {
        return Err(OcrError::Unsupported(format!(
            "Unsupported OCR preprocessing mode: {preprocessing}"
        )));
    }
    if settings.ocr_page_segmentation_mode > 13 {
        return Err(OcrError::Unsupported(
            "OCR_PAGE_SEGMENTATION_MODE must be between 0 and 13".to_owned(),
        ));
    }
    let temp_path = PathBuf::from("/tmp").join(format!("eln-ocr-{}.png", Uuid::new_v4().simple()));
    let ocr_path = if preprocessing == "none" {
        path.to_owned()
    } else {
        let source = path.to_owned();
        let output = temp_path.clone();
        let mode = preprocessing.to_owned();
        tokio::task::spawn_blocking(move || preprocess_image(&source, &output, &mode))
            .await
            .map_err(|error| OcrError::Internal(error.to_string()))??;
        temp_path.clone()
    };
    let language_argument = requested.join("+");
    let mut command = Command::new("tesseract");
    command
        .arg(&ocr_path)
        .arg("stdout")
        .arg("-l")
        .arg(&language_argument)
        .arg("--psm")
        .arg(settings.ocr_page_segmentation_mode.to_string())
        .kill_on_drop(true);
    let output = timeout(Duration::from_secs(120), command.output()).await;
    if preprocessing != "none" {
        let _ = tokio::fs::remove_file(&temp_path).await;
    }
    let output = match output {
        Ok(Ok(output)) => output,
        Ok(Err(error)) if error.kind() == std::io::ErrorKind::NotFound => {
            return Err(OcrError::Unsupported(
                "Image OCR engine is not installed".to_owned(),
            ))
        }
        Ok(Err(error)) => return Err(OcrError::Internal(error.to_string())),
        Err(_) => {
            return Err(OcrError::Unsupported(
                "Image OCR timed out after 120 seconds".to_owned(),
            ))
        }
    };
    if !output.status.success() {
        return Err(OcrError::Unsupported(format!(
            "Image OCR failed: {}",
            last_error_line(&output.stderr)
        )));
    }
    Ok((
        String::from_utf8_lossy(&output.stdout).trim().to_owned(),
        format!(
            "tesseract:{language_argument};preprocess={preprocessing};psm={}",
            settings.ocr_page_segmentation_mode
        ),
    ))
}

async fn list_tesseract_languages() -> Result<Vec<String>, OcrError> {
    let mut command = Command::new("tesseract");
    command.arg("--list-langs").kill_on_drop(true);
    match timeout(Duration::from_secs(15), command.output()).await {
        Ok(Ok(output)) if output.status.success() => Ok(String::from_utf8_lossy(&output.stdout)
            .lines()
            .skip(1)
            .map(str::trim)
            .filter(|line| !line.is_empty())
            .map(str::to_owned)
            .collect()),
        Ok(Err(error)) if error.kind() == std::io::ErrorKind::NotFound => Err(
            OcrError::Unsupported("Image OCR engine is not installed".to_owned()),
        ),
        Ok(Ok(_)) => Ok(Vec::new()),
        Ok(Err(error)) => Err(OcrError::Internal(error.to_string())),
        Err(_) => Err(OcrError::Unsupported(
            "Image OCR engine did not respond".to_owned(),
        )),
    }
}

fn preprocess_image(source: &Path, output: &Path, mode: &str) -> Result<(), OcrError> {
    let mut image = image::open(source)
        .map_err(|error| OcrError::Unsupported(format!("Image preprocessing failed: {error}")))?
        .into_luma8();
    if mode.starts_with("crop_") {
        image = crop_content(&image);
    }
    autocontrast(&mut image);
    if mode.ends_with("_otsu") {
        let threshold = otsu_threshold(&image);
        for pixel in image.pixels_mut() {
            pixel.0[0] = if pixel.0[0] > threshold { 255 } else { 0 };
        }
    }
    let mut bordered = GrayImage::from_pixel(image.width() + 40, image.height() + 40, Luma([255]));
    imageops::replace(&mut bordered, &image, 20, 20);
    bordered
        .save_with_format(output, ImageFormat::Png)
        .map_err(|error| OcrError::Unsupported(format!("Image preprocessing failed: {error}")))
}

fn crop_content(image: &GrayImage) -> GrayImage {
    let mut left = image.width();
    let mut top = image.height();
    let mut right = 0;
    let mut bottom = 0;
    for (x, y, pixel) in image.enumerate_pixels() {
        if pixel.0[0] < 245 {
            left = left.min(x);
            top = top.min(y);
            right = right.max(x + 1);
            bottom = bottom.max(y + 1);
        }
    }
    if left >= right || top >= bottom {
        return image.clone();
    }
    let margin = 20.max(((image.width().max(image.height()) as f32) * 0.005).round() as u32);
    left = left.saturating_sub(margin);
    top = top.saturating_sub(margin);
    right = (right + margin).min(image.width());
    bottom = (bottom + margin).min(image.height());
    imageops::crop_imm(image, left, top, right - left, bottom - top).to_image()
}

fn autocontrast(image: &mut GrayImage) {
    let mut minimum = u8::MAX;
    let mut maximum = u8::MIN;
    for pixel in image.pixels() {
        minimum = minimum.min(pixel.0[0]);
        maximum = maximum.max(pixel.0[0]);
    }
    if minimum >= maximum {
        return;
    }
    let range = u16::from(maximum - minimum);
    for pixel in image.pixels_mut() {
        pixel.0[0] = ((u16::from(pixel.0[0] - minimum) * 255) / range) as u8;
    }
}

fn otsu_threshold(image: &GrayImage) -> u8 {
    let mut histogram = [0u64; 256];
    for pixel in image.pixels() {
        histogram[pixel.0[0] as usize] += 1;
    }
    let total = u64::from(image.width()) * u64::from(image.height());
    let sum: u64 = histogram
        .iter()
        .enumerate()
        .map(|(value, count)| value as u64 * count)
        .sum();
    let mut background_weight = 0u64;
    let mut background_sum = 0u64;
    let mut best_variance = 0f64;
    let mut best = 0u8;
    for (value, count) in histogram.iter().enumerate() {
        background_weight += count;
        if background_weight == 0 {
            continue;
        }
        let foreground_weight = total - background_weight;
        if foreground_weight == 0 {
            break;
        }
        background_sum += value as u64 * count;
        let background_mean = background_sum as f64 / background_weight as f64;
        let foreground_mean = (sum - background_sum) as f64 / foreground_weight as f64;
        let variance = background_weight as f64
            * foreground_weight as f64
            * (background_mean - foreground_mean).powi(2);
        if variance > best_variance {
            best_variance = variance;
            best = value as u8;
        }
    }
    best
}

fn limit_text(text: &str, max_chars: usize) -> (String, bool) {
    let count = text.chars().count();
    if count <= max_chars {
        return (text.to_owned(), false);
    }
    let marker = format!("\n[Content truncated at {max_chars} characters]");
    let marker_count = marker.chars().count();
    let body_count = max_chars.saturating_sub(marker_count);
    let body: String = text.chars().take(body_count).collect();
    let marker: String = marker.chars().take(max_chars - body_count).collect();
    (format!("{body}{marker}"), true)
}

fn last_error_line(stderr: &[u8]) -> String {
    String::from_utf8_lossy(stderr)
        .lines()
        .filter(|line| !line.trim().is_empty())
        .next_back()
        .unwrap_or("unknown error")
        .trim()
        .to_owned()
}

#[cfg(test)]
mod tests {
    use super::{limit_text, otsu_threshold};
    use image::{GrayImage, Luma};

    #[test]
    fn test_text_limit_reports_truncation() {
        let (text, truncated) = limit_text(&"x".repeat(100), 50);
        assert!(truncated);
        assert_eq!(text.chars().count(), 50);
        assert!(text.ends_with("characters]"));
    }

    #[test]
    fn test_otsu_threshold_separates_binary_values() {
        let mut image = GrayImage::from_pixel(10, 10, Luma([10]));
        for x in 5..10 {
            for y in 0..10 {
                image.put_pixel(x, y, Luma([240]));
            }
        }
        let threshold = otsu_threshold(&image);
        assert!((10..240).contains(&threshold));
    }
}
