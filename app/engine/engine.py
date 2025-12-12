"""
Workflow execution engine.

Provides the core WorkflowEngine class that executes workflow graphs
by traversing nodes and managing state transitions.
"""

import asyncio
import inspect
from datetime import datetime
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schemas import RunStatus, WorkflowRun
from app.engine.registry import get_tool


# Special node name indicating workflow termination
END_NODE = "__end__"


class WorkflowEngineError(Exception):
    """Base exception for workflow engine errors."""
    pass


class NodeNotFoundError(WorkflowEngineError):
    """Raised when a referenced node is not found in the registry."""
    
    def __init__(self, node_name: str):
        self.node_name = node_name
        super().__init__(f"Node '{node_name}' not found in tool registry")


class InvalidGraphError(WorkflowEngineError):
    """Raised when the graph definition is invalid."""
    pass


class WorkflowEngine:
    """
    State machine executor for workflow graphs.
    
    The engine traverses a directed graph of nodes, executing each node's
    tool function and passing the accumulated state between them. Supports
    both standard edges (A -> B) and conditional edges (A -> B if X else C).
    
    Attributes:
        session: Async database session for persisting run state.
        on_node_complete: Optional callback invoked after each node execution.
    
    Example:
        engine = WorkflowEngine(session)
        final_state = await engine.run(
            run_id=run_uuid,
            graph={"nodes": [...], "edges": {...}},
            start_node="analyze_syntax",
            initial_state={"code": "def foo(): pass"}
        )
    """
    
    def __init__(
        self,
        session: AsyncSession,
        on_node_complete: Callable[[UUID, str, dict[str, Any]], None] | None = None,
    ):
        """
        Initialize the workflow engine.
        
        Args:
            session: Async database session for state persistence.
            on_node_complete: Optional async callback called after each node.
                              Signature: (run_id, node_name, current_state) -> None
        """
        self.session = session
        self.on_node_complete = on_node_complete
    
    async def run(
        self,
        run_id: UUID,
        graph: dict[str, Any],
        start_node: str,
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a workflow from the start node until completion.
        
        Traverses the graph using a while loop, executing each node's tool
        and determining the next node based on edges or conditional logic.
        State is persisted to the database after each node execution.
        
        Args:
            run_id: UUID of the workflow run record.
            graph: Graph definition containing nodes, edges, and conditional_edges.
            start_node: Name of the first node to execute.
            initial_state: Initial state dictionary to pass to the first node.
        
        Returns:
            The final accumulated state after workflow completion.
        
        Raises:
            NodeNotFoundError: If a node referenced in the graph is not registered.
            InvalidGraphError: If the graph structure is invalid.
        """
        # Validate graph structure
        self._validate_graph(graph, start_node)
        
        # Initialize state and tracking
        state = initial_state.copy()
        current_node = start_node
        logs: list[dict[str, Any]] = []
        
        # Update run status to running
        await self._update_run(
            run_id,
            status=RunStatus.RUNNING,
            current_node=current_node,
            state=state,
            logs=logs,
        )
        
        try:
            # Main execution loop
            while current_node != END_NODE:
                # Get the tool for this node
                tool = get_tool(current_node)
                if tool is None:
                    raise NodeNotFoundError(current_node)
                
                # Execute the node
                node_start = datetime.utcnow()
                try:
                    # Handle both sync and async tools
                    if inspect.iscoroutinefunction(tool):
                        state = await tool(state)
                    else:
                        state = tool(state)
                    
                    log_entry = {
                        "node": current_node,
                        "timestamp": node_start.isoformat(),
                        "duration_ms": (datetime.utcnow() - node_start).total_seconds() * 1000,
                        "status": "success",
                    }
                except Exception as e:
                    log_entry = {
                        "node": current_node,
                        "timestamp": node_start.isoformat(),
                        "duration_ms": (datetime.utcnow() - node_start).total_seconds() * 1000,
                        "status": "error",
                        "error": str(e),
                    }
                    logs.append(log_entry)
                    raise
                
                logs.append(log_entry)
                
                # Determine next node
                current_node = self._get_next_node(graph, current_node, state)
                
                # Persist state
                await self._update_run(
                    run_id,
                    current_node=current_node if current_node != END_NODE else None,
                    state=state,
                    logs=logs,
                )
                
                # Invoke callback if provided
                if self.on_node_complete:
                    if inspect.iscoroutinefunction(self.on_node_complete):
                        await self.on_node_complete(run_id, current_node, state)
                    else:
                        self.on_node_complete(run_id, current_node, state)
            
            # Mark run as completed
            await self._update_run(
                run_id,
                status=RunStatus.COMPLETED,
                completed_at=datetime.utcnow(),
            )
            
            return state
            
        except Exception as e:
            # Mark run as failed
            await self._update_run(
                run_id,
                status=RunStatus.FAILED,
                error=str(e),
                completed_at=datetime.utcnow(),
                logs=logs,
            )
            raise
    
    def _validate_graph(self, graph: dict[str, Any], start_node: str) -> None:
        """
        Validate the graph structure before execution.
        
        Args:
            graph: The graph definition to validate.
            start_node: The starting node name.
        
        Raises:
            InvalidGraphError: If the graph structure is invalid.
        """
        if "nodes" not in graph:
            raise InvalidGraphError("Graph must contain 'nodes' list")
        
        nodes = set(graph.get("nodes", []))
        if start_node not in nodes:
            raise InvalidGraphError(
                f"Start node '{start_node}' not found in graph nodes"
            )
        
        # Validate edges reference existing nodes
        edges = graph.get("edges", {})
        for source, target in edges.items():
            if source not in nodes:
                raise InvalidGraphError(f"Edge source '{source}' not in nodes")
            if target != END_NODE and target not in nodes:
                raise InvalidGraphError(f"Edge target '{target}' not in nodes")
        
        # Validate conditional edges
        conditional_edges = graph.get("conditional_edges", {})
        for source, config in conditional_edges.items():
            if source not in nodes:
                raise InvalidGraphError(
                    f"Conditional edge source '{source}' not in nodes"
                )
            true_next = config.get("true_next", END_NODE)
            false_next = config.get("false_next", END_NODE)
            
            if true_next != END_NODE and true_next not in nodes:
                raise InvalidGraphError(
                    f"Conditional edge true_next '{true_next}' not in nodes"
                )
            if false_next != END_NODE and false_next not in nodes:
                raise InvalidGraphError(
                    f"Conditional edge false_next '{false_next}' not in nodes"
                )
    
    def _get_next_node(
        self,
        graph: dict[str, Any],
        current_node: str,
        state: dict[str, Any],
    ) -> str:
        """
        Determine the next node to execute based on edges and conditions.
        
        Args:
            graph: The graph definition.
            current_node: The node that just finished executing.
            state: The current accumulated state.
        
        Returns:
            The name of the next node, or END_NODE if workflow is complete.
        """
        # Check for conditional edge first
        conditional_edges = graph.get("conditional_edges", {})
        if current_node in conditional_edges:
            config = conditional_edges[current_node]
            condition = config.get("condition", "False")
            
            # Evaluate condition with state in scope
            # Using a safe evaluation approach with only state access
            try:
                result = self._evaluate_condition(condition, state)
            except Exception:
                # Default to false on evaluation error
                result = False
            
            if result:
                return config.get("true_next", END_NODE)
            else:
                return config.get("false_next", END_NODE)
        
        # Check for standard edge
        edges = graph.get("edges", {})
        if current_node in edges:
            return edges[current_node]
        
        # No edge found - end workflow
        return END_NODE
    
    def _evaluate_condition(
        self,
        condition: str,
        state: dict[str, Any],
    ) -> bool:
        """
        Safely evaluate a condition expression.
        
        Supports simple expressions like:
        - "state.score < 80"
        - "state['syntax_valid'] == True"
        - "state.get('has_errors', False)"
        
        Args:
            condition: The condition expression string.
            state: The state dictionary to evaluate against.
        
        Returns:
            Boolean result of the condition evaluation.
        """
        # Create a simple namespace for evaluation
        class StateAccessor:
            """Provides attribute-style access to state dict."""
            
            def __init__(self, data: dict[str, Any]):
                self._data = data
            
            def __getattr__(self, name: str) -> Any:
                return self._data.get(name)
            
            def __getitem__(self, key: str) -> Any:
                return self._data.get(key)
            
            def get(self, key: str, default: Any = None) -> Any:
                return self._data.get(key, default)
        
        # Allowed names for evaluation
        safe_globals = {
            "__builtins__": {},
            "True": True,
            "False": False,
            "None": None,
        }
        safe_locals = {
            "state": StateAccessor(state),
        }
        
        # Evaluate with restricted scope
        return bool(eval(condition, safe_globals, safe_locals))
    
    async def _update_run(
        self,
        run_id: UUID,
        status: RunStatus | None = None,
        current_node: str | None = None,
        state: dict[str, Any] | None = None,
        logs: list[dict[str, Any]] | None = None,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """
        Update a workflow run record in the database.
        
        Only updates fields that are provided (not None).
        
        Args:
            run_id: UUID of the run to update.
            status: New status value.
            current_node: Current node being executed.
            state: Current accumulated state.
            logs: Execution logs.
            error: Error message if failed.
            completed_at: Completion timestamp.
        """
        result = await self.session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        
        if run is None:
            return
        
        if status is not None:
            run.status = status
        if current_node is not None:
            run.current_node = current_node
        if state is not None:
            run.state = state
        if logs is not None:
            run.logs = logs
        if error is not None:
            run.error = error
        if completed_at is not None:
            run.completed_at = completed_at
        
        self.session.add(run)
        await self.session.flush()
