import os
import sys
import logging

__curdir__ = os.getcwd()
if "src" in __curdir__:
    sys.path.append("../utils")
else:
    sys.path.append("./utils")

from setup import setup_paths

setup_paths()

from common.client import A2AClient
from common.types import Message, TextPart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def ping_client_service(
    client: A2AClient,
    task_id: str,
    session_id: str,
    text: str,
):
    """Function to ping deployed A2A servers"""
    
    user_message = Message(
        role="user",
        parts=[TextPart(text=text)]
    )
    send_params = {
        "id": task_id,
        "sessionId": session_id,
        "message": user_message
    }
    try:
        logger.info(f"Sending task {task_id} to server...")
        response = await client.send_task(payload=send_params)
        if response.error:
            logger.error(f"Task {task_id} failed: {response})")
        elif response.result:
            task_result=response.result
            logger.info(f"Task {task_id} completed with state: {task_result.status.state}")
            return task_result
    except Exception as e:
        logger.error(f"An error occurred while communicating with the agent: {e}")
        raise ValueError(e)