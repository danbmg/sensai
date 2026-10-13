from datetime import datetime


def calculator(a: float, b: float, operation: str):
    if operation == "add":
        return a + b

    if operation == "subtract":
        return a - b

    if operation == "multiply":
        return a * b

    if operation == "divide":
        if b == 0:
            raise ValueError("Division by zero is impossible.")

        return a / b

    raise ValueError(
        "Unknown operation. "
        "Use add, subtract, multiply or divide."
    )


def get_current_time():
    now = datetime.now()

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
    }


def register_basic_tools(registry):
    registry.register(
        name="calculator",
        description=(
            "Perform an arithmetic calculation. "
            "Use this tool when the user asks for a calculation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "First number",
                },
                "b": {
                    "type": "number",
                    "description": "Second number",
                },
                "operation": {
                    "type": "string",
                    "description": "Operation to perform",
                    "enum": [
                        "add",
                        "subtract",
                        "multiply",
                        "divide",
                    ],
                },
            },
            "required": [
                "a",
                "b",
                "operation",
            ],
        },
        function=calculator,
    )

    registry.register(
        name="get_current_time",
        description=(
            "Return the current local date and time. "
            "Use this tool when the user asks for "
            "the current date or time."
        ),
        parameters={
            "type": "object",
            "properties": {},
        },
        function=get_current_time,
    )