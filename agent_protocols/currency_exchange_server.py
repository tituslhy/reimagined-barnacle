import os
import sys

import uvicorn
import asyncio
import logging

from typing import Dict

__curdir__ = os.getcwd()
if "agent_protocols" in __curdir__:
    sys.path.append("../utils")
    sys.path.append("../src")
else:
    sys.path.append("./utils")
    sys.path.append("./src")

from setup import setup_paths
from task_manager import CurrencyTaskManager
from agent import get_agent

setup_paths()

from common.server import A2AServer
from common.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
host = "localhost"
port = 8001
endpoint="/currency"

async def create_currency_agent_server(mcp_client_url: str = "http://localhost:3000/sse"):
    agent = await get_agent(mcp_client_url = mcp_client_url)
    capabilities = AgentCapabilities(streaming=False)
    skill = AgentSkill(
        id="currency_conversion_agent",
        name="Currency conversion agent",
        description="Returns the exchange rate for the currencies of interest",
        tags=["currency_exchange"],
        examples=["What is the exchange rate from SGD to EUR"]
    )
    agent_card = AgentCard(
        name="Currency conversion agent",
        description="Returns the exchange rate for the currencies of interest",
        url=f"http://{host}:{port}{endpoint}",
        version="1.0.0",
        defaultInputModes=CurrencyTaskManager.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=CurrencyTaskManager.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[skill]
    )

    server = A2AServer(
        agent_card=agent_card,
        task_manager=CurrencyTaskManager(agent=agent),
        host=host,
        port=port,
        endpoint=endpoint
    )
    return server

if __name__ == "__main__":
    import asyncio
    
    mcp_client_url= "http://localhost:3000/sse"
    print(f"🚀 Starting currency agent server on http://{host}:{port}{endpoint}")
    server = asyncio.run(create_currency_agent_server(mcp_client_url))
    server.start()
    # uvicorn.run(server.app, host=host, port=port)