from pathlib import Path

from PIL import Image, ImageDraw

from app.services.ocr_image import preprocess_image


def make_test_image(path: Path) -> None:
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 300, 180), fill=(40, 80, 140))
    image.save(path)


def test_crop_otsu_produces_smaller_binary_image(tmp_path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "processed.png"
    make_test_image(source)

    metadata = preprocess_image(source, output, "crop_otsu")

    assert metadata["crop_bbox"] is not None
    assert metadata["processed_size"][0] < metadata["original_size"][0]
    assert metadata["processed_size"][1] < metadata["original_size"][1]
    assert isinstance(metadata["otsu_threshold"], int)
    with Image.open(output) as image:
        colors = image.convert("L").getcolors(maxcolors=256)
        assert colors is not None
        assert {value for _count, value in colors} <= {0, 255}


def test_autocontrast_keeps_audit_metadata(tmp_path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "processed.png"
    make_test_image(source)

    metadata = preprocess_image(source, output, "grayscale_autocontrast")

    assert metadata == {
        "mode": "grayscale_autocontrast",
        "original_size": [400, 300],
        "processed_size": [440, 340],
        "crop_bbox": None,
        "otsu_threshold": None,
    }
