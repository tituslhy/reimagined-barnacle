#%%
import asyncio
import logging
import traceback
from typing import AsyncIterable, Union, Dict, Any

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
from agent import get_agent

setup_paths()

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


# %%
