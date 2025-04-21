#%%
import asyncio
import logging
import traceback
from typing import AsyncIterable, Union, Dict, Any

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow import Context

import os
import sys

__curdir__ = os.getcwd()
if "src" in __curdir__:
    sys.path.append("../utils")
    sys.path.append("./")
else:
    sys.path.append("./utils")
    sys.path.append("./src")
from setup import setup_paths

setup_paths()

import common.server.utils as utils
from common.types import (
    SendTaskRequest,
    TaskSendParams,
    Message,
    TaskStatus,
    TaskState,
    Artifact,
    TextPart,
    SendTaskResponse,
    JSONRPCResponse,
    SendTaskStreamingRequest,
    InvalidParamsError,
)
from common.server.task_manager import InMemoryTaskManager

logger = logging.getLogger(__name__)
# %%

class CurrencyTaskManager(InMemoryTaskManager):
    """Task manager for the currency agent.
    Handles task routing and response packing."""
    
    SUPPORTED_CONTENT_TYPES = ["text","text/plain"]
    
    def __init__(
        self, 
        agent: FunctionAgent, 
    ):
        super().__init__()
        self.agent = agent
        self.ctx_states: Dict[str, Dict[str, Any]] = dict()
    
    def _validate_request(
        self, request:SendTaskRequest
    ) -> JSONRPCResponse | None:
        """Method to validate request"""
        
        if not utils.are_modalities_compatible(
            request.params.acceptedOutputModes,
            self.SUPPORTED_CONTENT_TYPES,
        ):
            logger.warning(
                "Unsupported output mode. Received %s, Support %s",
                request.params.acceptedOutputModes,
                self.SUPPORTED_CONTENT_TYPES,
            )
            return utils.new_incompatible_types_error(request.id)
        
        return None            
    
    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse :
        """Implementation of on_send_task abstractmethod by parent class
        
        Handles the 'send task' request."""
        
        # Check if modalities are compatbile
        validation_error = self._validate_request(request)
        if validation_error:
            return SendTaskResponse(id=request.id, error=validation_error.error)
   
        task_send_params: TaskSendParams = request.params
        await self.upsert_task(task_send_params)
        
        return await self._run_agent(request)
    
    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskResponse] | JSONRPCResponse:
        error = self._validate_request(request)
        if error:
            return error
        await self.upsert_task(request.params)
    
    async def _run_agent(self, request: SendTaskRequest) -> SendTaskResponse:
        task_send_params: TaskSendParams = request.params 
        part = task_send_params.message.parts[0]     
        session_id = task_send_params.sessionId       
        task_id = task_send_params.id
        
        if not isinstance(part, TextPart):
            raise ValueError("The input must be a text part")
        query = part.text
        
        ### Main invocation logic ###
        try:
            ctx= None
            # Check if we have a saved context state for this session
            print(f"Len of tasks: {len(self.tasks)}", flush=True)
            print(f"Len of ctx_states: {len(self.ctx_states)}", flush=True)            
            saved_ctx_state = self.ctx_states.get(session_id, None)
            
            if saved_ctx_state is not None:
                # Resume with existing context
                logger.info(f"Resuming session {session_id} with saved context")
                ctx = Context.from_dict(self.agent, saved_ctx_state)
                handler = self.agent.run(query, ctx=ctx)
            
            else:
                # Start a new session
                logger.info(f"Starting new session {session_id}")
                handler = self.agent.run(query)
            
            response = await handler
            content = str(response)
            parts = [
                {
                    "type": "text",
                    "text": content
                }
            ]
            # Store conversation context
            self.ctx_states[session_id] = handler.ctx.to_dict()
            
            artifact = Artifact(
                parts=parts,
                index=0,
                append=False
            )
            task_status = TaskStatus(state=TaskState.COMPLETED)
            latest_task = await self.update_store(task_id, task_status, [artifact])
            task_result = self.append_task_history(latest_task, task_send_params.historyLength)
            
            return SendTaskResponse(id=request.id, result = task_result)
            # return SendTaskResponse(id=request.id, result = latest_task)
        
        except Exception as e:
            logger.error(f"An error occurred while invoking the agent: {e}")
            logger.error(traceback.format_exc())
            
            # Clean up context in case of error
            if session_id in self.ctx_states:
                del self.ctx_states[session_id]
            
            # Return error response
            parts = [{"type": "text", "text": f"Error: {str(e)}"}]
            task_status = TaskStatus(state=TaskState.FAILED, message=Message(role="agent", parts=parts))
            task = await self.update_store(task_id, task_status, None)
            task_result = self.append_task_history(task, task_send_params.historyLength)
            return SendTaskResponse(id=request.id, result=task_result)                
# %%
