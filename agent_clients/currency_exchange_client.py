import os
import sys
import logging

__curdir__ = os.getcwd()
if "agent_protocols" in __curdir__:
    sys.path.append("../utils")
else:
    sys.path.append("./utils")

from setup import setup_paths

setup_paths()

from common.client import A2AClient
from common.client.card_resolver import A2ACardResolver
from common.types import AgentCard # Import AgentCard if needed directly

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_client(url):
    """Returns an A2A client from url deployment.
    
    Note that the A2ACardResolver only takes absolute URL without endpoint (for e.g. http://localhost:8000)
    The A2A client instantiation takes the URL with the endpoint (for e.g. http://localhost:8000/currency)
    """
    try:
        card_resolver = A2ACardResolver(url)
        agent_card: AgentCard = card_resolver.get_agent_card()
        client = A2AClient(agent_card=agent_card)
        return client
    except Exception as e:
        logger.error(f"Failed to fetch AgentCard or initialize client: {e}")
        try:
            client = A2AClient(url=url)
            return client
        except Exception as e:
            logger.error(f"Failed to initialize client. Error: {e}")
            return