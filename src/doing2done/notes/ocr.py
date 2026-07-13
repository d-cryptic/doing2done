"""On-device handwriting OCR via Apple's Vision framework (free, local).

Requires the 'ocr' extra:  uv sync --extra ocr
Same engine that already makes Apple Notes searchable.
"""
from __future__ import annotations

from pathlib import Path


def recognize(image_path: str | Path) -> str:
    """OCR an image file to text using VNRecognizeTextRequest (accurate)."""
    try:
        import Quartz
        import Vision
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Apple Vision bindings missing. Run: uv sync --extra ocr"
        ) from e

    url = Quartz.CFURLCreateWithFileSystemPath(
        None, str(image_path), Quartz.kCFURLPOSIXPathStyle, False
    )
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        raise ValueError(f"Cannot read image: {image_path}")
    cg_image = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    handler.performRequests_error_([request], None)

    lines: list[str] = []
    for obs in request.results() or []:
        top = obs.topCandidates_(1)
        if top:
            lines.append(top[0].string())
    return "\n".join(lines)
