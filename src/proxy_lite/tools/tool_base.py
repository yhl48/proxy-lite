import inspect
from functools import cached_property, wraps
from typing import Any, Callable, Optional

from pydantic import BaseModel


class Tool:
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    @cached_property
    def schema(self) -> list[dict[str, Any]]:
        schema = []
        for name, method in self.__class__.__dict__.items():
            # If function is not callable and isn't decorated using attach_param_schema
            if not isinstance(method, Callable) or not hasattr(method, "param_model"):
                continue

            docstring = inspect.getdoc(method)
            if not docstring:
                raise ValueError(f"The tool function '{name}' is missing a docstring.")
            # Handle multi-line docstirngs
            description = " ".join(line.strip() for line in docstring.split("\n"))

            tool_json = {
                "name": name,
                "description": description,
                "parameters": method.param_model.model_json_schema(),
            }
            schema.append(tool_json)
        return schema


def attach_param_schema(param_model: type[BaseModel]):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, **kwargs):
            # Throw an error if there's a mismatch between the function parameters and pydantic model's fields.
            validated_params = param_model(**kwargs)
            return func(self, **validated_params.model_dump())

        wrapper.param_model = param_model
        return wrapper

    return decorator


class ToolExecutionResponse(BaseModel):
    content: Optional[str] = None
    id: Optional[str] = None
