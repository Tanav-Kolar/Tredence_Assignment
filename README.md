# Mini-Agent Workflow Engine

A lightweight backend workflow engine for defining, connecting, and executing sequences of processing steps (nodes) with state passing—similar to a simplified LangGraph.

## Features

- **Graph Engine**: State machine execution with standard and conditional edges
- **Tool Registry**: `@register_tool` decorator for dynamic node registration
- **Async PostgreSQL**: SQLModel + asyncpg for workflow persistence
- **Code Review Workflow**: Built-in AST-based Python code analysis
- **Real-time Updates**: WebSocket for live execution streaming
- **RESTful API**: FastAPI with automatic OpenAPI docs

---

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for PostgreSQL)

### 1. Setup Environment

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start PostgreSQL

```bash
# Start the database container
docker-compose up -d

# Verify it's running
docker ps
```

> **Without Docker?** Install PostgreSQL locally and create a database matching `.env` credentials.

### 3. Run the Server

```bash
uvicorn app.main:app --reload
```

Server runs at `http://localhost:8000`

### 4. Explore the API

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with DB status |
| `GET` | `/tools` | List all registered tools |
| `POST` | `/graph/create` | Create a workflow definition |
| `POST` | `/graph/run` | Execute a workflow |
| `GET` | `/graph/state/{run_id}` | Query run state |
| `POST` | `/code-review` | Quick code review (convenience) |
| `WS` | `/ws/graph/{run_id}` | Real-time execution updates |

---

## Usage Examples

### Health Check

```bash
curl http://localhost:8000/health
```

### List Available Tools

```bash
curl http://localhost:8000/tools
```

Response:
```json
{
  "tools": ["analyze_syntax", "check_style", "score_code", "refine_code"],
  "count": 4
}
```

### Quick Code Review

```bash
curl -X POST "http://localhost:8000/code-review?code=def%20hello():%20print('world')"
```

### Create a Custom Workflow

```bash
curl -X POST http://localhost:8000/graph/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Code Review",
    "description": "Custom code analysis workflow",
    "graph": {
      "nodes": ["analyze_syntax", "check_style", "score_code", "refine_code"],
      "edges": {
        "analyze_syntax": "check_style",
        "check_style": "score_code",
        "refine_code": "check_style"
      },
      "conditional_edges": {
        "score_code": {
          "condition": "state.needs_refinement and state.refinement_iteration < 3",
          "true_next": "refine_code",
          "false_next": "__end__"
        }
      },
      "start_node": "analyze_syntax"
    }
  }'
```

### Execute the Workflow

```bash
curl -X POST http://localhost:8000/graph/run \
  -H "Content-Type: application/json" \
  -d '{
    "graph_id": "<UUID_FROM_CREATE>",
    "input": {
      "code": "def hello():\n    print(\"world\")"
    }
  }'
```

### Query Run State

```bash
curl http://localhost:8000/graph/state/<RUN_ID>
```

---

## Project Structure

```
Tredence_Assignment/
├── docker-compose.yml      # PostgreSQL container
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables
├── .env.example            # Template for .env
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI application + endpoints
    ├── api_models.py       # Pydantic request/response schemas
    ├── db/
    │   ├── config.py       # Pydantic settings
    │   ├── database.py     # Async engine + sessions
    │   └── schemas.py      # SQLModel tables
    ├── engine/
    │   ├── registry.py     # @register_tool decorator
    │   └── engine.py       # WorkflowEngine class
    └── workflows/
        └── code_review.py  # Code review tools
```

---

## Code Review Tools

The built-in code review workflow includes:

| Tool | Purpose |
|------|---------|
| `analyze_syntax` | AST-based syntax validation |
| `check_style` | Detects `print()`, missing docstrings, long lines |
| `score_code` | Quality score (100 - deductions) |
| `refine_code` | Mock refinement with loop-back |

### Scoring Rules

- **Syntax error**: -50 points
- **Each `print()` statement**: -10 points
- **Missing docstring**: -5 points
- **Line > 100 chars**: -2 points

If score < 80, the workflow loops through `refine_code` (max 3 iterations).

---

## Creating Custom Tools

Register new tools using the decorator:

```python
from app.engine.registry import register_tool

@register_tool("my_custom_tool")
def my_custom_tool(state: dict) -> dict:
    """Process state and return modified state."""
    # Your logic here
    return {**state, "custom_result": "done"}
```

---

## Graph Definition Format

```json
{
  "nodes": ["node_a", "node_b", "node_c"],
  "edges": {
    "node_a": "node_b"
  },
  "conditional_edges": {
    "node_b": {
      "condition": "state.value > 10",
      "true_next": "node_c",
      "false_next": "__end__"
    }
  },
  "start_node": "node_a"
}
```

- `__end__` terminates the workflow
- Conditions support `state.key` or `state['key']` syntax

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `workflow_user` | Database username |
| `POSTGRES_PASSWORD` | `workflow_pass` | Database password |
| `POSTGRES_DB` | `workflow_engine` | Database name |
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `DATABASE_URL` | (constructed) | Full connection URL |

---

## Tech Stack

- **Python 3.10+**
- **FastAPI** - Async web framework
- **SQLModel** - ORM with Pydantic integration
- **asyncpg** - Async PostgreSQL driver
- **PostgreSQL 15** - Database (via Docker)

---

## License

MIT
