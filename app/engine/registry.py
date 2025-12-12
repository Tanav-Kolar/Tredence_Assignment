"""
Tool registry for workflow nodes.

Provides a decorator-based registration system that allows functions
to be referenced by string names in workflow definitions.
"""

from typing import Any, Callable, TypeVar

# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., Any])

# Global registry mapping tool names to their implementations
TOOL_REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_tool(name: str) -> Callable[[F], F]:
    """
    Decorator to register a function as a workflow tool.
    
    Registered tools can be referenced by their string name in workflow
    graph definitions, enabling dynamic node resolution at runtime.
    
    Args:
        name: The string identifier for this tool. Must be unique.
    
    Returns:
        A decorator that registers the function and returns it unchanged.
    
    Raises:
        ValueError: If a tool with the same name is already registered.
    
    Example:
        @register_tool("analyze_syntax")
        async def analyze_syntax(state: dict[str, Any]) -> dict[str, Any]:
            # Process state and return modified state
            return {**state, "syntax_valid": True}
    """
    def decorator(func: F) -> F:
        if name in TOOL_REGISTRY:
            raise ValueError(
                f"Tool '{name}' is already registered. "
                f"Existing: {TOOL_REGISTRY[name].__name__}, "
                f"New: {func.__name__}"
            )
        TOOL_REGISTRY[name] = func
        return func
    
    return decorator


def get_tool(name: str) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """
    Retrieve a registered tool by name.
    
    Args:
        name: The string identifier of the tool to retrieve.
    
    Returns:
        The registered tool function, or None if not found.
    
    Example:
        tool = get_tool("analyze_syntax")
        if tool:
            new_state = await tool(current_state)
    """
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[str]:
    """
    List all registered tool names.
    
    Returns:
        A list of all registered tool names.
    
    Example:
        available = list_tools()
        print(f"Available tools: {available}")
    """
    return list(TOOL_REGISTRY.keys())


def clear_registry() -> None:
    """
    Clear all registered tools.
    
    Primarily useful for testing to reset state between test cases.
    """
    TOOL_REGISTRY.clear()
