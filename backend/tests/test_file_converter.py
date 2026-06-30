import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from app.utils.file_converter import FileConverter, FileConverterError


class TestFileConverter(unittest.TestCase):
    def test_txt_extraction(self):
        text = FileConverter.extract_text(b"Hello World", "resume.txt")
        self.assertEqual(text, "Hello World")

    def test_unsupported_extension(self):
        with self.assertRaises(FileConverterError):
            FileConverter.extract_text(b"data", "resume.xyz")

    @patch("pypdf.PdfReader")
    def test_pdf_raises_on_empty_text(self, mock_reader):
        mock_reader.return_value.pages = []
        with self.assertRaises(FileConverterError):
            FileConverter.extract_text(b"%PDF fake", "resume.pdf")


if __name__ == "__main__":
    unittest.main()
