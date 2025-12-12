"""
Database schemas for workflow storage.

Defines SQLModel tables for persisting workflow definitions and execution runs.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class RunStatus(str, Enum):
    """Possible states for a workflow run."""
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowDefinition(SQLModel, table=True):
    """
    Stores a workflow graph definition.
    
    A workflow consists of nodes (processing steps) and edges (connections
    between nodes). The graph structure is stored as JSONB for flexibility.
    
    Attributes:
        id: Unique identifier for the workflow.
        name: Human-readable workflow name.
        description: Optional description of what the workflow does.
        graph: JSONB containing nodes, edges, and conditional_edges.
        created_at: Timestamp when the workflow was created.
        updated_at: Timestamp when the workflow was last modified.
    
    Example graph structure:
        {
            "nodes": ["analyze_syntax", "check_style", "score_code"],
            "edges": {
                "analyze_syntax": "check_style",
                "check_style": "score_code"
            },
            "conditional_edges": {
                "score_code": {
                    "condition": "state.score < 80",
                    "true_next": "refine_code",
                    "false_next": "__end__"
                }
            },
            "start_node": "analyze_syntax"
        }
    """
    
    __tablename__ = "workflow_definitions"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str | None = Field(default=None)
    graph: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WorkflowRun(SQLModel, table=True):
    """
    Stores the execution history and state of a workflow run.
    
    Each run tracks the current execution state, accumulated data,
    and a log of all node executions for debugging and audit purposes.
    
    Attributes:
        id: Unique identifier for this run.
        workflow_id: Reference to the workflow definition being executed.
        status: Current execution status (pending, running, completed, failed).
        current_node: The node currently being or last executed.
        state: JSONB containing the accumulated state data.
        logs: JSONB array of execution log entries.
        error: Error message if the run failed.
        started_at: Timestamp when execution began.
        completed_at: Timestamp when execution finished (success or failure).
    
    Example state:
        {
            "code": "def foo(): print('hello')",
            "syntax_valid": true,
            "style_issues": ["print() found at line 1"],
            "score": 90
        }
    
    Example logs:
        [
            {"node": "analyze_syntax", "timestamp": "...", "result": "passed"},
            {"node": "check_style", "timestamp": "...", "result": "warning"}
        ]
    """
    
    __tablename__ = "workflow_runs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workflow_id: UUID = Field(foreign_key="workflow_definitions.id", index=True)
    status: RunStatus = Field(default=RunStatus.PENDING)
    current_node: str | None = Field(default=None)
    state: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    logs: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    error: str | None = Field(default=None)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None)
