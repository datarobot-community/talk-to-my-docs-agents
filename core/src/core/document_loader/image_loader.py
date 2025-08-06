# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Image conversion utilities for RAG-Ultra: convert document pages to base64-encoded JPEG images.
Supports PDFs (via PyMuPDF or pdf2image), PPTX (via conversion), and robust parallel processing.
"""

import base64
import io
import logging
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict

# Optional dependency imports at module level
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image

from .constants import (
    DEFAULT_DPI,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_MAX_WORKERS,
    TEXT_FILE_TYPES,
)

logger = logging.getLogger(__name__)


def convert_page_to_image(
    document_path: str,
    page_num: int,
    dpi: int = DEFAULT_DPI,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> str | None:
    """
    Convert a specific page from a document to a base64-encoded JPEG image.

    Args:
        document_path: Path to the document
        page_num: Page number to convert (1-indexed)
        dpi: Resolution in dots per inch
        jpeg_quality: JPEG compression quality (1-95)

    Returns:
        Base64-encoded string of the JPEG image or None if conversion fails

    Raises:
        ValueError: If document type is not supported or the page cannot be converted
    """
    file_ext = Path(document_path).suffix.lower().lstrip(".")

    if file_ext == "pdf":
        # Prefer PyMuPDF (faster) and only fall back when necessary
        result = convert_pdf_page_to_image_fitz(
            document_path, page_num, dpi, jpeg_quality
        )
        if result:
            return result

        return convert_pdf_page_to_image(document_path, page_num, dpi, jpeg_quality)
    elif file_ext == "docx":
        logger.warning(
            "Direct DOCX to image conversion is not supported. Consider converting to PDF first."
        )
        return ""
    elif file_ext == "pptx":
        return convert_pptx_slide_to_image(document_path, page_num, dpi, jpeg_quality)
    elif file_ext in TEXT_FILE_TYPES:
        logger.warning("Text files cannot be directly converted to images.")
        return ""
    else:
        raise ValueError(f"Unsupported file type for image conversion: {file_ext}")


def _process_pdf_page_fitz(
    path: str, page_idx: int, zoom: float, jpeg_quality: int
) -> tuple[int, str]:
    """
    Helper for parallel PDF page conversion using PyMuPDF.
    Returns (1-indexed page number, base64 JPEG string).
    """
    try:
        with fitz.open(path) as doc:
            page = doc[page_idx]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return (page_idx + 1, img_base64)
    except Exception as e:
        logger.error(f"Error processing page {page_idx + 1}: {e}")
        return (page_idx + 1, "")


def convert_pdf_page_to_image_fitz(
    path: str,
    page_num: int,
    dpi: int = DEFAULT_DPI,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> str:
    """
    Convert a PDF page to a base64-encoded JPEG image using PyMuPDF (fitz).

    Args:
        path: Path to the PDF file
        page_num: Page number to convert (1-indexed)
        dpi: Resolution in dots per inch
        jpeg_quality: JPEG compression quality (1-95)

    Returns:
        Base64-encoded string of the JPEG image
    """
    try:
        # Open the PDF
        doc = fitz.open(path)

        # Check if page number is valid
        if page_num < 1 or page_num > len(doc):
            logger.error(f"Invalid page number {page_num}. PDF has {len(doc)} pages.")
            return ""

        # Get the page (0-indexed in PyMuPDF)
        page = doc[page_num - 1]

        # Calculate zoom factor based on DPI
        zoom = dpi / 72  # 72 is the default DPI for PDF

        # Get the pixmap (image)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))

        # Convert to PIL Image
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.info(
            f"Converted page {page_num} of {path} to base64 JPEG image using PyMuPDF"
        )
        return img_base64

    except Exception as e:
        logger.error(f"Error converting PDF page to image using PyMuPDF: {e}")
        return ""


def convert_pdf_page_to_image(
    path: str,
    page_num: int,
    dpi: int = DEFAULT_DPI,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> str:
    """
    Convert a PDF page to a base64-encoded JPEG image using pdf2image.

    Args:
        path: Path to the PDF file
        page_num: Page number to convert (1-indexed)
        dpi: Resolution in dots per inch
        jpeg_quality: JPEG compression quality (1-95)

    Returns:
        Base64-encoded string of the JPEG image
    """
    try:
        # Convert the PDF page to image
        images = convert_from_path(
            path, dpi=dpi, first_page=page_num, last_page=page_num
        )

        if not images:
            logger.error(f"Failed to convert page {page_num} of PDF {path}")
            return ""

        # Get the first image (should be the only one)
        image = images[0]

        # Convert to base64
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)

        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.info(f"Converted page {page_num} of {path} to base64 JPEG image")
        return img_base64
    except Exception as e:
        logger.error(f"Error converting PDF page to image: {e}")
        return ""


def convert_pptx_slide_to_image(
    path: str,
    slide_num: int,
    dpi: int = DEFAULT_DPI,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> str:
    """
    Convert a PowerPoint slide to a base64-encoded JPEG image.

    This requires a combination of libraries and may use an external converter.

    Args:
        pptx_path: Path to the PowerPoint file
        slide_num: Slide number to convert (1-indexed)
        dpi: Resolution in dots per inch
        jpeg_quality: JPEG compression quality (1-95)

    Returns:
        Base64-encoded string of the JPEG image
    """
    # TODO: We'll need to install libreoffice into the docker image to make this work, and add instructions
    # for folks to install it on their local machine as well.
    try:
        # Check if libreoffice or unoconv is available (need one for conversion)
        use_libreoffice = False
        use_unoconv = False

        try:
            subprocess.run(
                ["libreoffice", "--version"], check=True, capture_output=True
            )
            use_libreoffice = True
        except (subprocess.SubprocessError, FileNotFoundError):
            try:
                subprocess.run(
                    ["unoconv", "--version"], check=True, capture_output=True
                )
                use_unoconv = True
            except (subprocess.SubprocessError, FileNotFoundError):
                logger.error(
                    "Neither LibreOffice nor unoconv found for PPTX conversion"
                )
                return ""

        # Create temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            pdf_output = temp_dir_path / "output.pdf"

            # Convert PPTX to PDF
            if use_libreoffice:
                subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        temp_dir,
                        path,
                    ],
                    check=True,
                    capture_output=True,
                )

                # Rename if necessary
                orig_name = Path(path).stem + ".pdf"
                orig_path = temp_dir_path / orig_name
                if orig_path != pdf_output:
                    orig_path.rename(pdf_output)

            elif use_unoconv:
                subprocess.run(
                    ["unoconv", "-f", "pdf", "-o", pdf_output, path],
                    check=True,
                    capture_output=True,
                )

            # Now convert the PDF page to image
            if pdf_output.exists():
                return convert_pdf_page_to_image(
                    str(pdf_output), slide_num, dpi, jpeg_quality
                )
            else:
                logger.error(f"Failed to convert PPTX to PDF: {path}")
                return ""
    except Exception as e:
        logger.error(f"Error converting PPTX slide to image: {e}")
        return ""


def convert_document_pages_to_images(
    path: str,
    dpi: int = DEFAULT_DPI,
    poppler_path: str | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> Dict[int, str]:
    """
    Convert all pages in a document to base64-encoded JPEG images.

    Args:
        document_path: Path to the document
        dpi: Resolution in dots per inch
        poppler_path: Path to poppler binaries (required for Windows with pdf2image)
        max_workers: Maximum number of parallel processes to use
        jpeg_quality: JPEG compression quality (1-95)

    Returns:
        Dict mapping page numbers to base64-encoded JPEG images
    """
    file_ext = Path(path).suffix.lower().lstrip(".")

    # For now, only fully support PDF for bulk conversion
    if file_ext == "pdf":
        # Prefer PyMuPDF (faster) if available
        try:
            return convert_pdf_to_images_fitz(path, dpi, max_workers, jpeg_quality)
        except Exception as e:
            logger.warning(
                f"Failed to convert PDF with PyMuPDF: {e}. Trying pdf2image..."
            )

        # Fallback to pdf2image
        return convert_pdf_to_images_pdf2image(path, dpi, poppler_path, jpeg_quality)

    else:
        logger.warning(
            f"Bulk conversion not implemented for {file_ext} files. Converting pages one by one."
        )
        return {}


def convert_pdf_to_images_fitz(
    path: str,
    dpi: int = DEFAULT_DPI,
    max_workers: int = DEFAULT_MAX_WORKERS,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> Dict[int, str]:
    """
    Convert all pages in a PDF to base64-encoded JPEG images using PyMuPDF with parallel processing.

    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution in dots per inch
        max_workers: Maximum number of worker processes
        jpeg_quality: JPEG compression quality (1-95)

    Returns:
        Dict mapping page numbers to base64-encoded JPEG images
    """
    try:
        # Open the PDF just to get page count
        with fitz.open(path) as doc:
            page_count = len(doc)

        # Calculate zoom factor based on DPI
        zoom = dpi / 72  # 72 is the default DPI for PDF

        result = {}

        # Adjust max_workers based on page count
        actual_workers = min(max_workers, max(1, page_count))

        # Use parallel processing for multiple pages
        with ProcessPoolExecutor(max_workers=actual_workers) as executor:
            # Submit all page conversion tasks
            future_to_page = {
                executor.submit(
                    _process_pdf_page_fitz, path, page_idx, zoom, jpeg_quality
                ): page_idx
                for page_idx in range(page_count)
            }

            # Process results as they complete
            for future in as_completed(future_to_page):
                page_num, img_base64 = future.result()
                if img_base64:
                    result[page_num] = img_base64

        logger.info(
            f"Converted {len(result)} pages from {path} to base64 JPEG images using PyMuPDF"
        )
        return result

    except Exception as e:
        logger.error(f"Error converting PDF to images using PyMuPDF: {e}")
        return {}


def convert_pdf_to_images_pdf2image(
    path: str,
    dpi: int = DEFAULT_DPI,
    poppler_path: str | None = None,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> Dict[int, str]:
    """
    Convert all pages in a PDF to base64-encoded JPEG images using pdf2image.

    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution in dots per inch
        poppler_path: Path to poppler binaries (required for Windows)
        jpeg_quality: JPEG compression quality (1-95)

    Returns:
        Dict mapping page numbers to base64-encoded JPEG images
    """
    try:
        # Use poppler_path if provided
        conversion_kwargs: Dict[str, Any] = {"dpi": dpi}
        if poppler_path:
            conversion_kwargs["poppler_path"] = poppler_path
        images = convert_from_path(path, **conversion_kwargs)

        result = {}
        for i, image in enumerate(images):
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            # Store as 1-indexed
            result[i + 1] = img_base64
        logger.info(
            f"Converted {len(result)} pages from {path} to base64 JPEG images using pdf2image"
        )
        return result
    except Exception as e:
        logger.error(f"Error batch converting PDF pages to images using pdf2image: {e}")
        return {}
