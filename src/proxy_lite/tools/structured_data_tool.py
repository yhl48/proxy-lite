from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal
import json
import pandas as pd
from io import StringIO

from proxy_lite.tools.tool_base import Tool, ToolExecutionResponse, attach_param_schema

class TableExtractionParams(BaseModel):
    mark_id: int = Field(..., description="Mark ID of the table element to extract")
    format: Literal["json", "csv", "markdown"] = Field(
        default="json", description="Output format for the extracted table"
    )

class StructuredDataTool(Tool):
    """Extract and process structured data from web pages"""
    
    def __init__(self, session=None):
        super().__init__()
        self.session = session
        print(f"DEBUG: StructuredDataTool initialized with session: {session is not None}")
    
    @attach_param_schema(TableExtractionParams)
    async def extract_table(self, mark_id: int, format: str = "json") -> ToolExecutionResponse:
        """Extract a table from the webpage and convert it to structured format"""
        print(f"DEBUG: extract_table called with mark_id={mark_id}, format={format}")
        # Get the table element using browser capabilities
        table_html = await self.session.current_page.evaluate("""
            (mark_id) => {
                const element = marked_elements_convergence[mark_id];
                if (element && element.tagName.toLowerCase() === 'table') {
                    return element.outerHTML;
                } else {
                    // Try to find a table inside the element
                    const table = element.querySelector('table');
                    return table ? table.outerHTML : null;
                }
            }
        """, mark_id)
        
        if not table_html:
            return ToolExecutionResponse(content="No table found in the selected element")
        
        # Use pandas to parse the HTML table
        df = pd.read_html(StringIO(table_html))[0]
        
        # Convert to requested format
        if format == "json":
            result = df.to_json(orient="records", indent=2)
        elif format == "csv":
            result = df.to_csv(index=False)
        elif format == "markdown":
            result = df.to_markdown(index=False)
        
        return ToolExecutionResponse(content=result) 