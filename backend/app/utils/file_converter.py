import io
import re
from pathlib import Path
from typing import Optional

from loguru import logger


class FileConverterError(Exception):
    pass


class FileConverter:
    @staticmethod
    def extract_text(file_bytes: bytes, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        logger.info("Converting file", ext=ext, filename=filename)

        if ext == ".pdf":
            return FileConverter._from_pdf(file_bytes)
        elif ext == ".docx":
            return FileConverter._from_docx(file_bytes)
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
            return FileConverter._from_image(file_bytes)
        elif ext in (".txt",):
            return file_bytes.decode("utf-8", errors="replace")
        else:
            raise FileConverterError(f"Unsupported file type: {ext}")

    @staticmethod
    def _from_pdf(file_bytes: bytes) -> str:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise FileConverterError("PDF is empty or unreadable (scanned? Try OCR).")
        return text

    @staticmethod
    def _from_docx(file_bytes: bytes) -> str:
        try:
            from docx import Document

            doc = Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            raise FileConverterError("python-docx is not installed. `pip install python-docx`")
        except Exception as e:
            raise FileConverterError(f"DOCX read error: {e}")

    @staticmethod
    def _from_image(file_bytes: bytes) -> str:
        try:
            from PIL import Image
            import pytesseract

            image = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(image)
            if not text.strip():
                raise FileConverterError("No text detected in image.")
            return text
        except ImportError:
            raise FileConverterError(
                "pytesseract or Pillow not installed. "
                "`pip install pytesseract Pillow` and install tesseract-ocr system package."
            )
        except FileNotFoundError:
            raise FileConverterError(
                "tesseract not found on system PATH. Install it first:\n"
                "  macOS: brew install tesseract\n"
                "  Ubuntu: apt install tesseract-ocr"
            )
        except Exception as e:
            raise FileConverterError(f"OCR error: {e}")
