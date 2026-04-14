"""Exceptions used by the shared tool layer."""

class UnsupportedToolError(Exception):
    """Raised when the model requests a tool that is not in the allowlist."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f'Unsupported tool: {tool_name}')


class ToolLoopExhaustedError(Exception):
    """Raised when the assistant exceeds the configured tool-call budget."""

    def __init__(self, max_rounds: int):
        self.max_rounds = max_rounds
        super().__init__(
            f'Assistant exceeded maximum tool rounds ({max_rounds})'
        )
