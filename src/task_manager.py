#%%
import asyncio
import logging
import traceback
from typing import AsyncIterable, Union, Dict, Any

from llama_index.core.agent.workflow import FunctionAgent, AgentOutput
from llama_index.core.workflow import Context, StartEvent

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
    FilePart,
    SendTaskResponse,
    InternalError,
    JSONRPCResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    Task,
    TaskIdParams,
    PushNotificationConfig,
    InvalidParamsError,
)
from common.server.task_manager import InMemoryTaskManager
from common.utils.push_notification_auth import PushNotificationSenderAuth

logger = logging.getLogger(__name__)
# %%

class CurrencyTaskManager(InMemoryTaskManager):
    """Task manager for the currency agent.
    Handles task routing and response packing."""
    
    SUPPORTED_OUTPUT_TYPES = ["text","text/plain"]
    
    def __init__(
        self, 
        agent: FunctionAgent, 
        notification_sender_auth: PushNotificationSenderAuth
    ):
        super().__init__()
        self.agent = agent
        self.notification_sender_auth = notification_sender_auth
        self.ctx_states: Dict[str, Dict[str, Any]] = dict()
    
    async def send_task_notification(self, task: Task):
        if not await self.has_push_notification_info(task.id):
            logger.info(f"No push notification info found for task {task.id}")
            return
        push_info = await self.get_push_notification_info(task.id)
        
        logger.info(f"Notifying for task {task.id}=> {task.status.create}")
        await self.notification_sender_auth.send_push_notification(
            push_info.url,
            data=task.model_dump(exclude_none=True)
        )
    
    async def set_push_notification_info(
        self, 
        task_id: str,
        push_notification_config: PushNotificationConfig
    ):
        """Handler to authenticate push notification destinations
        Overrides the parent class' method with the same name."""
        
        is_verified = await self.notification.sender_auth.verify_push_notification_url(
            push_notification_config.url
        )
        if not is_verified:
            return False
        await super().set_push_notification_info(task_id, push_notification_config)
        return True
    
    def _validate_request(
        self, request: Union[SendTaskRequest, SendTaskStreamingRequest]
    ) -> JSONRPCResponse | None:
        """Method to validate request"""
        
        task_send_params: TaskSendParams = request.params
        if not utils.are_modalities_compatible(
            request.params.acceptedOutputModes,
            self.SUPPORTED_OUTPUT_TYPES,
        ):
            logger.warning(
                "Unsupported output mode. Received %s, Support %s",
                request.params.acceptedOutputModes,
                self.SUPPORTED_CONTENT_TYPES,
            )
            return utils.new_incompatible_types_error(request.id)
        
        if task_send_params.pushNotification and not task_send_params.pushNotification.url:
            logger.warning("Push notification URL is missing")
            return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is missing"))
        
        return None            
    
    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse :
        """Implementation of on_send_task abstractmethod by parent class
        
        Handles the 'send task' request."""
        
        # Check if modalities are compatbile
        validation_error = self._validate_request(request)
        if validation_error:
            return SendTaskResponse(id=request.id, error=validation_error.error)
        if request.params.pushNotification:
            if not await self.set_push_notification_info(request.params.id, request.params.pushNotification):
                return SendTaskResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is invalid."))
            
        task_send_params: TaskSendParams = request.params
        await self.upsert_task(task_send_params)
        
        # Check if this is a continuation of an existing task that needs input
        task_id = request.params.id
        session_id = request.params.sessionId
        task_exists = await self.get_task(task_id) is not None
        
        if not task_exists or session_id not in self.ctx_states:
            # This is a new task. Mark as working
            task = await self.update_store(
                task_id,
                TaskStatus(state=TaskState.WORKING), None
            )
        else:
            # Existing task with saved context - continue from INPUT_REQUIRED state
            logger.info(f"Continuing task {task_id} with user input")
            task = await self.get_task(task_id)
        
        await self.send_task_notification(task)
        
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
            task_status = TaskStatus(TaskState.COMPLETED)
            latest_task = await self.update_store(task_id, task_status, [artifact])
            task_result = self.append_task_history(latest_task, task_send_params.historyLength)
            await self.send_task_notification(latest_task)
            
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
            await self.send_task_notification(task)
            return SendTaskResponse(id=request.id, result=task_result)                
            
            
        

# class CurrencyTaskManager(InMemoryTaskManager):
#     """Handles task routing and response packing"""
    
#     # Limit the supported output types for convenience
#     SUPPORTED_OUTPUT_TYPES = ["text","text/plain"]
    
#     def __init__(
#         self, 
#         agent: FunctionAgent, 
#         notification_sender_auth: PushNotificationSenderAuth
#     ):
#         super().__init__()
#         self.agent = agent
#         self.notification_sender_auth = notification_sender_auth
#         self.ctx_states: Dict[str, Dict[str, Any]] = dict()
    
#     def _get_input_event(self, task_send_params: TaskSendParams) -> StartEvent:
#         """Method to format request pings to a workflow start event"""
#         text_parts = []
#         for part in task_send_params.message_parts:
#             if isinstance(part, TextPart):
#                 text_parts.append(part.text)
#             else:
#                 raise ValueError(f"Unsupported part type: {type(part)}")
#         return StartEvent(
#             query = "\n".join(text_parts)
#         )
    
#     async def _run_agent(self, request: SendTaskStreamingRequest):
#         """Main function that invokes the agent"""
        
#         task_send_params: TaskSendParams = request.params
#         task_id = task_send_params.id
#         session_id = task_send_params.sessionId
#         start_event = self._get_input_event(task_send_params)
        
#         try:
#             ctx, handler = None, None
            
#             # Check if we have a saved context state for this session
#             print(f"Len of tasks: {len(self.tasks)}", flush=True)
#             print(f"Len of ctx_states: {len(self.ctx_states)}", flush=True)
#             saved_ctx_state = self.ctx_states.get(session_id, None)
            
#             if saved_ctx_state is not None:
#                 # Resume with existing context
#                 logger.info(f"Resuming session {session_id} with saved context")
#                 ctx = Context.from_dict(self.agent, saved_ctx_state)
#                 handler = self.agent.run(start_event = start_event, ctx=ctx)
            
#             else:
#                 # Start a new session
#                 logger.info(f"Starting new session {session_id}")
#                 handler = self.agent.run(start_event=start_event)
            
#             # Stream events as they come - for debugging
#             # async for event in handler.stream_events():
#             #     if isinstance(event, AgentStream):
#             #         print(event.delta, end="", flush=True)
            
#             final_response = await handler
            
#             ##### Postprocess final response #####
#             content = str(final_response)
#             parts = [
#                 {
#                     "type": "text",
#                     "text": content
#                 }
#             ]
#             self.ctx_states[session_id] = handler.ctx.to_dict()
#             artifact = Artifact(
#                 parts=parts,
#                 index=0,
#                 append=False,
#             )
#             task_status = TaskStatus(state=TaskState.COMPELTED)
#             latest_task = await self.update_store(task_id, task_status, [artifact])
#             await self.send_task_notification(latest_task)
            
#             # Send artifact updates
#             task_artifact_update_event = TaskArtifactUpdateEvent(
#                 id = task_id, artifact = artifact
#             )
#             await self.enqueue_events_for_sse(task_id, task_artifact_update_event)
            
#             task_update_event = TaskStatusUpdateEvent(
#                 id = task_id, status = task_status, final=True
#             )
#             await self.enqueue_events_for_sse(task_id, task_update_event)
            
#         except Exception as e:
#             logger.error(traceback.format_exc())
            
#             # Report error to client
#             await self.enqueue_events_for_sse(
#                 task_id,
#                 InternalError(message=f"An error occurred: {e}")
#             )
            
#             # Clean up context in case of error
#             if session_id in self.ctx_states:
#                 del self.ctx_states[session_id]
    
#     def _validate_request(
#         self, request: Union[SendTaskRequest, SendTaskStreamingRequest],
#     ) -> JSONRPCResponse | None:
#         """Method to validate incoming request"""
        
#         task_send_params: TaskSendParams = request.params
        
#         if not utils.are_modalities_compatible(
#             task_send_params.acceptedOutputModes,
#             self.SUPPORTED_OUTPUT_TYPES,
#         ):
#             logger.warning(
#                 "Unsupported output mode. Received %s, Support %s",
#                 task_send_params.acceptedOutputModes,
#                 self.SUPPORTED_OUTPUT_TYPES,
#             )
#             return utils.new_incompatible_types_error(request.id)

#         if task_send_params.pushNotification and not task_send_params.pushNotification.url:
#             logger.warning("Push notification URL is missing")
#             return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is missing"))
        
#         return None         
    
#     async def on_send_task(
#         self, request: SendTaskRequest
#     ) -> SendTaskResponse:
#         """Implementation of on_send_task abstract method from parent class
        
#         Handles the 'send task' request.
#         """
        
#         validation_error = self._validate_request(request)
        
#         if validation_error:
#             return SendTaskResponse(
#                 id = request.id,
#                 error = validation_error.error
#             )
#         if request.params.pushNotification:
#             if not await self.set_push_notification_info(request.params.id, request.params.pushNotification):
#                 return SendTaskResponse(
#                     id = request.id,
#                     error=InvalidParamsError(message="Push notification URL is invalid.")
#                 )
        
#         await self.upsert_task(request.params)
        
#         # Check if this is a continuation of an existing task
#         task_id = request.params.id
#         session_id = request.params.sessionId
#         task_exists = await self.get_task(task_id) is not None
        
#         if not task_exists or session_id not in self.ctx_states:
#             # New task or no saved context - mark as working
#             task = await self.update_store(
#                 task_id, TaskStatus(state=TaskState.WORKING), None
#             )
#         else:
#             logger.info(f"Continuing task {task_id} with user input")
#             task = await self.get_task(task_id)
        
#         await self.send_task_notification(task)
        
#         task_send_params: TaskSendParams = request.params
#         input_event = self._get_input_event(task_send_params)
        
#         # try:
#         #     # Check if we have a saved context for this session
#         #     c