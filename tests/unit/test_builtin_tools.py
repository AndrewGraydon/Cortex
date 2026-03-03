"""Tests for built-in tools — clock, calculator, system_info, timer, memory."""

from __future__ import annotations

import pytest

from cortex.agent.tools.builtin.calculator import CalculatorTool
from cortex.agent.tools.builtin.clock import ClockTool
from cortex.agent.tools.builtin.memory_tool import MemoryQueryTool, MemorySaveTool
from cortex.agent.tools.builtin.system_info import SystemInfoTool
from cortex.agent.tools.builtin.timer import (
    TimerCancelTool,
    TimerQueryTool,
    TimerSetTool,
    TimerStore,
    set_timer_store,
)


class TestClockTool:
    async def test_get_time(self) -> None:
        tool = ClockTool()
        result = await tool.execute({"format": "time"})
        assert result.success
        assert ":" in result.display_text  # e.g. "It's 2:30 PM."

    async def test_get_date(self) -> None:
        tool = ClockTool()
        result = await tool.execute({"format": "date"})
        assert result.success
        assert result.display_text.startswith("It's")

    async def test_get_both(self) -> None:
        tool = ClockTool()
        result = await tool.execute({})
        assert result.success
        assert "on" in result.display_text  # "It's X:XX PM on Monday..."

    async def test_schema(self) -> None:
        tool = ClockTool()
        schema = tool.get_schema()
        assert schema["name"] == "clock"
        assert "format" in schema["parameters"]["properties"]

    async def test_tier_safe(self) -> None:
        tool = ClockTool()
        assert tool.permission_tier == 0

    async def test_custom_timezone(self) -> None:
        tool = ClockTool(timezone="America/Vancouver")
        result = await tool.execute({})
        assert result.success


class TestCalculatorTool:
    async def test_addition(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 + 3"})
        assert result.success
        assert result.data == 5

    async def test_multiplication(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "42 * 17"})
        assert result.success
        assert result.data == 714

    async def test_division(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "100 / 3"})
        assert result.success
        assert abs(result.data - 33.333333) < 0.001

    async def test_complex_expression(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "(2 + 3) * 4 - 1"})
        assert result.success
        assert result.data == 19

    async def test_power(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 ** 10"})
        assert result.success
        assert result.data == 1024

    async def test_sqrt(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "sqrt(144)"})
        assert result.success
        assert result.data == 12.0

    async def test_pi(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "pi * 2"})
        assert result.success
        assert abs(result.data - 6.283185) < 0.001

    async def test_division_by_zero(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "1 / 0"})
        assert not result.success

    async def test_invalid_expression(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "not math"})
        assert not result.success

    async def test_empty_expression(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({})
        assert not result.success

    async def test_display_text_format(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 + 2"})
        assert "equals 4" in result.display_text

    async def test_no_code_execution(self) -> None:
        tool = CalculatorTool()
        result = await tool.execute({"expression": "__import__('os')"})
        assert not result.success


class TestSystemInfoTool:
    async def test_basic_info(self) -> None:
        tool = SystemInfoTool()
        result = await tool.execute({})
        assert result.success
        assert "uptime_seconds" in result.data
        assert "Uptime" in result.display_text

    async def test_schema(self) -> None:
        tool = SystemInfoTool()
        schema = tool.get_schema()
        assert schema["name"] == "system_info"


class TestTimerTools:
    @pytest.fixture(autouse=True)
    def fresh_store(self) -> None:
        set_timer_store(TimerStore())

    async def test_set_timer(self) -> None:
        tool = TimerSetTool()
        result = await tool.execute({"duration": 300, "label": "tea"})
        assert result.success
        assert "timer_id" in result.data
        assert "5 minute" in result.display_text

    async def test_set_timer_seconds(self) -> None:
        tool = TimerSetTool()
        result = await tool.execute({"duration": 30})
        assert result.success
        assert "30 second" in result.display_text

    async def test_set_timer_hours(self) -> None:
        tool = TimerSetTool()
        result = await tool.execute({"duration": 7200})
        assert result.success
        assert "2 hour" in result.display_text

    async def test_set_timer_invalid_duration(self) -> None:
        tool = TimerSetTool()
        result = await tool.execute({"duration": -5})
        assert not result.success

    async def test_set_timer_no_duration(self) -> None:
        tool = TimerSetTool()
        result = await tool.execute({})
        assert not result.success

    async def test_query_no_timers(self) -> None:
        tool = TimerQueryTool()
        result = await tool.execute({})
        assert result.success
        assert "No active timers" in result.display_text

    async def test_query_with_timers(self) -> None:
        set_tool = TimerSetTool()
        await set_tool.execute({"duration": 300, "label": "tea"})
        query_tool = TimerQueryTool()
        result = await query_tool.execute({})
        assert result.success
        assert "tea" in result.display_text

    async def test_cancel_timer(self) -> None:
        set_tool = TimerSetTool()
        await set_tool.execute({"duration": 300, "label": "tea"})
        cancel_tool = TimerCancelTool()
        result = await cancel_tool.execute({"label": "tea"})
        assert result.success
        assert "cancelled" in result.display_text

    async def test_cancel_nonexistent(self) -> None:
        cancel_tool = TimerCancelTool()
        result = await cancel_tool.execute({"label": "nope"})
        assert not result.success

    async def test_timer_set_tier(self) -> None:
        assert TimerSetTool().permission_tier == 1

    async def test_timer_query_tier(self) -> None:
        assert TimerQueryTool().permission_tier == 0


class TestMemoryTools:
    async def test_memory_query_stub(self) -> None:
        tool = MemoryQueryTool()
        result = await tool.execute({"query": "user name"})
        assert result.success
        assert result.data == []

    async def test_memory_query_no_query(self) -> None:
        tool = MemoryQueryTool()
        result = await tool.execute({})
        assert not result.success

    async def test_memory_save_stub(self) -> None:
        tool = MemorySaveTool()
        result = await tool.execute({"fact": "User likes tea"})
        assert result.success
        assert "remember" in result.display_text.lower()

    async def test_memory_save_no_fact(self) -> None:
        tool = MemorySaveTool()
        result = await tool.execute({})
        assert not result.success
