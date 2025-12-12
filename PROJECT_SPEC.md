# Project Specification: Mini-Agent Workflow Engine (PostgreSQL Version)

## 1. Project Overview
We are building a lightweight backend workflow engine similar to a simplified "LangGraph." The goal is to define, connect, and execute sequences of steps (nodes) where state is passed between them.

**Critical Constraints:**
* **Pure Backend:** No frontend required.
* **No AI/ML Models:** Do not use OpenAI, LangChain, or HuggingFace. The logic must be pure Python (rule-based).
* **Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLModel (PostgreSQL + asyncpg).

## 2. Core Architecture
The system consists of two main parts: the **Graph Engine** and the **API Layer**.

### 2.1 The Graph Engine (`/app/engine`)
The engine must manage a "State Machine" workflow.
* **State:** A generic dictionary or Pydantic model that accumulates data as it moves through nodes.
* **Nodes:** Standard Python functions. They accept `State` and return a modified `State`.
* **Edges:** Define the flow. We need standard edges (A -> B) and conditional edges (A -> B if X, else C).
* **Registry Pattern:** Implement a decorator `@register_tool` to register functions so they can be referenced by string names in the API.

### 2.2 Data Persistence (`/app/db`)
Use **PostgreSQL** with **SQLModel** (async) to store:
1.  **Workflows:** JSON definition of nodes and edges.
2.  **Runs:** The history/logs of a specific execution.

**Infrastructure:**
* Include a `docker-compose.yml` file to spin up the PostgreSQL container easily.

## 3. Implementation Steps for AI

### Step 1: Infrastructure & Models
1.  Create `docker-compose.yml` for PostgreSQL.
2.  Create `database.py` using `SQLModel` and `async_engine`.
3.  Create `schemas.py`:
    * `WorkflowDefinition`: Stores the graph structure (JSONB column for nodes/edges).
    * `WorkflowRun`: Stores the current state and execution logs (JSONB).

### Step 2: Build the Engine Logic
Create `engine.py`.
* Implement a `WorkflowEngine` class.
* It should have a method `run(start_node, initial_state)`.
* Use a `while` loop to traverse the graph.
* Support **Branching**: Check the state to decide the next node.

### Step 3: Implement the "Code Review" Agent (Option A)
Implement the specific logic for the assignment using pure Python `ast` module.
* **Location:** `/app/workflows/code_review.py`
* **Tools to Implement:**
    1.  `analyze_syntax(code)`: Use `ast.parse()` to check for syntax errors.
    2.  `check_style(code)`: Fail if the code contains `print()` (enforce `logging` instead).
    3.  `score_code(code)`: Start at 100. Deduct 10 points for every "bad" pattern found.
    4.  **Looping Logic**: If `score < 80`, route back to a "refine" step (mock refinement).

### Step 4: FastAPI Endpoints
Expose the engine via `main.py`.
* `POST /graph/create`: Saves a graph definition to Postgres. Returns `graph_id`.
* `POST /graph/run`: Accepts `graph_id` and `input`. Triggers the engine. Returns `run_id` + final state.
* `GET /graph/state/{run_id}`: Returns the current state of a run from Postgres.

## 4. Specific Code Requirements
* **Type Hinting:** Use strict type hints everywhere.
* **Async/Await:** The engine execution and DB calls must be `async`.
* **Docstrings:** All functions must have docstrings explaining the logic.
* **Error Handling:** Gracefully handle cases where a node name in the graph does not exist in the registry.

## 5. Bonus Features (Include if possible)
* **WebSocket:** `/ws/graph/{run_id}` that streams the state updates in real-time as nodes finish execution.