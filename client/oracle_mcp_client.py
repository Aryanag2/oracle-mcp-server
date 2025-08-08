#!/usr/bin/env python3

import asyncio
import subprocess
import json
import sys
import os
from oci_generative_ai import ChatOCIGenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate

# Initialize Oracle Gen AI
model = ChatOCIGenAI(
    compartment_id="ocid1.tenancy.oc1..aaaaaaaahzy3x4boh7ipxyft2rowu2xeglvanlfewudbnueugsieyuojkldq",
    auth_type="SECURITY_TOKEN",
    auth_profile="aryan-chicago",
    model_id="openai.gpt-4.1-mini",
    service_endpoint="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
    model_kwargs={"temperature": 0, "max_tokens": 4096},
)

class MCPStdioClient:
    def __init__(self, server_script_path):
        self.server_script_path = server_script_path
        self.process = None
        self.request_id = 0
        self.tools = []
    
    async def start_server(self):
        print(f"🔧 Starting server: {self.server_script_path}")
        
        server_dir = os.path.dirname(self.server_script_path)
        
        self.process = await asyncio.create_subprocess_exec(
            "uv", "run", "main.py",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            text=False,  
            cwd=server_dir  
        )
        
        await asyncio.sleep(3)
        
        if self.process.returncode is not None:
            stderr_output = await self.process.stderr.read()
            raise RuntimeError(f"Server process exited immediately with code {self.process.returncode}. stderr: {stderr_output.decode('utf-8')}")
        
        print("📡 Initializing MCP session...")
        
        # Initialize the MCP session
        init_result = await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {}
            },
            "clientInfo": {
                "name": "oracle-mcp-client",
                "version": "1.0.0"
            }
   eibccdcbh     })
        
        print(f"Initialize result received")
        
        await self.send_notification("notifications/initialized")
        
        print("Waiting for server to complete database initialization...")
        await asyncio.sleep(5)
        
        print("📋 Loading available tools...")
        tools_result = await self.list_tools()
        self.tools = tools_result.get("tools", [])
        print(f"✅ Loaded {len(self.tools)} tools")
    
    async def send_request(self, method, params=None):
        """Send a JSON-RPC request to the server"""
        if not self.process:
            raise RuntimeError("Server not started")
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        request_json = (json.dumps(request) + '\n').encode('utf-8')
        self.process.stdin.write(request_json)
        await self.process.stdin.drain()
        
        try:
            response_line = await asyncio.wait_for(self.process.stdout.readline(), timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError("Timeout waiting for server response")
            
        if not response_line:
            raise RuntimeError("Server closed connection")
        
        try:
            response = json.loads(response_line.decode('utf-8').strip())
            if "error" in response:
                raise RuntimeError(f"Server error: {response['error']}")
            return response.get("result")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON response: {response_line.decode('utf-8')}") from e
    
    async def send_notification(self, method, params=None):
        """Send a JSON-RPC notification (no response expected)"""
        if not self.process:
            raise RuntimeError("Server not started")
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        # Send notification with proper encoding
        notification_json = (json.dumps(notification) + '\n').encode('utf-8')
        self.process.stdin.write(notification_json)
        await self.process.stdin.drain()
    
    async def list_tools(self):
        """List available tools from the server"""
        return await self.send_request("tools/list")
    
    async def call_tool(self, name, arguments=None):
        """Call a specific tool"""
        print(f"🔧 Calling tool: {name}")
        try:
            result = await self.send_request("tools/call", {
                "name": name,
                "arguments": arguments or {}
            })
            return result
        except Exception as e:
            return {"error": str(e)}
    
    async def close(self):
        """Close the connection and terminate the server"""
        if self.process:
            self.process.stdin.close()
            await self.process.wait()
            self.process = None

class OracleMCPChat:
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.conversation_history = []
        
        # System message to help the AI understand how to use the tools
        self.system_message = """You are an Oracle database assistant with access to MCP tools for querying and analyzing Oracle databases. 

Available tools and their purposes:
""" + self._format_tools_description()

    def _format_tools_description(self):
        """Format available tools for the system message"""
        if not self.mcp_client.tools:
            return "No tools loaded yet."
        
        descriptions = []
        for tool in self.mcp_client.tools:
            name = tool.get('name', 'Unknown')
            desc = tool.get('description', 'No description available')
            # Get parameter info
            schema = tool.get('inputSchema', {})
            params = []
            if isinstance(schema, dict) and 'properties' in schema:
                for prop_name, prop_info in schema['properties'].items():
                    param_type = prop_info.get('type', 'string')
                    params.append(f"{prop_name} ({param_type})")
            
            param_str = f" - Parameters: {', '.join(params)}" if params else ""
            descriptions.append(f"• {name}: {desc}{param_str}")
        
        return "\n".join(descriptions)

    async def process_user_input(self, user_input):
        """Process user input and potentially call MCP tools"""
        # Add user message to history
        self.conversation_history.append(HumanMessage(content=user_input))
        
        # Create the prompt with conversation history and tool information
        messages = [SystemMessage(content=self.system_message)]
        messages.extend(self.conversation_history[-10:])  # Keep last 10 messages for context
        
        tool_usage_prompt = f"""
You are an intelligent assistant with access to MCP tools for exploring Oracle databases.

When answering the user's question:
1. Choose the most appropriate tool from: {', '.join([tool['name'] for tool in self.mcp_client.tools])}
2. If a tool is required, write a line like:
   CALL_TOOL: tool_name with parameters: {{"param1": "value1", "param2": "value2"}}
   - Always use explicit values. Do NOT use Python-style variables (like search_term).
   - For broad queries (like “what tables are there”), use: {{"search_term": "%"}}
   - Wrap all strings in quotes.
   - If no parameters are needed, use an empty dict: {{}}
3. Then explain the result to the user in simple terms.
4. Give a final response in english language, not in code or JSON format.
"""


        
        messages.append(HumanMessage(content=tool_usage_prompt))
        
        # Get AI response
        tmpl = ChatPromptTemplate.from_messages(messages)
        chain = tmpl | model
        
        try:
            ai_response = chain.invoke({})
            response_content = ai_response.content
            
            # Check if the AI wants to call a tool
            if "CALL_TOOL:" in response_content:
                response_content = await self._handle_tool_calls(response_content)
            
            # Add AI response to history
            self.conversation_history.append(AIMessage(content=response_content))
            
            return response_content
            
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            self.conversation_history.append(AIMessage(content=error_msg))
            return error_msg

    async def _handle_tool_calls(self, response_content):
        """Handle tool calls from AI response"""
        lines = response_content.split('\n')
        final_response = []
        
        for line in lines:
            if line.strip().startswith("CALL_TOOL:"):
                try:
                    # Parse tool call
                    tool_part = line.split("CALL_TOOL:")[1].strip()
                    if " with parameters:" in tool_part:
                        tool_name = tool_part.split(" with parameters:")[0].strip()
                        params_str = tool_part.split(" with parameters:")[1].strip()
                        # Parse parameters safely as JSON
                        try:
                            params = json.loads(params_str)
                        except json.JSONDecodeError:
                            params = {}
                    else:
                        tool_name = tool_part.strip()
                        params = {}
                    
                    # Call the tool
                    print(f"🤖 AI is calling tool: {tool_name}")
                    tool_result = await self.mcp_client.call_tool(tool_name, params)
                    
                    if isinstance(tool_result, dict) and "error" in tool_result:
                        final_response.append(f"❌ Tool error: {tool_result['error']}")
                    else:
                        # Format the tool result
                        if isinstance(tool_result, dict) and "content" in tool_result:
                            result_text = tool_result["content"]
                        else:
                            result_text = str(tool_result)
                        
                        final_response.append(f"📊 {tool_name} result:\n{result_text}")
                        
                except Exception as e:
                    final_response.append(f"❌ Error calling tool: {str(e)}")
            else:
                final_response.append(line)
        
        return '\n'.join(final_response)

async def main():
    """Main chat loop"""
    server_script = "/Users/aryangosaliya/Desktop/oracle-mcp-server/server/main.py"
    
    # Initialize MCP client
    print("🚀 Starting Oracle MCP Chat Client...")
    mcp_client = MCPStdioClient(server_script)
    
    try:
        await mcp_client.start_server()
        
        # Initialize chat
        chat = OracleMCPChat(mcp_client)
        
        print("\n" + "="*60)
        print("🎉 Oracle Database Chat Assistant Ready!")
        print("="*60)
        print("Available tools:", ", ".join([tool['name'] for tool in mcp_client.tools]))
        print("\nYou can ask questions about your Oracle database.")
        print("Type 'quit', 'exit', or 'bye' to end the conversation.")
        print("="*60)
        
        # Chat loop
        while True:
            try:
                # Get user input
                user_input = input("\n💬 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if not user_input:
                    continue
                
                # Process input and get response
                print("🤔 Processing...")
                response = await chat.process_user_input(user_input)
                
                print(f"\n🤖 Assistant: {response}")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
    
    except Exception as e:
        print(f"❌ Failed to start MCP client: {e}")
    
    finally:
        print("🧹 Cleaning up...")
        await mcp_client.close()

if __name__ == "__main__":
    asyncio.run(main())