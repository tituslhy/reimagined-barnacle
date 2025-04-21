"""
Source: 
https://huggingface.co/blog/lynn-mikami/agent2agent
"""
#%%
import os
import sys

import uvicorn
import asyncio
import logging
from uuid import uuid4
from typing import Dict

__curdir__ = os.getcwd()
if "agent_protocols" in __curdir__:
    sys.path.append("../utils")
else:
    sys.path.append("./utils")

from setup import setup_paths

setup_paths()

from common.types import (
    AgentCard, AgentCapabilities, AgentSkill, Task, TaskState, TaskStatus,
    Message, TextPart, SendTaskRequest, SendTaskResponse,
    JSONRPCResponse, JSONRPCError, InternalError
)
from common.server import A2AServer, TaskManager

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Agent Definition ---
ECHO_AGENT_CARD = AgentCard(
    name="Echo Agent",
    description="A simple A2A agent that echoes back user messages.",
    url="http://localhost:8001/a2a", # Where this server will run
    version="0.1.0",
    capabilities=AgentCapabilities(
        streaming=False, # This simple agent won't stream
        pushNotifications=False,
        stateTransitionHistory=False
    ),
    authentication=None, # No auth for this simple example
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    skills=[
        AgentSkill(
            id="echo",
            name="Echo Message",
            description="Receives a text message and sends it back.",
            inputModes=["text"],
            outputModes=["text"],
            examples=["'Hello there!' -> 'Hello there!'"]
        )
    ]
)

# --- Task Management Logic ---
class EchoTaskManager(TaskManager):
    def __init__(self):
        # Simple in-memory store for tasks
        self.tasks: Dict[str, Task] = {}
        self.lock = asyncio.Lock()

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        task_params = request.params
        task_id = task_params.id
        user_message = task_params.message

        logger.info(f"Received task {task_id} with message: {user_message.parts}")

        # Basic validation: Expecting a single TextPart
        if not user_message.parts or not isinstance(user_message.parts[0], TextPart):
            logger.error(f"Task {task_id}: Invalid input - expected TextPart.")
            error = JSONRPCError(code=-32602, message="Invalid input: Expected a single TextPart.")
            return SendTaskResponse(id=request.id, error=error)

        user_text = user_message.parts[0].text

        # Create the agent's response message
        agent_response_message = Message(
            role="agent",
            parts=[TextPart(text=f"You said: {user_text}")]
        )

        # Create the final Task object
        final_task_status = TaskStatus(
            state=TaskState.COMPLETED,
            message=agent_response_message # Include final message in status
        )
        completed_task = Task(
            id=task_id,
            sessionId=task_params.sessionId,
            status=final_task_status,
            artifacts=[], # No artifacts for echo
            history=[user_message, agent_response_message] # Simple history
        )

        # Store the completed task (optional for this simple case)
        async with self.lock:
            self.tasks[task_id] = completed_task

        logger.info(f"Task {task_id} completed.")
        # Return the completed task in the response
        return SendTaskResponse(id=request.id, result=completed_task)

    # --- Implement other required abstract methods (can raise NotImplemented) ---
    async def on_get_task(self, request):
        # Basic implementation for demonstration
        async with self.lock:
            task = self.tasks.get(request.params.id)
        if task:
            return JSONRPCResponse(id=request.id, result=task)
        else:
            error = JSONRPCError(code=-32001, message="Task not found")
            return JSONRPCResponse(id=request.id, error=error)

    async def on_cancel_task(self, request):
        error = JSONRPCError(code=-32004, message="Cancel not supported")
        return JSONRPCResponse(id=request.id, error=error)

    async def on_send_task_subscribe(self, request):
         error = JSONRPCError(code=-32004, message="Streaming not supported")
         return JSONRPCResponse(id=request.id, error=error)

    async def on_set_task_push_notification(self, request):
        error = JSONRPCError(code=-32003, message="Push notifications not supported")
        return JSONRPCResponse(id=request.id, error=error)

    async def on_get_task_push_notification(self, request):
        error = JSONRPCError(code=-32003, message="Push notifications not supported")
        return JSONRPCResponse(id=request.id, error=error)

    async def on_resubscribe_to_task(self, request):
         error = JSONRPCError(code=-32004, message="Resubscribe not supported")
         return JSONRPCResponse(id=request.id, error=error)


# --- Server Setup ---
if __name__ == "__main__":
    task_manager = EchoTaskManager()
    server = A2AServer(
        host="localhost",
        port=8001,
        endpoint="/a2a", # Matches AgentCard URL path
        agent_card=ECHO_AGENT_CARD,
        task_manager=task_manager
    )
    print("Starting Echo A2A Server on http://localhost:8001")
    
    uvicorn.run(server.app, host="localhost", port=8001)