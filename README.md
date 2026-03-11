# Enterprise Data Agent

Production-quality multi-warehouse AI agent that queries Oracle databases using natural language. Built with a **Java Spring Boot** backend, **Python LangGraph** agent orchestration, and **Python MCP servers** for Oracle DB access.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Java Backend   │────▶│  LangGraph Agent │────▶│  MCP Server HQ  │──▶ Oracle HQ
│  (Spring Boot)  │     │  (Python/FastAPI) │     └─────────────────┘
│                 │     │                   │     ┌─────────────────┐
│  REST API       │     │  RAG Search       │────▶│  MCP Server East│──▶ Oracle East
│  Auth / CORS    │     │  Cache Check      │     └─────────────────┘
│  Rate Limiting  │     │  SQL Generation   │     ┌─────────────────┐
│                 │     │  Reflection       │────▶│  MCP Server West│──▶ Oracle West
└────────┬────────┘     └────────┬──────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
    ┌─────────┐           ┌──────────┐
    │  Redis  │◀─────────▶│ ChromaDB │
    │ (Cache) │           │  (RAG)   │
    └─────────┘           └──────────┘
```

## Agent Flow

1. **User query** → Java backend receives natural language question
2. **RAG search** → Agent searches ChromaDB for relevant table metadata
3. **Cache check** → Redis lookup: `mcp:{db}:{table}:{query_hash}`
4. **MCP query** → On cache miss, execute read-only SQL via MCP server
5. **Reflection** → LLM analyzes raw data: trends, comparisons, anomalies
6. **Cache store** → Results cached in Redis with smart TTLs
7. **Response** → CEO-level briefing: numbers, trends, red flags

## Components

| Component | Tech | Port | Description |
|-----------|------|------|-------------|
| Java Backend | Spring Boot 3.4, Java 21 | 8080 | REST API, Redis cache, auth |
| Agent Service | Python 3.11, LangGraph, FastAPI | 8001 | AI agent orchestration, RAG, MCP client |
| MCP Servers | Python 3.11, MCP SDK | stdio | Oracle DB access (one per warehouse) |
| Redis | Redis 7 | 6379 | Query result cache |
| ChromaDB | Embedded | — | Vector store for table metadata |

## Quick Start

### Prerequisites
- Docker & Docker Compose
- OpenAI API key
- Oracle database instance(s)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your Oracle credentials and OpenAI API key
```

### 2. Configure warehouses

Edit `config/warehouses.json` to match your Oracle instances:

```json
[
  {
    "warehouse_id": "hq",
    "label": "HQ Warehouse",
    "mcp_command": "python",
    "mcp_args": ["-m", "src.server"],
    "mcp_cwd": "/app/mcp-server",
    "mcp_env": {
      "ORACLE_HOST": "your-oracle-host",
      "ORACLE_PORT": "1521",
      "ORACLE_SERVICE_NAME": "ORCL",
      "ORACLE_USER": "readonly_user",
      "ORACLE_PASSWORD": "your-password",
      "MCP_WAREHOUSE_ID": "hq",
      "MCP_READ_ONLY": "true"
    }
  }
]
```

### 3. Start services

```bash
docker compose up -d
```

### 4. Sync metadata (first run)

```bash
curl -X POST http://localhost:8080/api/warehouses/sync
```

### 5. Query

```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are our Q2 sales targets by region?"}'
```

## API Endpoints

### Query
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/query` | Submit a natural language query |

### Warehouses
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/warehouses` | List connected warehouses |
| POST | `/api/warehouses/sync` | Sync metadata from all warehouses |
| POST | `/api/warehouses/search` | Search RAG metadata store |

### Cache
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cache/stats` | Get cache statistics |
| GET | `/api/cache/keys` | List cached keys |
| DELETE | `/api/cache/{warehouseId}/{tableName}` | Invalidate table cache |
| DELETE | `/api/cache/{warehouseId}` | Invalidate warehouse cache |
| DELETE | `/api/cache` | Invalidate all cache |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Full health check |
| GET | `/actuator/health` | Spring Boot health |

## Cache Strategy

| Data Type | TTL | Pattern |
|-----------|-----|---------|
| Live sales/orders | 5 min | `SALES`, `ORDERS`, `TRANSACTIONS` |
| Reference/targets | 1 hour | `TARGETS`, `CONFIG`, `REFERENCE` |
| Default | 1 hour | Everything else |

Key format: `mcp:{warehouse_id}:{table_name}:{query_sha256_prefix}`

## Safety

- **Read-only enforcement**: MCP servers reject any INSERT/UPDATE/DELETE/DDL
- **Query validation**: Regex-based SQL statement classification
- **Rate limiting**: Redis + MCP connection timeouts
- **No credential exposure**: All secrets via environment variables

## Adding a New Warehouse

1. Add Oracle connection to `.env`
2. Add entry to `config/warehouses.json`
3. Add MCP server service to `docker-compose.yml`
4. Restart: `docker compose up -d`
5. Sync metadata: `curl -X POST http://localhost:8080/api/warehouses/sync`

No code changes required.

## Development

### Java Backend
```bash
cd java-backend
mvn spring-boot:run
```

### Agent Service
```bash
cd agent-service
poetry install
poetry run uvicorn src.main:app --reload --port 8001
```

### MCP Server (standalone)
```bash
cd mcp-server
poetry install
poetry run python -m src.server
```
