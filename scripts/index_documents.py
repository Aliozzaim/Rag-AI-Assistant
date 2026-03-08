"""
Document indexing script for Qdrant.
Processes documents and code files, generates embeddings, and stores them in Qdrant.
"""
import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.services.embedding_service import EmbeddingService
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentIndexer:
    """Indexes documents and code files into Qdrant."""

    def __init__(self):
        """Initialize Qdrant client and embedding service."""
        self.qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=30.0
        )
        self.collection_name = settings.qdrant_collection_name

        # Initialize embedding service based on provider
        if settings.embedding_provider == "bedrock":
            self.embedding_service = EmbeddingService(
                provider="bedrock",
                region=settings.aws_region,
                aws_profile=settings.aws_profile,
                access_key_id=settings.aws_access_key_id,
                secret_access_key=settings.aws_secret_access_key,
                model_id=settings.embedding_model,
                dimension=settings.embedding_dimension
            )
        elif settings.embedding_provider == "local":
            self.embedding_service = EmbeddingService(
                provider="local",
                model_name=settings.embedding_model
            )
        elif settings.embedding_provider == "openai":
            self.embedding_service = EmbeddingService(
                provider="openai",
                api_key=settings.openai_api_key,
                model=settings.embedding_model
            )
        else:
            raise ValueError(
                f"Unsupported embedding provider: {settings.embedding_provider}")

        # Get vector dimension from embedding service
        self.vector_dimension = self.embedding_service.get_dimension()
        logger.info(
            f"Using {settings.embedding_provider} provider with dimension {self.vector_dimension}")

        # Ensure collection exists
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        """Create collection if it doesn't exist."""
        try:
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.collection_name not in collection_names:
                logger.info(f"Creating collection: {self.collection_name}")
                logger.info(
                    f"Vector dimension: {self.vector_dimension} (for {self.embedding_model})")
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_dimension,  # Automatically matches embedding model
                        distance=Distance.COSINE
                    )
                )
                logger.info(
                    f"Collection {self.collection_name} created successfully")
            else:
                logger.info(
                    f"Collection {self.collection_name} already exists")
        except Exception as e:
            logger.error(f"Failed to create/verify collection: {str(e)}")
            raise

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """
        Split text into chunks with overlap.

        Args:
            text: Text to chunk
            chunk_size: Maximum characters per chunk
            overlap: Characters to overlap between chunks

        Returns:
            List of text chunks
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # Try to break at sentence or line boundary
            if end < len(text):
                # Look for newline first
                newline_pos = text.rfind('\n', start, end)
                if newline_pos != -1:
                    end = newline_pos + 1
                else:
                    # Look for sentence boundary
                    sentence_end = text.rfind('. ', start, end)
                    if sentence_end != -1:
                        end = sentence_end + 2

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap  # Overlap for context

        return chunks

    def read_file(self, file_path: Path) -> Optional[str]:
        """Read file content, handling different file types."""
        try:
            # Get file extension
            ext = file_path.suffix.lower()

            # Text files
            if ext in ['.txt', '.md', '.markdown', '.rst']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

            # Code files
            code_extensions = [
                '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
                '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala',
                '.sql', '.sh', '.bash', '.yaml', '.yml', '.json', '.xml', '.html',
                '.css', '.scss', '.less', '.vue', '.dart', '.r', '.m', '.mm'
            ]
            if ext in code_extensions:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

            # Skip binary files
            logger.warning(f"Skipping unsupported file type: {file_path}")
            return None

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return None

    def index_file(self, file_path: Path, base_path: Path) -> int:
        """
        Index a single file into Qdrant.

        Args:
            file_path: Path to the file to index
            base_path: Base directory path for relative path calculation

        Returns:
            Number of chunks indexed
        """
        content = self.read_file(file_path)
        if not content:
            return 0

        # Calculate relative path for source identifier
        try:
            relative_path = file_path.relative_to(base_path)
            source = str(relative_path).replace('\\', '/')
        except:
            source = str(file_path)

        # Chunk the content
        chunks = self.chunk_text(content)

        if not chunks:
            return 0

        # Generate embeddings and prepare points
        points = []
        for idx, chunk in enumerate(chunks):
            try:
                # Generate embedding
                embedding = self.embedding_service.generate_embedding(chunk)

                # Create unique ID for this chunk
                chunk_id = f"{source}_{idx}"
                point_id = int(hashlib.md5(
                    chunk_id.encode()).hexdigest()[:8], 16)

                # Prepare point
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "text": chunk,
                        "source": source,
                        "chunk_id": chunk_id,
                        "file_path": source,
                        "chunk_index": idx,
                        "total_chunks": len(chunks)
                    }
                )
                points.append(point)

            except Exception as e:
                logger.error(
                    f"Error processing chunk {idx} of {file_path}: {str(e)}")
                continue

        if not points:
            return 0

        # Upsert points to Qdrant
        try:
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Indexed {len(points)} chunks from {source}")
            return len(points)
        except Exception as e:
            logger.error(f"Error indexing {source}: {str(e)}")
            return 0

    def index_directory(
        self,
        directory: str,
        extensions: Optional[List[str]] = None,
        exclude_dirs: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        Index all files in a directory.

        Args:
            directory: Directory path to index
            extensions: List of file extensions to include (None = all supported)
            exclude_dirs: List of directory names to exclude (e.g., ['node_modules', '.git'])

        Returns:
            Dictionary with indexing statistics
        """
        base_path = Path(directory).resolve()
        if not base_path.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        exclude_dirs = exclude_dirs or [
            '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', '.env']

        stats = {
            "files_processed": 0,
            "chunks_indexed": 0,
            "errors": 0
        }

        # Walk through directory
        for root, dirs, files in os.walk(base_path):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                file_path = Path(root) / file

                # Filter by extension if specified
                if extensions and file_path.suffix.lower() not in extensions:
                    continue

                try:
                    chunks = self.index_file(file_path, base_path)
                    stats["files_processed"] += 1
                    stats["chunks_indexed"] += chunks
                except Exception as e:
                    logger.error(f"Error indexing {file_path}: {str(e)}")
                    stats["errors"] += 1

        return stats


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Index documents and code into Qdrant")
    parser.add_argument(
        "directory",
        type=str,
        help="Directory path to index"
    )
    parser.add_argument(
        "--extensions",
        type=str,
        nargs="+",
        help="File extensions to include (e.g., .py .md .txt)",
        default=None
    )
    parser.add_argument(
        "--exclude-dirs",
        type=str,
        nargs="+",
        help="Directories to exclude (e.g., .git node_modules)",
        default=['.git', 'node_modules', '__pycache__', '.venv', 'venv']
    )
    parser.add_argument(
        "--collection",
        type=str,
        help="Qdrant collection name (overrides config)",
        default=None
    )

    args = parser.parse_args()

    # Override collection name if provided
    if args.collection:
        settings.qdrant_collection_name = args.collection

    # Initialize indexer
    indexer = DocumentIndexer()

    # Index directory
    logger.info(f"Starting indexing of directory: {args.directory}")
    stats = indexer.index_directory(
        directory=args.directory,
        extensions=args.extensions,
        exclude_dirs=args.exclude_dirs
    )

    # Print statistics
    print("\n" + "="*50)
    print("Indexing Complete!")
    print("="*50)
    print(f"Files processed: {stats['files_processed']}")
    print(f"Chunks indexed: {stats['chunks_indexed']}")
    print(f"Errors: {stats['errors']}")
    print("="*50)


if __name__ == "__main__":
    main()
