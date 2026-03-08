# - Microsoft Teams AI Assistant Backend

A secure, read-only backend service for the Microsoft Teams AI assistant that provides intelligent answers based on a knowledge base using vector search and AWS Bedrock.

## 🚀 Features

- **Multi-source search** across:
  - **Qdrant** - Vector-based knowledge retrieval with Amazon Titan V2 embeddings
  - **MongoDB** - Product database query and review analysis (optional)
  - **Stash/Bitbucket** - Code repository search (optional)
  - **Confluence** - Documentation search (optional)
- **AWS Bedrock integration**:
  - **LLM**: Claude models for answer generation
  - **Embeddings**: Titan Text Embeddings V2 (1024/512/256 dimensions)
- **Flexible embedding providers**: Bedrock (default), Local models, or OpenAI
- **API endpoints**:
  - `POST /ask` - Ask questions and get AI-generated answers
  - `POST /add-embedding` - Add documents via API
  - `GET /health` - Health check for all services
- **Security**:
  - Input sanitization to prevent prompt injection
  - API key authentication
  - Rate limiting
- **Performance**:
  - Answer caching with Redis
  - Parallel search across all sources
  - Optimized vector similarity search
- **Production-ready**:
  - Comprehensive logging
  - Error handling with graceful degradation
  - Health monitoring

## Architecture

1. Teams bot sends question → POST /ask endpoint
2. Service sanitizes input and checks cache
3. **Parallel search** across all enabled sources:
   - Generates embedding and queries Qdrant (vector search)
   - Queries MongoDB product database for products and reviews (optional)
   - Searches Stash/Bitbucket code repositories (API search)
   - Searches Confluence documentation (API search)
4. Combines and ranks results from all sources
5. Builds prompt with retrieved chunks and instructions
6. Calls AWS Bedrock LLM to generate answer
7. Returns answer with source citations from all sources

## Setup

### Prerequisites

- **Python 3.9-3.12** (Python 3.13 may have compatibility issues with some dependencies)
- Qdrant (Cloud or self-hosted)
- AWS account with Bedrock access (for LLM)
- **Embedding Provider** (choose one):
  - AWS Bedrock (recommended - same account as LLM)
  - Local models (free, install `sentence-transformers`)
  - OpenAI API (optional)
- MongoDB access (optional, for product database queries)
- Stash/Bitbucket access (optional, for code search)
- Confluence access (optional, for documentation search)
- Redis (optional, for caching)

**Note**: OpenAI API is **not required**. You can use AWS Bedrock or local models for embeddings!

**Python Version Note**: If you encounter build errors with Python 3.13, use Python 3.11 or 3.12 instead.

### Installation

1. Clone the repository and navigate to the project directory:

```bash
cd AI
```

2. Create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Copy `env.example` to `.env` and configure:

```bash
cp env.example .env
# Edit .env with your credentials
```

The `env.example` file includes:

- Qdrant configuration with your API key pre-filled
- AWS Bedrock settings
- Optional MongoDB product database configuration
- Optional Stash and Confluence configurations
- All other required settings with examples

5. Start the service:

```bash
# Make sure venv is activated first!
source venv/bin/activate

# Start the service (ALWAYS use python -m uvicorn, not just uvicorn!)
# Run from project root directory, NOT from frontend directory!
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# OR use the entry point:
python main.py

# Or with auto-reload for development
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**⚠️ Critical**: Always use `python -m uvicorn` (not just `uvicorn`) to ensure you're using the venv's Python and packages!

## Environment Variables

See `.env.example` for all required configuration options.

### Quick Setup

**Qdrant (Required)**

- `QDRANT_URL` - Your Qdrant endpoint (e.g., `https://api.qdrant.io`)
- `QDRANT_API_KEY` - Your Qdrant API key
- `QDRANT_COLLECTION_NAME` - Collection name for knowledge base

**AWS Bedrock (Required for LLM)**

- `AWS_REGION` - AWS region (default: `eu-west-1`)
- `AWS_ACCESS_KEY_ID` - Your AWS access key
- `AWS_SECRET_ACCESS_KEY` - Your AWS secret key
- `BEDROCK_MODEL_ID` - LLM model (e.g., `anthropic.claude-v2`)

**Embeddings (Choose One)**

- **Option 1 - AWS Bedrock Titan V2** (Recommended - same account as LLM):
  ```bash
  EMBEDDING_PROVIDER=bedrock
  EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
  EMBEDDING_DIMENSION=1024  # or 512, 256
  ```
- **Option 2 - Local Models** (Free, no API keys):
  ```bash
  EMBEDDING_PROVIDER=local
  EMBEDDING_MODEL=all-MiniLM-L6-v2
  # Install: pip install sentence-transformers
  ```
- **Option 3 - OpenAI** (If you have OpenAI access):
  ```bash
  EMBEDDING_PROVIDER=openai
  EMBEDDING_MODEL=text-embedding-ada-002
  OPENAI_API_KEY=your_key
  ```

See [TITAN_V2_SETUP.md](TITAN_V2_SETUP.md) for Titan V2 setup, [EMBEDDING_ALTERNATIVES.md](EMBEDDING_ALTERNATIVES.md) for alternatives, and [QDRANT_SETUP.md](QDRANT_SETUP.md) for Qdrant setup.

**Stash/Bitbucket (Optional)**

- `STASH_ENABLED=true`
- `STASH_BASE_URL` - Stash/Bitbucket URL
- `STASH_USERNAME` / `STASH_PASSWORD` or `STASH_TOKEN`

**MongoDB (Optional - for product database queries)**

- `MONGODB_ENABLED=true`
- `MONGODB_URI` - MongoDB connection URI (e.g., `mongodb+srv://user:pass@cluster.mongodb.net/`)
- `MONGODB_DATABASE_NAME` - Database name (default: `ProductReview`)
- `MONGODB_PRODUCTS_COLLECTION` - Products collection name (default: `products`)
- `MONGODB_REVIEWS_COLLECTION` - Reviews collection name (default: `marketplace_reviews`)
- `MONGODB_MAX_RESULTS` - Maximum results per search (default: `10`)
- `MONGODB_TIMEOUT` - Request timeout in seconds (default: `10`)

**Confluence (Optional)**

- `CONFLUENCE_ENABLED=true`
- `CONFLUENCE_BASE_URL` - Confluence URL
- `CONFLUENCE_USERNAME` / `CONFLUENCE_PASSWORD` or `CONFLUENCE_TOKEN`

See [STASH_CONFLUENCE_SETUP.md](STASH_CONFLUENCE_SETUP.md) for detailed configuration.

## API Usage

### POST /ask

Ask questions and get AI-generated answers with source citations.

**Request:**

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "user": "John Doe",
    "question": "How do I deploy the application?"
  }'
```

**Response:**

```json
{
  "answer": "To deploy the application, follow these steps: 1) Build the Docker image...",
  "sources": [
    "docs/deployment.md",
    "mongodb://products/iPhone-14-Pro",
    "stash://repo/deploy.sh",
    "confluence://ENG/Deployment Guide"
  ]
}
```

### POST /add-embedding

Add documents to the knowledge base via API.

**Request:**

```bash
curl -X POST http://localhost:8000/add-embedding \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "text": "Your document content here...",
    "source": "docs/api-guide.md",
    "chunk_size": 1000,
    "metadata": {
      "author": "John Doe",
      "version": "1.0"
    }
  }'
```

**Response:**

```json
{
  "success": true,
  "chunks_indexed": 3,
  "message": "Successfully indexed 3 chunk(s) from docs/api-guide.md"
}
```

### GET /health

Check health status of all services.

**Request:**

```bash
curl http://localhost:8000/health
```

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00",
  "services": {
    "vector_db": true,
    "bedrock": true,
    "cache": true,
    "mongodb": true,
    "stash": false,
    "confluence": false
  }
}
```

See [API_USAGE.md](API_USAGE.md) for detailed API documentation and examples.

## Knowledge Base Setup

Before using the service, you need to index your documents and codebase into Qdrant.

### Quick Start: Index Your Documents

1. **Index a directory** (e.g., your documentation):

   ```bash
   python index_documents.py /path/to/your/documents
   ```

2. **Index your codebase**:

   ```bash
   python index_documents.py /path/to/your/codebase \
     --extensions .py .js .ts .md \
     --exclude-dirs node_modules __pycache__ .git
   ```

3. **Index multiple sources**:

   ```bash
   # Documentation
   python index_documents.py ./docs

   # Codebase
   python index_documents.py ./src --extensions .py .js .ts

   # Confluence exports
   python index_documents.py ./confluence_exports
   ```

The indexing script will:

- ✅ Automatically create the Qdrant collection if needed
- ✅ Process supported file types (code, markdown, text, etc.)
- ✅ Chunk documents appropriately with overlap
- ✅ Generate embeddings using your configured provider (Bedrock/Local/OpenAI)
- ✅ Store everything in Qdrant with metadata

### Add Embeddings via API

You can also add documents programmatically:

```bash
curl -X POST http://localhost:8000/add-embedding \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{
    "text": "Document content...",
    "source": "docs/my-doc.md"
  }'
```

See [example_add_embedding.py](example_add_embedding.py) for Python examples.

### Supported File Types

- **Documentation**: `.md`, `.txt`, `.rst`
- **Code**: `.py`, `.js`, `.ts`, `.java`, `.cpp`, `.go`, `.rs`, and many more
- **Config**: `.yaml`, `.json`, `.xml`

### Collection Setup

The collection is created automatically with the correct dimension based on your embedding model. For Titan V2:

- **1024 dimensions** (default) - Best accuracy
- **512 dimensions** - Balanced cost/accuracy
- **256 dimensions** - Cost-optimized

The dimension is automatically detected from your `EMBEDDING_DIMENSION` setting.

See [INDEXING_GUIDE.md](INDEXING_GUIDE.md) for detailed indexing instructions and [QDRANT_SETUP.md](QDRANT_SETUP.md) for Qdrant setup.

## Security

- All inputs are sanitized to prevent prompt injection
- API key authentication required
- Rate limiting prevents abuse
- Read-only operations (no code execution)
- Environment variables for all secrets

## Logging

Logs are written to stdout with structured format including:

- Timestamp
- User (anonymized)
- Question (sanitized)
- Response time
- Error details (if any)

## Error Handling

The service handles:

- Vector DB connection failures
- MongoDB connection failures
- AWS Bedrock timeouts
- Empty search results
- Invalid inputs
- Rate limit exceeded

## Quick Start Example

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp env.example .env
# Edit .env with your credentials

# 3. Index your documents
python index_documents.py ./docs

# 4. Start the service (use python -m uvicorn!)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. Test it
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{"user": "test", "question": "What is in the documentation?"}'
```

## Project Structure

```
AI/
├── main.py                 # FastAPI application
├── vector_db.py            # Qdrant vector database service
├── embedding_service.py   # Embedding generation (Bedrock/Local/OpenAI)
├── bedrock_service.py     # AWS Bedrock LLM integration
├── mongodb_service.py     # MongoDB product database queries
├── stash_service.py       # Stash/Bitbucket code search
├── confluence_service.py  # Confluence documentation search
├── cache_service.py       # Redis caching
├── security.py            # Input sanitization
├── config.py              # Configuration management
├── index_documents.py     # Document indexing script
├── requirements.txt       # Python dependencies
├── env.example            # Environment variables template
└── docs/                  # Documentation
    ├── API_USAGE.md
    ├── INDEXING_GUIDE.md
    ├── TITAN_V2_SETUP.md
    └── ...
```

## Documentation

- **[API_USAGE.md](API_USAGE.md)** - Complete API documentation with examples
- **[INDEXING_GUIDE.md](INDEXING_GUIDE.md)** - How to index documents and codebase
- **[TITAN_V2_SETUP.md](TITAN_V2_SETUP.md)** - Amazon Titan V2 embedding setup
- **[QDRANT_SETUP.md](QDRANT_SETUP.md)** - Qdrant vector database setup
- **[STASH_CONFLUENCE_SETUP.md](STASH_CONFLUENCE_SETUP.md)** - Stash and Confluence integration
- **[EMBEDDING_ALTERNATIVES.md](EMBEDDING_ALTERNATIVES.md)** - Embedding provider options
- **[ADD_EMBEDDINGS_GUIDE.md](ADD_EMBEDDINGS_GUIDE.md)** - How to add embeddings via API
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design

## Testing

### Test Embedding Generation

```bash
python test_embedding_generation.py
```

### Test API Endpoints

```bash
# Test health check
curl http://localhost:8000/health

# Test question endpoint
python example_request.py

# Test adding embeddings
python example_add_embedding.py
```

## Development

Run with hot reload:

```bash
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest tests/  # If you have tests
```

## Troubleshooting

### Common Issues

1. **Qdrant connection failed**
   - Verify `QDRANT_URL` and `QDRANT_API_KEY` in `.env`
   - Check network connectivity

2. **Bedrock access denied**
   - Request model access in AWS Console → Bedrock → Model access
   - Verify AWS credentials

3. **Embedding generation fails**
   - Check embedding provider configuration
   - Verify API keys/credentials
   - Check dimension matches model output

4. **MongoDB connection failed**
   - Verify `MONGODB_URI` in `.env`
   - Check MongoDB credentials and network connectivity
   - Ensure database and collection names are correct

5. **Collection dimension mismatch**
   - Delete existing collection
   - Re-index with correct dimension

See individual setup guides for detailed troubleshooting.

## Contributing

1. Follow existing code patterns
2. Add tests for new features
3. Update documentation
4. Ensure code passes linting

## License

MIT

## Support

For issues and questions:

- Check the documentation in the `docs/` directory
- Review setup guides for your specific configuration
- Check logs for detailed error messages
