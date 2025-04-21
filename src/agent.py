from dotenv import load_dotenv, find_dotenv

from llama_index.llms.openai import OpenAI
from llama_index.core.agent.workflow import FunctionAgent, AgentStream
from llama_index.core.workflow import Context
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

_ = load_dotenv(find_dotenv())

async def get_agent(mcp_client_url: str = "http://localhost:3000/sse"):
    """Handler to create agents from MCP deployments"""
    
    mcp_client = BasicMCPClient(mcp_client_url)
    mcp_tool = McpToolSpec(client=mcp_client)
    tools = await mcp_tool.to_tool_list_async()
    agent = FunctionAgent(
        tools = tools,
        llm=OpenAI(model="gpt-4o-mini"),
    )
    return agent

async def main():
    """Test script for agent."""
    agent = get_agent()
    ctx = Context(agent)
    handler = agent.run("What is the exchange rate from SGD to USD?", ctx=ctx)
    async for event in handler.stream_events():
        if isinstance(event, AgentStream):
            print(event.delta, end="", flush=True)
    response = await handler
    return str(response)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())