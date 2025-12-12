"""
Mini-Agent Workflow Engine - FastAPI Application.

A lightweight backend workflow engine for defining, connecting,
and executing sequences of steps (nodes) where state is passed between them.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_models import (
    ErrorResponse,
    GraphCreateRequest,
    GraphCreateResponse,
    GraphRunRequest,
    GraphRunResponse,
    GraphStateResponse,
    HealthResponse,
    ToolListResponse,
)
from app.db.database import close_db, get_session_dependency, init_db
from app.db.schemas import RunStatus, WorkflowDefinition, WorkflowRun
from app.engine.engine import (
    InvalidGraphError,
    NodeNotFoundError,
    WorkflowEngine,
)
from app.engine.registry import list_tools

# Import workflows to register their tools
import app.workflows.code_review  # noqa: F401


# =============================================================================
# WebSocket Connection Manager
# =============================================================================

class ConnectionManager:
    """
    Manages WebSocket connections for real-time state updates.
    
    Maintains a mapping of run_id to connected WebSocket clients,
    allowing targeted updates to be broadcast during workflow execution.
    """
    
    def __init__(self):
        self.active_connections: dict[UUID, list[WebSocket]] = {}
    
    async def connect(self, run_id: UUID, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection for a run."""
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
        self.active_connections[run_id].append(websocket)
    
    def disconnect(self, run_id: UUID, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if run_id in self.active_connections:
            self.active_connections[run_id].remove(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]
    
    async def broadcast(self, run_id: UUID, message: dict[str, Any]) -> None:
        """Send a message to all connected clients for a run."""
        if run_id in self.active_connections:
            for connection in self.active_connections[run_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass  # Client disconnected


manager = ConnectionManager()


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    
    Initializes the database on startup and closes connections on shutdown.
    """
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Mini-Agent Workflow Engine",
    description="A lightweight backend workflow engine for defining and executing step sequences",
    version="1.0.0",
    lifespan=lifespan,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


# =============================================================================
# Health & Utility Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Utility"])
async def health_check(
    session: AsyncSession = Depends(get_session_dependency),
) -> HealthResponse:
    """
    Check application health and database connectivity.
    
    Returns:
        Health status including database connection state.
    """
    try:
        await session.execute(select(1))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status,
    )


@app.get("/tools", response_model=ToolListResponse, tags=["Utility"])
async def get_tools() -> ToolListResponse:
    """
    List all registered workflow tools.
    
    Returns:
        List of available tool names that can be used in workflow graphs.
    """
    tools = list_tools()
    return ToolListResponse(tools=tools, count=len(tools))


# =============================================================================
# Graph/Workflow Endpoints
# =============================================================================

@app.post("/graph/create", response_model=GraphCreateResponse, tags=["Workflow"])
async def create_graph(
    request: GraphCreateRequest,
    session: AsyncSession = Depends(get_session_dependency),
) -> GraphCreateResponse:
    """
    Create a new workflow graph definition.
    
    Validates the graph structure and persists it to the database.
    
    Args:
        request: Graph definition including name, description, and structure.
    
    Returns:
        The created graph's ID and confirmation message.
    
    Raises:
        HTTPException 400: If the graph structure is invalid.
    """
    # Validate graph has required structure
    graph = request.graph
    if "nodes" not in graph:
        raise HTTPException(
            status_code=400,
            detail="Graph must contain 'nodes' list"
        )
    
    if "start_node" not in graph:
        raise HTTPException(
            status_code=400,
            detail="Graph must specify 'start_node'"
        )
    
    # Validate start_node exists in nodes
    if graph["start_node"] not in graph["nodes"]:
        raise HTTPException(
            status_code=400,
            detail=f"start_node '{graph['start_node']}' not found in nodes list"
        )
    
    # Create workflow definition
    workflow = WorkflowDefinition(
        name=request.name,
        description=request.description,
        graph=graph,
    )
    
    session.add(workflow)
    await session.flush()
    
    return GraphCreateResponse(
        graph_id=workflow.id,
        name=workflow.name,
    )


@app.post("/graph/run", response_model=GraphRunResponse, tags=["Workflow"])
async def run_graph(
    request: GraphRunRequest,
    session: AsyncSession = Depends(get_session_dependency),
) -> GraphRunResponse:
    """
    Execute a workflow graph with the provided input.
    
    Creates a new run record, executes the workflow engine,
    and returns the final state upon completion.
    
    Args:
        request: Graph ID, initial input state, and optional start node override.
    
    Returns:
        Run ID, final state, and execution logs.
    
    Raises:
        HTTPException 404: If the graph ID doesn't exist.
        HTTPException 400: If the graph has invalid structure or missing nodes.
    """
    # Fetch workflow definition
    result = await session.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == request.graph_id)
    )
    workflow = result.scalar_one_or_none()
    
    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow with ID '{request.graph_id}' not found"
        )
    
    # Determine start node
    graph = workflow.graph
    start_node = request.start_node or graph.get("start_node")
    
    if not start_node:
        raise HTTPException(
            status_code=400,
            detail="No start_node specified in request or graph definition"
        )
    
    # Create run record
    run = WorkflowRun(
        workflow_id=workflow.id,
        status=RunStatus.PENDING,
        state=request.input,
    )
    session.add(run)
    await session.flush()
    
    # Create callback for WebSocket updates
    async def on_node_complete(run_id: UUID, node_name: str, state: dict[str, Any]) -> None:
        await manager.broadcast(run_id, {
            "event": "node_complete",
            "node": node_name,
            "state": state,
        })
    
    # Execute workflow
    engine = WorkflowEngine(session, on_node_complete=on_node_complete)
    
    try:
        final_state = await engine.run(
            run_id=run.id,
            graph=graph,
            start_node=start_node,
            initial_state=request.input,
        )
    except NodeNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Node '{e.node_name}' referenced in graph is not registered"
        )
    except InvalidGraphError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    
    # Fetch updated run record
    await session.refresh(run)
    
    # Broadcast completion
    await manager.broadcast(run.id, {
        "event": "workflow_complete",
        "status": run.status.value,
        "final_state": final_state,
    })
    
    return GraphRunResponse(
        run_id=run.id,
        graph_id=workflow.id,
        status=run.status.value,
        final_state=final_state,
        logs=run.logs,
    )


@app.get("/graph/state/{run_id}", response_model=GraphStateResponse, tags=["Workflow"])
async def get_run_state(
    run_id: UUID,
    session: AsyncSession = Depends(get_session_dependency),
) -> GraphStateResponse:
    """
    Retrieve the current state of a workflow run.
    
    Args:
        run_id: UUID of the run to query.
    
    Returns:
        Current run status, state, logs, and metadata.
    
    Raises:
        HTTPException 404: If the run ID doesn't exist.
    """
    result = await session.execute(
        select(WorkflowRun).where(WorkflowRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run with ID '{run_id}' not found"
        )
    
    return GraphStateResponse(
        run_id=run.id,
        workflow_id=run.workflow_id,
        status=run.status.value,
        current_node=run.current_node,
        state=run.state,
        logs=run.logs,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


# =============================================================================
# WebSocket Endpoint (Bonus Feature)
# =============================================================================

@app.websocket("/ws/graph/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: UUID):
    """
    WebSocket endpoint for real-time workflow state updates.
    
    Clients can connect to receive live updates as nodes complete
    during workflow execution. Messages are JSON objects with:
    - event: "node_complete" | "workflow_complete"
    - node: Current node name (for node_complete)
    - state: Current accumulated state
    - status: Final status (for workflow_complete)
    
    Args:
        websocket: The WebSocket connection.
        run_id: UUID of the run to subscribe to.
    """
    await manager.connect(run_id, websocket)
    try:
        while True:
            # Keep connection alive, waiting for messages
            # Client can send ping messages which we ignore
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)


# =============================================================================
# Code Review Convenience Endpoint
# =============================================================================

@app.post("/code-review", response_model=GraphRunResponse, tags=["Code Review"])
async def run_code_review(
    code: str,
    session: AsyncSession = Depends(get_session_dependency),
) -> GraphRunResponse:
    """
    Convenience endpoint to run the code review workflow.
    
    This creates a temporary code review graph and executes it
    with the provided code, returning the analysis results.
    
    Args:
        code: Python source code to analyze.
    
    Returns:
        Analysis results including syntax validity, style issues, and score.
    """
    from app.workflows.code_review import get_code_review_graph
    
    graph = get_code_review_graph()
    
    # Create temporary workflow
    workflow = WorkflowDefinition(
        name="Code Review (Temporary)",
        description="Temporary code review workflow",
        graph=graph,
    )
    session.add(workflow)
    await session.flush()
    
    # Create run
    run = WorkflowRun(
        workflow_id=workflow.id,
        status=RunStatus.PENDING,
        state={"code": code},
    )
    session.add(run)
    await session.flush()
    
    # Execute
    engine = WorkflowEngine(session)
    
    try:
        final_state = await engine.run(
            run_id=run.id,
            graph=graph,
            start_node=graph["start_node"],
            initial_state={"code": code},
        )
    except (NodeNotFoundError, InvalidGraphError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    await session.refresh(run)
    
    return GraphRunResponse(
        run_id=run.id,
        graph_id=workflow.id,
        status=run.status.value,
        final_state=final_state,
        logs=run.logs,
    )
