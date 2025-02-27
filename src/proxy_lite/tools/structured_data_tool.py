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
        
        # Get all tables from the page
        table_html = await self.session.current_page.evaluate("""
            (index) => {
                const tables = document.querySelectorAll('table');
                if (tables.length > 0) {
                    // Return the table at the specified index
                    return tables[index]?.outerHTML || null;
                }
                return null;
            }
        """, mark_id)  # Pass mark_id as the index parameter
        
        if not table_html:
            return ToolExecutionResponse(content=f"No table found at index {mark_id}")
        
        print(f"DEBUG: Found table HTML: {table_html[:200]}...")  # Debug first 200 chars
        
        # Use pandas to parse the HTML table
        df = pd.read_html(StringIO(table_html))[0]
        
        # Convert to requested format
        if format == "json":
            result = df.to_json(orient="records", indent=2)
        elif format == "csv":
            result = df.to_csv(index=False)
        elif format == "markdown":
            result = df.to_markdown(index=False)
        
        print(f"DEBUG: Extracted table data: {result[:200]}...")  # Debug first 200 chars
        return ToolExecutionResponse(content=result) 