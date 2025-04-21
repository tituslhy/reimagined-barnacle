"""
Source: 
https://huggingface.co/blog/lynn-mikami/agent2agent

With minor edits
"""
import os
import sys
import asyncio
import logging
from uuid import uuid4

__curdir__ = os.getcwd()
if "agent_protocols" in __curdir__:
    sys.path.append("../utils")
else:
    sys.path.append("./utils")

from setup import setup_paths

setup_paths()

# Assuming common types and client are importable
from common.client import A2AClient
from common.client.card_resolver import A2ACardResolver
from common.types import Message, TextPart, AgentCard # Import AgentCard if needed directly

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ECHO_SERVER_URL = "http://localhost:8001/a2a" # URL from Echo Server's AgentCard

async def main():
    """The A2A client must be deployed first onto a server!"""
    
    # Fetch agent card first
    
    try:
        card_resolver = A2ACardResolver(ECHO_SERVER_URL)
        agent_card: AgentCard = card_resolver.get_agent_card()
        client = A2AClient(agent_card=agent_card)
    except Exception as e:
        logger.error(f"Failed to fetch AgentCard or initialize client: {e}")
        try:
            client = A2AClient(url=ECHO_SERVER_URL)
        except Exception as e:
            logger.error(f"Failed to initialize client. Error: {e}")
            return
    
    task_id = f"echo-task-{uuid4().hex}"
    session_id = f"session-{uuid4().hex}"
    user_text="Testing the echo client!"
    
    user_message = Message(
        role="user",
        parts=[TextPart(text=user_text)]
    )
    
    send_params = {
        "id": task_id,
        "sessionId": session_id,
        "message": user_message
    }
    
    try:
        logger.info(f"Sending task {task_id} to {ECHO_SERVER_URL}...")
        response = await client.send_task(payload=send_params)
        
        if response.error:
            logger.error(f"Task {task_id} failed: {response.error.message} (Code: {response.error.code})")
        elif response.result:
            task_result=response.result
            logger.info(f"Task {task_id} completed with state: {task_result.status.state}")
            if task_result.status.message and task_result.status.message.parts:
                agent_part = task_result.status.message.parts[0]
                if isinstance(agent_part, TextPart):
                    logger.info(f"Agent response: {agent_part.text}")
                else:
                    logger.warning("Agent response was not TextPart")
            else:
                 logger.warning("No message part in agent response status")
        else:
            logger.error(f"Received unexpected response for task {task_id}: {response}")
    
    except Exception as e:
        logger.error(f"An error occurred while communicating with the agent: {e}")

if __name__ == "__main__":
    asyncio.run(main())
                    
            
