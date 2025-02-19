from pydantic import BaseModel, Field

from proxy_lite.tools.tool_base import Tool, attach_param_schema


class ReturnValueParams(BaseModel):
    value: str = Field(description="The value to return to the user.")


class ReturnValueTool(Tool):
    def __init__(self):
        pass

    @attach_param_schema(ReturnValueParams)
    def return_value(self, value: str):
        """Return a value to the user. Use this tool when you have finished the task in order to provide any information the user has requested."""  # noqa: E501
        print(value)
