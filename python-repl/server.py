import asyncio
import io
import subprocess
import re
from contextlib import redirect_stdout, redirect_stderr
import traceback
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
import pandas as pd
import json
# Add pandas configuration
pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', 1000)

class PythonREPLServer:
    def __init__(self):
        self.server = Server("python-repl")
        self.global_namespace = {
            "__builtins__": __builtins__,
            "pd": pd,
        }
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return await self.handle_list_tools()
            
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            return await self.handle_call_tool(name, arguments)

    async def handle_list_tools(self) -> list[types.Tool]:
        return [
            types.Tool(
                name="execute_python",
                description="Execute Python code and return the output. Variables persist between executions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute",
                        },
                        "reset": {
                            "type": "boolean",
                            "description": "Reset the Python session (clear all variables)",
                            "default": False
                        }
                    },
                    "required": ["code"],
                },
            ),
            types.Tool(
                name="list_variables",
                description="List all variables in the current session",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="install_package",
                description="Install a Python package using uv",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "package": {
                            "type": "string",
                            "description": "Package name to install (e.g., 'pandas')",
                        }
                    },
                    "required": ["package"],
                },
            )
        ]

    async def handle_call_tool(
        self, name: str, arguments: dict | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if not arguments:
            raise ValueError("Missing arguments")
        
        if name == "execute_python":
            code = arguments.get("code")
            if not code:
                raise ValueError("Missing code parameter")

            if arguments.get("reset", False):
                self.global_namespace.clear()
                self.global_namespace["__builtins__"] = __builtins__
                self.global_namespace["pd"] = pd
                return [
                    types.TextContent(
                        type="text",
                        text="Python session reset. All variables cleared."
                    )
                ]

            stdout = io.StringIO()
            stderr = io.StringIO()
            
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exec(code, self.global_namespace)
                
                output = stdout.getvalue()
                errors = stderr.getvalue()
                
                result = {}
                if output:
                    result["output"] = output
                if errors:
                    result["errors"] = errors

                last_line = code.strip().split('\n')[-1]
                last_value = eval(last_line, self.global_namespace)
                
                if isinstance(last_value, pd.DataFrame):
                    df_json = {
                        "type": "dataframe",
                        "data": last_value.to_dict(orient="records"),
                        "columns": last_value.columns.tolist(),
                        "shape": list(last_value.shape)
                    }
                    return [
                        types.TextContent(
                            type="text",
                            text=json.dumps(df_json)
                        )
                    ]
                elif isinstance(last_value, (list, dict)):
                    result["result"] = last_value
                else:
                    result["result"] = repr(last_value)

                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(result)
                    )
                ]
                    
            except Exception as e:
                error_msg = f"Error executing code:\n{traceback.format_exc()}"
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": error_msg})
                    )
                ]

        elif name == "install_package":
            package = arguments.get("package")
            if not package:
                raise ValueError("Missing package name")
                
            try:
                subprocess.run(
                    ["uv", "pip", "install", "pip"],
                    capture_output=True,
                    text=True,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": f"Failed to install pip: {e.stderr}"})
                    )
                ]
            
            if not re.match("^[A-Za-z0-9][A-Za-z0-9._-]*$", package):
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": f"Invalid package name: {package}"})
                    )
                ]
            
            try:
                process = subprocess.run(
                    ["uv", "pip", "install", package],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if process.returncode != 0:
                    return [
                        types.TextContent(
                            type="text",
                            text=json.dumps({"error": f"Failed to install package: {process.stderr}"})
                        )
                    ]
                
                try:
                    exec(f"import {package.split('[')[0]}", self.global_namespace)
                    return [
                        types.TextContent(
                            type="text",
                            text=json.dumps({"success": f"Successfully installed and imported {package}"})
                        )
                    ]
                except ImportError as e:
                    return [
                        types.TextContent(
                            type="text",
                            text=json.dumps({"error": f"Package installed but import failed: {str(e)}"})
                        )
                    ]
                    
            except subprocess.CalledProcessError as e:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": f"Failed to install package:\n{e.stderr}"})
                    )
                ]
                
        elif name == "list_variables":
            vars_dict = {
                k: repr(v) for k, v in self.global_namespace.items() 
                if not k.startswith('_') and k != '__builtins__'
            }
            
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"variables": vars_dict})
                )
            ]
            
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def run(self):
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="python-repl",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

async def main():
    server = PythonREPLServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
