import httpx
from dotenv import load_dotenv, find_dotenv

from llama_index.core.tools import FunctionTool
from llama_index.llms.openai import OpenAI
from llama_index.core.agent.workflow import FunctionAgent, AgentStream
from llama_index.core.workflow import Context

_ = load_dotenv(find_dotenv())

def get_exchange_rate(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    currency_date: str = "latest",
):
    """Use this to get current exchange rate.

    Args:
        currency_from: The currency to convert from (e.g., "USD").
        currency_to: The currency to convert to (e.g., "EUR").
        currency_date: The date for the exchange rate or "latest". Defaults to "latest".

    Returns:
        A dictionary containing the exchange rate data, or an error message if the request fails.
    """    
    try:
        response = httpx.get(
            f"https://api.frankfurter.app/{currency_date}",
            params={"from": currency_from, "to": currency_to},
        )
        response.raise_for_status()

        data = response.json()
        if "rates" not in data:
            return {"error": "Invalid API response format."}
        return data
    except httpx.HTTPError as e:
        return {"error": f"API request failed: {e}"}
    except ValueError:
        return {"error": "Invalid JSON response from API."}

def get_agent():
    tools = [FunctionTool.from_defaults(get_exchange_rate)]
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