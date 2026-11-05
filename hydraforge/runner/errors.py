"""Exception types for execution runners and sandboxes."""

class RunnerError(Exception):
    """Base exception for submission runner errors."""
    pass


class UnsafeExecutionEnvironmentError(RunnerError):
    """Raised when host environment does not satisfy mandatory isolation requirements (e.g. Docker offline)."""
    pass


class ExecutionTimeoutError(RunnerError):
    """Raised when a submission process exceeds wall-clock execution limits."""
    pass


class ResourceLimitExceededError(RunnerError):
    """Raised when a submission process exceeds memory, file, or thread limits."""
    pass


class RunnerExecutionError(RunnerError):
    """Raised when a submission exits with non-zero status or fails to execute."""
    pass

