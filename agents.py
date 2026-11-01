# First step - loading all the libraries

from dotenv import load_dotenv
load_dotenv()

import os
import requests

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage

from tavily import TavilyClient
from rich import print


# Now let's create some tools

# Weather tool

API_KEY = os.getenv("OPENWEATHER_API_KEY")


@tool
def get_weather(city: str) -> str:
    """Get current weather of a city."""

    API_KEY = os.getenv("OPENWEATHER_API_KEY")

    url = "https://api.openweathermap.org/data/2.5/weather"

    response = requests.get(
        url,
        params={
            "q": f"{city},IN",
            "appid": API_KEY,
            "units": "metric"
        },
        timeout=10
    )

    data = response.json()

    if str(data.get("cod")) != "200":
        return f"Error: {data.get('message', 'Could not fetch weather')}"

    temp = data["main"]["temp"]
    desc = data["weather"][0]["description"]

    return f"Weather in {city}: {desc}, {temp}°C"


# Tavily news tool

tavily_client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


@tool
def get_news(city: str) -> str:
    """Get the latest news about a city."""

    response = tavily_client.search(
        query=f"Latest local news, events, and developments in {city}, India",
        search_depth="basic",
        max_results=3
    )

    results = response.get("results", [])

    if not results:
        return f"No news found for {city}"

    news_list = []

    for r in results:
        title = r.get("title", "No title")
        url = r.get("url", "")
        snippet = r.get("content", "")

        news_list.append(
            f"- {title}\n  {url}\n  {snippet[:100]}..."
        )

    return f"Latest news in {city}:\n\n" + "\n\n".join(news_list)


# Test the news tool

print(get_news.invoke({"city": "Srinagar"}))


# LLM

llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash"
)

tools = {
    "get_weather": get_weather,
    "get_news": get_news
}

llm_with_tool = llm.bind_tools([get_weather, get_news])


# Agent loop - very important

messages = []

print("City intelligence system")
print("Type Exit to quit")


while True:
    user_input = input("You: ")

    if user_input.lower() == "exit":
        break

    messages.append(HumanMessage(content=user_input))

    while True:

        # Invoke Gemini
        try:
            result = llm_with_tool.invoke(messages)

        except Exception as e:
            print(f"Gemini API error: {e}")
            break

        messages.append(result)

        # If a tool is required
        if result.tool_calls:

            denied = False

            for tool_call in result.tool_calls:

                tool_name = tool_call["name"]

                # Human in the loop
                confirm = input(
                    f"Agent wants to call {tool_name}. Approve (yes/no): "
                )

                if confirm.lower() != "yes":

                    print("Tool call denied.")

                    # Remove the assistant message containing
                    # the pending tool calls
                    messages.pop()

                    messages.append(
                        HumanMessage(
                            content=(
                                f"The call to {tool_name} was denied. "
                                "Answer without using that tool."
                            )
                        )
                    )

                    denied = True
                    break

                # Execute the tool
                tool_result = tools[tool_name].invoke(
                    tool_call["args"]
                )

                # Add tool result to messages
                messages.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"]
                    )
                )

            if denied:
                continue

            # Loop again so Gemini can process tool results
            continue

        else:
            print("\nFinal Answer:\n")
            print(result.content)
            print("\n" + "=" * 50 + "\n")
            break


# User input
# LLM decides which tool to call
# Tool executes
# ToolMessage is added
# LLM processes the tool result
# Final answer