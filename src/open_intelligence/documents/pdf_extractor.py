"""Extract text from a PDF, page by page, with PyMuPDF."""
import pymupdf

pymupdf.TOOLS.mupdf_display_errors(False)  # harmless "could not parse color space" warnings


def extract_pages(pdf_bytes: bytes, max_pages: int) -> list[str]:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("encrypted_pdf")
        if doc.page_count > max_pages:
            raise ValueError(f"too_many_pages:{doc.page_count}")
        return [page.get_text("text") for page in doc]