"""
API request and response models.

Pydantic models for validating API inputs and structuring outputs.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Graph/Workflow Endpoints
# =============================================================================

class GraphCreateRequest(BaseModel):
    """Request body for creating a new workflow graph."""
    
    name: str = Field(..., description="Human-readable workflow name")
    description: str | None = Field(None, description="Optional workflow description")
    graph: dict[str, Any] = Field(
        ...,
        description="Graph definition with nodes, edges, and conditional_edges",
        examples=[{
            "nodes": ["analyze_syntax", "check_style", "score_code"],
            "edges": {"analyze_syntax": "check_style", "check_style": "score_code"},
            "conditional_edges": {},
            "start_node": "analyze_syntax"
        }]
    )


class GraphCreateResponse(BaseModel):
    """Response after successfully creating a workflow graph."""
    
    graph_id: UUID = Field(..., description="Unique identifier for the created workflow")
    name: str = Field(..., description="Workflow name")
    message: str = Field(default="Workflow created successfully")


class GraphRunRequest(BaseModel):
    """Request body for executing a workflow."""
    
    graph_id: UUID = Field(..., description="ID of the workflow to execute")
    input: dict[str, Any] = Field(
        ...,
        description="Initial state/input data for the workflow",
        examples=[{"code": "def hello(): print('world')"}]
    )
    start_node: str | None = Field(
        None,
        description="Optional override for starting node (defaults to graph's start_node)"
    )


class GraphRunResponse(BaseModel):
    """Response after triggering a workflow execution."""
    
    run_id: UUID = Field(..., description="Unique identifier for this execution run")
    graph_id: UUID = Field(..., description="ID of the executed workflow")
    status: str = Field(..., description="Current run status")
    final_state: dict[str, Any] = Field(..., description="Final accumulated state")
    logs: list[dict[str, Any]] = Field(default_factory=list, description="Execution logs")


class GraphStateResponse(BaseModel):
    """Response for querying run state."""
    
    run_id: UUID = Field(..., description="Execution run ID")
    workflow_id: UUID = Field(..., description="Associated workflow ID")
    status: str = Field(..., description="Current status (pending, running, completed, failed)")
    current_node: str | None = Field(None, description="Currently executing node")
    state: dict[str, Any] = Field(..., description="Current accumulated state")
    logs: list[dict[str, Any]] = Field(default_factory=list, description="Execution logs")
    error: str | None = Field(None, description="Error message if failed")
    started_at: datetime = Field(..., description="Execution start time")
    completed_at: datetime | None = Field(None, description="Execution completion time")


# =============================================================================
# Utility Endpoints
# =============================================================================

class ToolListResponse(BaseModel):
    """Response listing all registered tools."""
    
    tools: list[str] = Field(..., description="List of registered tool names")
    count: int = Field(..., description="Total number of tools")


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(default="healthy")
    database: str = Field(..., description="Database connection status")
    version: str = Field(default="1.0.0")


class ErrorResponse(BaseModel):
    """Standard error response format."""
    
    error: str = Field(..., description="Error type/code")
    detail: str = Field(..., description="Human-readable error message")
    path: str | None = Field(None, description="Request path that caused the error")
