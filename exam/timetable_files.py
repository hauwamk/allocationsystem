"""Turns an officer-uploaded timetable document into a JPG or PNG.

Officers upload the official timetable itself, as a PDF or an image.
Students download it as a single picture, so PDFs are rasterised with
pypdfium2 and multi-page documents are stitched into one tall image.
"""

from io import BytesIO
from pathlib import Path

try:
    import pypdfium2 as pdfium
except ImportError:  # PDF export stays unavailable until it is installed
    pdfium = None

from django.core.exceptions import ValidationError
from PIL import Image

ALLOWED_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".webp")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 5
RENDER_WIDTH = 1600
MAX_PDF_SCALE = 3.0
PAGE_GAP = 16


class TimetableFileError(ValueError):
    """Raised when an uploaded timetable file cannot be read or converted."""


def file_suffix(file_obj):
    return Path(getattr(file_obj, "name", "") or "").suffix.lower()


def _pdfium():
    if pdfium is None:
        raise TimetableFileError(
            "PDF support is not installed on this server. Install pypdfium2, "
            "or upload the timetable as a PNG or JPG image."
        )
    return pdfium


def validate_timetable_file(upload):
    """
    Form validator: rejects the wrong file type or an unreadable file while
    the officer is still on the page, instead of failing later when a
    student tries to download it.
    """
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError("The file is larger than 20 MB.")

    suffix = file_suffix(upload)
    if suffix not in ALLOWED_SUFFIXES:
        raise ValidationError("Upload a PDF, PNG, JPG or WEBP file.")

    upload.seek(0)
    data = upload.read()
    upload.seek(0)

    try:
        if suffix == ".pdf":
            pages = pdf_page_count(data)
            if pages > MAX_PDF_PAGES:
                raise TimetableFileError(
                    f"That PDF has {pages} pages. Upload a timetable with "
                    f"at most {MAX_PDF_PAGES} pages so it can be downloaded as one image."
                )
        else:
            _open_image(data)
    except TimetableFileError as exc:
        raise ValidationError(str(exc)) from exc


def pdf_page_count(data):
    document = None
    try:
        document = _pdfium().PdfDocument(data)
        count = len(document)
    except TimetableFileError:
        raise
    except Exception as exc:
        raise TimetableFileError(
            "That PDF could not be read. Try exporting it again."
        ) from exc
    finally:
        if document is not None:
            document.close()

    if count == 0:
        raise TimetableFileError("That PDF has no pages.")
    return count


def render_timetable_file(upload, image_format):
    """Returns the uploaded timetable as image bytes ("png" or "jpg")."""
    upload.seek(0)
    data = upload.read()
    upload.seek(0)

    if file_suffix(upload) == ".pdf":
        pages = _render_pdf(data)
    else:
        pages = [_open_image(data)]

    image = _stack_pages(pages)
    buffer = BytesIO()
    if image_format == "jpg":
        image.save(buffer, format="JPEG", quality=90, optimize=True)
    else:
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_pdf(data):
    document = None
    try:
        document = _pdfium().PdfDocument(data)
        page_count = len(document)
        if page_count == 0:
            raise TimetableFileError("That PDF has no pages.")
        if page_count > MAX_PDF_PAGES:
            raise TimetableFileError(
                f"That PDF has {page_count} pages. Upload a timetable with "
                f"at most {MAX_PDF_PAGES} pages so it can be downloaded as one image."
            )

        pages = []
        for index in range(page_count):
            page = document[index]
            width, height = page.get_size()
            scale = min(RENDER_WIDTH / width if width else MAX_PDF_SCALE, MAX_PDF_SCALE)
            bitmap = page.render(scale=scale)
            pages.append(bitmap.to_pil().convert("RGB"))
        return pages
    except TimetableFileError:
        raise
    except Exception as exc:
        raise TimetableFileError(
            "That PDF could not be read. Try exporting it again."
        ) from exc
    finally:
        if document is not None:
            document.close()


def _open_image(data):
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return _normalise(image)
    except Exception as exc:
        raise TimetableFileError(
            "That image could not be read. Try a PNG or JPG file."
        ) from exc


def _normalise(image):
    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        result = Image.new("RGB", rgba.size, "white")
        result.paste(rgba, mask=rgba.split()[-1])
    else:
        result = image.convert("RGB")

    if result.width > RENDER_WIDTH:
        height = round(result.height * RENDER_WIDTH / result.width)
        result = result.resize((RENDER_WIDTH, height), Image.Resampling.LANCZOS)
    return result


def _stack_pages(pages):
    if len(pages) == 1:
        return pages[0]

    width = max(page.width for page in pages)
    height = sum(page.height for page in pages) + PAGE_GAP * (len(pages) - 1)
    canvas = Image.new("RGB", (width, height), "white")
    top = 0
    for page in pages:
        canvas.paste(page, ((width - page.width) // 2, top))
        top += page.height + PAGE_GAP
    return canvas
