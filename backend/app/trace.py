"""
Request tracing utilities for correlating logs across async operations.

Uses Python's contextvars to pass trace_id through async calls without
threading it through function signatures.
"""

import logging
from contextvars import ContextVar

# Context variable for trace ID (survives across async calls)
trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')


def get_trace_id() -> str:
    """Get the current trace ID from context."""
    return trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """Set the trace ID in context."""
    trace_id_var.set(trace_id)


class TraceIDFormatter(logging.Formatter):
    """Custom formatter that adds trace_id to all log records."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Add trace_id to record if not already present
        if not hasattr(record, 'trace_id'):
            record.trace_id = get_trace_id() or 'NO_TRACE'
        return super().format(record)
