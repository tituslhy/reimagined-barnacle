import chainlit as cl
import os
from dotenv import load_dotenv, find_dotenv
from collections import defaultdict

from llama_index.core.agent.workflow import FunctionAgent, AgentStream, ToolCall
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.chat_engine import SimpleChatEngine
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.workflow import Context
from llama_index.llms.openai import OpenAI
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

import logging

logger = logging.getLogger(__name__)

_ = load_dotenv(find_dotenv())

llm = OpenAI("gpt-4o-mini", temperature=0)

@cl.on_chat_start
async def start():
    """Handler for chat start events. Sets session variables."""
    cl.user_session.set("mcp_tools", {})
    cl.user_session.set("mcp_tool_cache", defaultdict(list))
    cl.user_session.set("context", None)
    cl.user_session.set(
        "agent",
        SimpleChatEngine.from_defaults(
            llm=llm,
        )
    )
    memory = ChatMemoryBuffer.from_defaults()
    memory.put(
        ChatMessage(
            role=MessageRole.SYSTEM, 
            content="You are a helpful AI assistant. You can access tools using MCP servers if available."
        )
    )
    cl.user_session.set("memory",memory,)

@cl.on_message
async def on_message(message: cl.Message):
    agent = cl.user_session.get("agent")
    memory = cl.user_session.get("memory")
    chat_history = memory.get()
    msg = cl.Message("")
    
    if isinstance(agent, SimpleChatEngine):
        response = agent.stream_chat(message.content, chat_history=chat_history)
        for token in response.response_gen:
            await msg.stream_token(token)

    else: #FunctionAgent
        context = cl.user_session.get("context")
        handler = agent.run(
            message.content, 
            chat_history = chat_history,
            ctx = context
        )
        async for event in handler.stream_events():
            if isinstance(event, AgentStream):
                await msg.stream_token(event.delta)
            elif isinstance(event, ToolCall):
                with cl.Step(name=f"{event.tool_name} tool", type="tool"):
                    continue
        
        response = await handler
    
    memory.put(
        ChatMessage(
            role = MessageRole.USER,
            content= message.content
        )
    )
    memory.put(
        ChatMessage(
            role = MessageRole.ASSISTANT,
            content = str(response)
        )
    )
    cl.user_session.set("memory", memory)
    
    await msg.send()

@cl.on_mcp_connect
async def on_mcp_connect(connection):
    """Handler to connect to an MCP server. 
    Lists tools available on the server and connects these tools to
    the LLM agent."""
    mcp_cache = cl.user_session.get("mcp_tool_cache", {})
    mcp_tools = cl.user_session.get("mcp_tools", {})
    try:
        logger.info("Connecting to MCP")
        mcp_client = BasicMCPClient(connection.url)
        logger.info("Connected to MCP")
        mcp_tool_spec = McpToolSpec(client=mcp_client)
        logger.info("Unpacking tools")
        new_tools = await mcp_tool_spec.to_tool_list_async()
        for tool in new_tools:
            if tool.metadata.name not in mcp_tools:
                mcp_tools[tool.metadata.name] = tool
                mcp_cache[connection.name].append(tool.metadata.name)
        agent = FunctionAgent(
            tools=list(mcp_tools.values()),
            llm=llm,
        )
        cl.user_session.set("agent", agent)
        cl.user_session.set("context", Context(agent))
        cl.user_session.set("mcp_tools", mcp_tools)
        cl.user_session.set("mcp_tool_cache", mcp_cache)
        await cl.Message(f"Connected to MCP server: {connection.name} on {connection.url}").send()

        await cl.Message(
            f"Found {len(new_tools)} tools from {connection.name} MCP server."
        ).send()
    except Exception as e:
        await cl.Message(f"Error conecting to tools from MCP server: {str(e)}").send()

@cl.on_mcp_disconnect
async def on_mcp_disconnect(name: str):
    """Handler to handle disconnects from an MCP server.
    Updates tool list available for the LLM agent.
    """
    mcp_tools = cl.user_session.get("mcp_tools", {})
    mcp_cache = cl.user_session.get("mcp_tool_cache", {})
    
    if name in mcp_cache:
        for tool_name in mcp_cache[name]:
            del mcp_tools[tool_name]
        del mcp_cache[name]

    # Update tools list in agent
    if len(mcp_tools)>0:
        agent = FunctionAgent(
            tools=list(mcp_tools.values()), #agent still has tools not removed
            llm=llm,
        )
        cl.user_session.set("context", Context(agent))
    else:
        agent = SimpleChatEngine.from_defaults(
            llm=llm,
        )
        cl.user_session.set("context", None)
    cl.user_session.set("mcp_tools", mcp_tools)
    cl.user_session.set("mcp_tool_cache", mcp_cache)
    cl.user_session.set("agent", agent)
    
    await cl.Message(f"Disconnected from MCP server: {name}").send()
    