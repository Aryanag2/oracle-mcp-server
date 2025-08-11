#!/usr/bin/env python3
import asyncio
import json
import os
import httpx
from oci_generative_ai import ChatOCIGenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate

model = ChatOCIGenAI(
    compartment_id=os.getenv("OCI_COMPARTMENT_ID", "ocid1.tenancy.oc1..aaaaaaaahzy3x4boh7ipxyft2rowu2xeglvanlfewudbnueugsieyuojkldq"),
    auth_type=os.getenv("OCI_AUTH_TYPE", "SECURITY_TOKEN"),
    auth_profile=os.getenv("OCI_AUTH_PROFILE", "aryan-chicago"),
    model_id=os.getenv("OCI_MODEL_ID", "openai.gpt-4.1-mini"),
    service_endpoint=os.getenv("OCI_ENDPOINT", "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"),
    model_kwargs={"temperature": 0, "max_tokens": 4096},
)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://oracle-mcp:8000")


class MCPHTTPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.client = None
        self.tools = []
        self.request_id = 0
        
    async def connect(self):
        print(f"🔌 Connecting to MCP server at {self.base_url}")
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # Initialize MCP session
        init_result = await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "oracle-mcp-client", "version": "1.0.0"},
            },
        )
        
        await self.send_notification("notifications/initialized")
        
        # Give the backend a moment to warm up
        await asyncio.sleep(1.0)
        
        # Load tools
        tools_result = await self.list_tools()
        self.tools = tools_result.get("tools", [])
        print(f"✅ Loaded {len(self.tools)} tools")

    async def send_request(self, method, params=None):
        if not self.client:
            raise RuntimeError("HTTP client not connected")
        
        self.request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/mcp",  # Add /mcp to the path
                json=req
            )
            response.raise_for_status()
            resp = response.json()
            
            if "error" in resp:
                raise RuntimeError(f"Server error: {resp['error']}")
            return resp.get("result")
            
        except httpx.TimeoutException:
            raise RuntimeError(f"Timeout waiting for response to method={method}")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"HTTP error: {e.response.status_code}")


    # Update the send_notification method:
    async def send_notification(self, method, params=None):
        if not self.client:
            raise RuntimeError("HTTP client not connected")
        
        note = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        try:
            await self.client.post(
                f"{self.base_url}/mcp",  # Add /mcp to the path
                json=note
            )
        except Exception as e:
            # Notifications are fire-and-forget
            print(f"Warning: notification failed: {e}")
            
    async def list_tools(self):
        return await self.send_request("tools/list")

    async def call_tool(self, name, arguments=None):
        print(f"🔧 Calling tool: {name}")
        try:
            return await self.send_request("tools/call", {
                "name": name,
                "arguments": arguments or {}
            })
        except Exception as e:
            return {"error": str(e)}

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None


class OracleMCPChat:
    """
    Wraps LLM prompting + MCP tool orchestration.
    """
    
    def __init__(self, mcp_client: MCPHTTPClient):
        self.mcp_client = mcp_client
        self.conversation_history = []
        self.system_message = (
            "You are an Oracle database assistant with access to MCP tools for querying "
            "and analyzing Oracle databases.\n\nAvailable tools and their purposes:\n"
            + self._format_tools_description()
        )

    def _format_tools_description(self):
        if not self.mcp_client.tools:
            return "No tools loaded yet."

        parts = []
        for tool in self.mcp_client.tools:
            name = tool.get("name", "Unknown")
            desc = tool.get("description", "No description available")
            schema = tool.get("inputSchema", {})
            params = []
            if isinstance(schema, dict) and "properties" in schema:
                for prop_name, prop_info in schema["properties"].items():
                    ptype = prop_info.get("type", "string")
                    params.append(f"{prop_name} ({ptype})")
            param_str = f" - Parameters: {', '.join(params)}" if params else ""
            parts.append(f"• {name}: {desc}{param_str}")
        return "\n".join(parts)

    async def process_user_input(self, user_input: str) -> str:
        self.conversation_history.append(HumanMessage(content=user_input))

        messages = [SystemMessage(content=self.system_message)]
        messages.extend(self.conversation_history[-10:])  # last N turns

        tool_usage_prompt = f"""
You are an intelligent assistant with access to MCP tools for exploring Oracle databases.

When answering the user's question:
1. Choose the most appropriate tool from: {', '.join([t['name'] for t in self.mcp_client.tools])}
2. If a tool is required, write a line exactly like:
   CALL_TOOL: tool_name with parameters: {{"param1": "value1", "param2": "value2"}}
   - Always use explicit values (no Python variables).
   - For broad queries (like "what tables exist"), you may use: {{"search_term": "%"}}
   - Wrap all strings in quotes.
   - If no parameters are needed, use an empty dict: {{}}
3. After tool output, explain the result in simple terms.
4. Respond in English prose, not code or JSON (except the single CALL_TOOL line).
""".strip()

        messages.append(HumanMessage(content=tool_usage_prompt))

        tmpl = ChatPromptTemplate.from_messages(messages)
        chain = tmpl | model

        try:
            ai_response = chain.invoke({})
            response_content = ai_response.content if hasattr(ai_response, "content") else str(ai_response)

            if "CALL_TOOL:" in response_content:
                response_content = await self._handle_tool_calls(response_content)

            self.conversation_history.append(AIMessage(content=response_content))
            return response_content

        except Exception as e:
            err = f"Error processing request: {e}"
            self.conversation_history.append(AIMessage(content=err))
            return err

    async def _handle_tool_calls(self, response_content: str) -> str:
        lines = response_content.split("\n")
        final_lines = []

        for line in lines:
            if line.strip().startswith("CALL_TOOL:"):
                try:
                    tool_part = line.split("CALL_TOOL:")[1].strip()
                    if " with parameters:" in tool_part:
                        tool_name = tool_part.split(" with parameters:")[0].strip()
                        params_str = tool_part.split(" with parameters:")[1].strip()
                        try:
                            params = json.loads(params_str)
                        except json.JSONDecodeError:
                            params = {}
                    else:
                        tool_name = tool_part.strip()
                        params = {}

                    print(f"🤖 AI requested tool call: {tool_name} with params={params}")
                    tool_result = await self.mcp_client.call_tool(tool_name, params)

                    if isinstance(tool_result, dict) and "error" in tool_result:
                        final_lines.append(f"❌ Tool error: {tool_result['error']}")
                    else:
                        if isinstance(tool_result, dict) and "content" in tool_result:
                            result_text = tool_result["content"]
                        else:
                            result_text = json.dumps(tool_result, ensure_ascii=False, indent=2)
                        final_lines.append(f"📊 {tool_name} result:\n{result_text}")

                except Exception as e:
                    final_lines.append(f"❌ Error calling tool: {e}")
            else:
                final_lines.append(line)

        return "\n".join(final_lines)


async def main():
    print("🚀 Starting Oracle MCP Chat Client (HTTP mode)…")
    mcp_client = MCPHTTPClient(MCP_SERVER_URL)

    try:
        await mcp_client.connect()
        chat = OracleMCPChat(mcp_client)

        print("\n" + "=" * 60)
        print("🎉 Oracle Database Chat Assistant Ready!")
        print("=" * 60)
        print("Available tools:", ", ".join([t["name"] for t in mcp_client.tools]))
        print("\nAsk about your Oracle database. Type 'quit' to exit.")
        print("=" * 60)

        while True:
            try:
                user_input = input("\n💬 You: ").strip()
                if user_input.lower() in {"quit", "exit", "bye", "q"}:
                    print("👋 Goodbye!")
                    break
                if not user_input:
                    continue

                print("🤔 Processing...")
                response = await chat.process_user_input(user_input)
                print(f"\n🤖 Assistant: {response}")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")

    except Exception as e:
        print(f"❌ Client error: {e}")
    finally:
        print("🧹 Cleaning up...")
        await mcp_client.close()


if __name__ == "__main__":
    asyncio.run(main())