import logging
import os
import tempfile
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

logger = logging.getLogger(__name__)


def process_pdf(
    file_content: bytes,
    file_name: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> tuple[list[dict[str, Any]], int]:
    """
    Process a PDF file and split into chunks with metadata.

    Args:
        file_content: PDF file content as bytes
        file_name: Original file name
        chunk_size: Size of each text chunk
        chunk_overlap: Overlap between chunks

    Returns:
        Tuple of (list of chunks with metadata, page count)
    """
    tmp_file_path = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(file_content)
            tmp_file.flush()
            tmp_file_path = tmp_file.name

        # Process PDF
        loader = PyPDFLoader(tmp_file_path)
        documents = loader.load()

        page_count = len(documents)

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        chunks = text_splitter.split_documents(documents)

        result = []
        for chunk in chunks:
            result.append({
                "content": chunk.page_content,
                "file_name": file_name,
                "page_number": chunk.metadata.get("page", None),
            })

        return result, page_count

    finally:
        # Always cleanup temporary file
        if tmp_file_path and os.path.exists(tmp_file_path):
            try:
                os.unlink(tmp_file_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp PDF file: {e}")
