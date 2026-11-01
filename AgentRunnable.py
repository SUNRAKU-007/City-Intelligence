# First step - loading all the libraries


#......... IMPLEMENTED NOT MANUALLY , GOOD ONE.........


from dotenv import load_dotenv
load_dotenv()

import os
import requests

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from tavily import TavilyClient
from rich import print

from langchain_core.runnables import(
    RunnableLambda,
    RunnablePassthrough
)




# Now let's create some tools

# Weather tool

API_KEY = os.getenv("OPENWEATHER_API_KEY")


@tool
def get_weather(city: str) -> str:
    """Get current weather of a city."""

    API_KEY = os.getenv("OPENWEATHER_API_KEY")

    url = "https://api.openweathermap.org/data/2.5/weather"

    try:
        response = requests.get(
            url,
            params={
                "q": f"{city},IN",
                "appid": API_KEY,
                "units": "metric"
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
    
    except requests.RequestException as e:
        return f"Weather API error: {e}"

    if str(data.get("cod")) != "200":
        return f"Error: {data.get('message', 'Could not fetch weather')}"

    temp = data["main"]["temp"]
    feels_like=data["main"]["feels_like"]
    humidity=data["main"]["humidity"]
    desc = data["weather"][0]["description"]

    return (
        f" Current Weather in {city}:\n"
        f" Condition: {desc}\n"
        f"TemperatureL {temp}°C\n"
        f"Feels like: {feels_like}°C\n"
        f"Humdidity: {humidity}%"
    )

# Tavily news tool

tavily_client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


@tool
def get_news(city: str) -> str:
    """Get the latest local news, events, and developments in an Indian city."""
    try:
        response = tavily_client.search(
            query=f"Latest local news, events, and developments in {city}, India",
            search_depth="basic",
            max_results=3
        )
    except Exception as e:
        return f"News search error: {e}"

    results = response.get("results", [])

    if not results:
        return f"No news found for {city}"

    news_list = []

    for r in results:
        title = r.get("title", "No title")
        url = r.get("url", "")
        snippet = r.get("content", "")

        news_list.append(
            f"- {title}\n"
            f" URL: {url}\n"
            f" Summary: {snippet[:300]}..."
        )

    return f"Latest news in {city}:\n\n" + "\n\n".join(news_list)


# Test the news tool

# print(get_news.invoke({"city": "Srinagar"}))


# LLM

llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    temperature=0.2
)

# HUMAN APPROVAL MIDDLEWARE
@wrap_tool_call
def human_approval(request,handler):
    """Ask the user for approval before every tool execution."""
    
    tool_name=request.tool_call["name"]
    tool_args=request.tool_call["args"]
    tool_call_id=request.tool_call["id"]
    
    print("\n [bold yellow]Human Approval Required[/bold yellow]")
    print(f"Tool: {tool_name}")
    print(f"Arguments: {tool_args}")
    
    confirm=input(
        "Approve this tool call? (yes/no):"
    ).strip().lower()
    
    if confirm!="yes":
        print("[red]Tool call denied.[/red]")
        
        return ToolMessage(
            content=(
                f"The user denied executionn of {tool_name}. "
                "Do not claim that the tool was executed"
            ),
            tool_call_id=tool_call_id
        )
    print("[green]Tool call approved.[/green]")
    
    return handler(request)


#...... CREATE AGENT    
agent=create_agent(
    model=llm,
    tools = [
    get_weather,
    get_news
    ],
    system_prompt=(
        "You are a helpful City Intelligence Assistant. "
        "You can retrieve current weather and recent news for Indian cities. "
        "Use get_weather when the user asks about weather. "
        "Use get_news when the user asks about recent news or local events. "
        "Use tool results to provide accurate, concise answers. "
        "Never invent weather readings or news results. "
        "If a tool call is denied, respect that decision and answer "
        "without pretending the tool was executed."
    ),
    middleware=[
        human_approval
    ]

# llm_with_tool = llm.bind_tools([get_weather, get_news])
)

#Runnable 1: INPUT PREPROCESSSING

def preprocess_input(data:dict)->dict:
    """Convert user input into te agent's expected format"""
    
    user_input=data["user_input"].strip()
    
    return {
        "messages": [
            {
                "role":"user",
                "content":user_input
    }
        ]
    }
    
input_runnable=RunnableLambda(preprocess_input)


# RUNNABLE 2: OUTPUT PROCESSING

def extract_final_answer(result: dict)->str:
    """Extract the final AI response from the agent result."""
    
    final_message=next(
        (
            message
            for message in reversed(result["messages"])
            if message.type=="ai"
            and not message.tool_calls
        ),
        None
    )
    if final_message is None:
        return "No final response was returned."
    
    content= final_message.content
    
    #Mose text responses are strings.
    #Handle structured content blocks as well.
    
    if isinstance(content,str):
        return content
    if isinstance(content,list):
        text_parts=[]
        
        for block in content:
            if isinstance(block,dict) and block.get("type")=="text":
                text_parts.append(block.get("text",""))
                
        if text_parts:
            return "\n".join(text_parts)
    
    return str(content)
output_runnable=RunnableLambda(extract_final_answer)

 # CITY INTELLIGENCE CHAIN
 
city_intelligence_chain=(
     RunnablePassthrough()
     | RunnableLambda(
         lambda user_input:{
             "user_input":user_input
         }
     )
     |input_runnable
     |agent
     |output_runnable
 )       

# CHAT LOOP

print("\n[bold cyan]City Intelligence Agent[/bold cyan]") 
print("Ask about weather or news in Indian cities.")
print("Type 'exit' to quit.\n")

while True:
    
    try:
        user_input=input("You: ").strip()
        
        if user_input.lower() =="exit":
            print("[yellow]GoodBye[/yellow]")
            break
        if not user_input:
            continue
        
        answer=city_intelligence_chain.invoke(user_input)
        
        print("\n[bold green]Assistant:[/bold green]")
        print(answer)
        
        print("\n"+"="*50 +"\n")
        
    except KeyboardInterrupt:
        print("\n [yellow]Agent stopped:[/yellow]")
        break
    except Exception as e:
        print(f"\n[bold red]Agent error: {e}[/bold red]")
        print()
