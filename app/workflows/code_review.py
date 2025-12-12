"""
Code Review Workflow Tools.

Implements pure Python code analysis tools using the AST module.
These tools form a code review workflow with syntax checking,
style enforcement, scoring, and iterative refinement.

Workflow Graph:
    analyze_syntax -> check_style -> score_code -> [score < 80 ? refine_code : __end__]
                                                         |
                                                         v
                                                   check_style (loop)
"""

import ast
import re
from typing import Any

from app.engine.registry import register_tool


# Maximum refinement iterations to prevent infinite loops
MAX_REFINEMENT_ITERATIONS = 3


@register_tool("analyze_syntax")
def analyze_syntax(state: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze Python code for syntax errors using AST parsing.
    
    Uses the `ast.parse()` function to check if the provided code
    is syntactically valid Python.
    
    Args:
        state: Workflow state containing 'code' key with Python source.
    
    Returns:
        Updated state with:
        - syntax_valid (bool): Whether the code has valid syntax.
        - syntax_error (str | None): Error message if syntax is invalid.
        - ast_node_count (int): Number of AST nodes (complexity indicator).
    
    Example:
        state = {"code": "def foo(): pass"}
        result = analyze_syntax(state)
        # result["syntax_valid"] == True
    """
    code = state.get("code", "")
    
    try:
        tree = ast.parse(code)
        
        # Count AST nodes as a simple complexity metric
        node_count = sum(1 for _ in ast.walk(tree))
        
        return {
            **state,
            "syntax_valid": True,
            "syntax_error": None,
            "ast_node_count": node_count,
        }
    except SyntaxError as e:
        return {
            **state,
            "syntax_valid": False,
            "syntax_error": f"Line {e.lineno}: {e.msg}",
            "ast_node_count": 0,
        }


@register_tool("check_style")
def check_style(state: dict[str, Any]) -> dict[str, Any]:
    """
    Check code style and enforce logging over print statements.
    
    Scans the code for style violations, particularly the use of
    print() statements which should be replaced with proper logging.
    
    Args:
        state: Workflow state containing 'code' key with Python source.
    
    Returns:
        Updated state with:
        - style_issues (list[str]): List of style violation messages.
        - has_print_statements (bool): Whether print() was found.
        - style_passed (bool): Whether all style checks passed.
    
    Example:
        state = {"code": "print('hello')"}
        result = check_style(state)
        # result["has_print_statements"] == True
        # result["style_passed"] == False
    """
    code = state.get("code", "")
    style_issues: list[str] = []
    
    # Skip style check if syntax is invalid
    if not state.get("syntax_valid", True):
        return {
            **state,
            "style_issues": ["Skipped: syntax errors present"],
            "has_print_statements": False,
            "style_passed": False,
        }
    
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {
            **state,
            "style_issues": ["Unable to parse code for style checking"],
            "has_print_statements": False,
            "style_passed": False,
        }
    
    # Check for print() calls
    has_print = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                has_print = True
                style_issues.append(
                    f"Line {node.lineno}: Use logging instead of print()"
                )
    
    # Check for overly long lines (basic check via string analysis)
    lines = code.split("\n")
    for i, line in enumerate(lines, 1):
        if len(line) > 100:
            style_issues.append(
                f"Line {i}: Line exceeds 100 characters ({len(line)} chars)"
            )
    
    # Check for missing docstrings in functions/classes
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring = ast.get_docstring(node)
            if docstring is None:
                style_issues.append(
                    f"Line {node.lineno}: {node.name} missing docstring"
                )
    
    return {
        **state,
        "style_issues": style_issues,
        "has_print_statements": has_print,
        "style_passed": len(style_issues) == 0,
    }


@register_tool("score_code")
def score_code(state: dict[str, Any]) -> dict[str, Any]:
    """
    Calculate a quality score for the code based on detected issues.
    
    Starts with a perfect score of 100 and deducts points for
    each type of issue found during analysis.
    
    Scoring:
        - Syntax error: -50 points
        - Each print() statement: -10 points
        - Each style issue: -5 points
        - No docstrings: -5 points each
        - Long lines: -2 points each
    
    Args:
        state: Workflow state containing analysis results.
    
    Returns:
        Updated state with:
        - score (int): Quality score from 0-100.
        - score_breakdown (dict): Detailed deduction breakdown.
        - needs_refinement (bool): True if score < 80.
    
    Example:
        state = {"syntax_valid": True, "style_issues": [...]}
        result = score_code(state)
        # result["score"] == 85
    """
    score = 100
    breakdown: dict[str, int] = {}
    
    # Deduct for syntax errors
    if not state.get("syntax_valid", True):
        deduction = 50
        breakdown["syntax_error"] = deduction
        score -= deduction
    
    # Deduct for print statements
    if state.get("has_print_statements", False):
        # Count print-related issues
        print_count = sum(
            1 for issue in state.get("style_issues", [])
            if "print()" in issue
        )
        deduction = print_count * 10
        breakdown["print_statements"] = deduction
        score -= deduction
    
    # Deduct for other style issues
    style_issues = state.get("style_issues", [])
    for issue in style_issues:
        if "print()" in issue:
            continue  # Already counted
        elif "docstring" in issue.lower():
            deduction = 5
            breakdown["missing_docstrings"] = breakdown.get("missing_docstrings", 0) + deduction
            score -= deduction
        elif "exceeds" in issue.lower():
            deduction = 2
            breakdown["long_lines"] = breakdown.get("long_lines", 0) + deduction
            score -= deduction
        else:
            deduction = 5
            breakdown["other_issues"] = breakdown.get("other_issues", 0) + deduction
            score -= deduction
    
    # Ensure score doesn't go below 0
    score = max(0, score)
    
    # Check if refinement is needed
    needs_refinement = score < 80
    
    # Track refinement iteration
    iteration = state.get("refinement_iteration", 0)
    
    return {
        **state,
        "score": score,
        "score_breakdown": breakdown,
        "needs_refinement": needs_refinement,
        "refinement_iteration": iteration,
    }


@register_tool("refine_code")
def refine_code(state: dict[str, Any]) -> dict[str, Any]:
    """
    Attempt to refine the code to address identified issues.
    
    This is a mock refinement step that simulates code improvement.
    In a real implementation, this could use an LLM or rule-based
    transformations. Here, it applies simple transformations.
    
    Transformations applied:
        - Replace print() with logging.info()
        - Add basic docstrings to functions/classes
        - Increment refinement counter
    
    Args:
        state: Workflow state containing code and identified issues.
    
    Returns:
        Updated state with:
        - code (str): Refined version of the code.
        - refinement_iteration (int): Incremented iteration counter.
        - refinement_applied (list[str]): List of applied refinements.
    
    Note:
        After MAX_REFINEMENT_ITERATIONS (3), no more refinements
        are applied to prevent infinite loops.
    """
    code = state.get("code", "")
    iteration = state.get("refinement_iteration", 0) + 1
    refinements: list[str] = []
    
    # Check iteration limit
    if iteration > MAX_REFINEMENT_ITERATIONS:
        return {
            **state,
            "refinement_iteration": iteration,
            "refinement_applied": ["Max iterations reached, stopping refinement"],
            "needs_refinement": False,  # Force exit from loop
        }
    
    # Replace print() with logging.info()
    if state.get("has_print_statements", False):
        # Simple regex replacement (basic approach)
        new_code = re.sub(
            r'\bprint\s*\(',
            'logging.info(',
            code
        )
        if new_code != code:
            # Add logging import if not present
            if "import logging" not in new_code:
                new_code = "import logging\n\n" + new_code
            code = new_code
            refinements.append("Replaced print() with logging.info()")
    
    # Add placeholder docstrings to functions/classes without them
    try:
        tree = ast.parse(code)
        lines = code.split("\n")
        insertions: list[tuple[int, str, int]] = []  # (line_no, docstring, indent)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if ast.get_docstring(node) is None:
                    # Calculate indentation
                    func_line = lines[node.lineno - 1]
                    indent = len(func_line) - len(func_line.lstrip()) + 4
                    docstring = f'{" " * indent}"""TODO: Add docstring for {node.name}."""'
                    insertions.append((node.lineno, docstring, indent))
                    refinements.append(f"Added docstring placeholder for {node.name}()")
            elif isinstance(node, ast.ClassDef):
                if ast.get_docstring(node) is None:
                    class_line = lines[node.lineno - 1]
                    indent = len(class_line) - len(class_line.lstrip()) + 4
                    docstring = f'{" " * indent}"""TODO: Add docstring for {node.name} class."""'
                    insertions.append((node.lineno, docstring, indent))
                    refinements.append(f"Added docstring placeholder for class {node.name}")
        
        # Apply insertions in reverse order to preserve line numbers
        for line_no, docstring, _ in sorted(insertions, key=lambda x: x[0], reverse=True):
            lines.insert(line_no, docstring)
        
        code = "\n".join(lines)
        
    except SyntaxError:
        refinements.append("Could not parse code for docstring insertion")
    
    return {
        **state,
        "code": code,
        "refinement_iteration": iteration,
        "refinement_applied": refinements,
    }


def get_code_review_graph() -> dict[str, Any]:
    """
    Return the graph definition for the code review workflow.
    
    This graph defines the flow:
        analyze_syntax -> check_style -> score_code -> [conditional] -> refine_code/end
    
    Returns:
        A graph definition dict compatible with WorkflowEngine.
    """
    return {
        "nodes": [
            "analyze_syntax",
            "check_style",
            "score_code",
            "refine_code",
        ],
        "edges": {
            "analyze_syntax": "check_style",
            "check_style": "score_code",
            "refine_code": "check_style",  # Loop back for re-evaluation
        },
        "conditional_edges": {
            "score_code": {
                "condition": "state.needs_refinement and state.refinement_iteration < 3",
                "true_next": "refine_code",
                "false_next": "__end__",
            }
        },
        "start_node": "analyze_syntax",
    }
