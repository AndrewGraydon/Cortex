"""Calculator tool — safe math evaluation. Tier 0 (safe)."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from typing import Any

from cortex.agent.types import ToolResult

# Safe operators for math evaluation (binary and unary)
SAFE_BIN_OPS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

SAFE_UNARY_OPS: dict[type, Callable[..., Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Safe math functions and constants
SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "pi": math.pi,
    "e": math.e,
}

MAX_RESULT = 1e15  # Prevent absurdly large results


class CalculatorTool:
    """Safe math expression evaluator using AST parsing."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Evaluate math expression"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "calculator",
            "description": "Evaluate math expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression to evaluate",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        expr = arguments.get("expression", "")
        if not expr:
            return ToolResult(
                tool_name="calculator",
                success=False,
                error="No expression provided",
            )
        try:
            result = _safe_eval(expr)
            # Format nicely
            if isinstance(result, float) and result == int(result):
                display = str(int(result))
            elif isinstance(result, float):
                display = f"{result:.6g}"
            else:
                display = str(result)
            return ToolResult(
                tool_name="calculator",
                success=True,
                data=result,
                display_text=f"{expr} equals {display}.",
            )
        except (ValueError, TypeError, ZeroDivisionError) as e:
            return ToolResult(
                tool_name="calculator",
                success=False,
                error=str(e),
            )


def _safe_eval(expr: str) -> float | int:
    """Safely evaluate a math expression using AST parsing.

    Only allows arithmetic operations and safe math functions.
    No variable access, function calls (beyond whitelist), or imports.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        msg = f"Invalid expression: {e}"
        raise ValueError(msg) from e
    return _eval_node(tree.body)


def _eval_node(node: ast.expr) -> float | int:
    """Recursively evaluate an AST node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        msg = f"Unsupported constant type: {type(node.value).__name__}"
        raise ValueError(msg)

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_BIN_OPS:
            msg = f"Unsupported operator: {op_type.__name__}"
            raise ValueError(msg)
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        result: float | int = SAFE_BIN_OPS[op_type](left, right)
        if abs(result) > MAX_RESULT:
            msg = "Result too large"
            raise ValueError(msg)
        return result

    if isinstance(node, ast.UnaryOp):
        uop_type = type(node.op)
        if uop_type not in SAFE_UNARY_OPS:
            msg = f"Unsupported unary operator: {uop_type.__name__}"
            raise ValueError(msg)
        operand = _eval_node(node.operand)
        return float(SAFE_UNARY_OPS[uop_type](operand))

    if isinstance(node, ast.Name):
        name = node.id
        if name in SAFE_FUNCTIONS:
            val = SAFE_FUNCTIONS[name]
            if isinstance(val, (int, float)):
                return val
        msg = f"Unknown variable: {name}"
        raise ValueError(msg)

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            func = SAFE_FUNCTIONS[node.func.id]
            if callable(func):
                args = [_eval_node(arg) for arg in node.args]
                call_result: float | int = func(*args)
                return call_result
        msg = "Function calls not allowed"
        raise ValueError(msg)

    msg = f"Unsupported expression type: {type(node).__name__}"
    raise ValueError(msg)
