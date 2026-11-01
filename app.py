from dotenv import load_dotenv

load_dotenv()

import os
import html
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
import streamlit as st
from tavily import TavilyClient
from langchain.tools import tool
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

OWM = "https://api.openweathermap.org/data/2.5"

st.set_page_config(page_title="City Intelligence", page_icon="🏙️", layout="wide")


# ----------------------------------------------------------------------
# DATA LAYER (plain functions, return structured data)
# ----------------------------------------------------------------------
def _weather_raw(city: str):
    params = {
        "q": f"{city},IN",
        "appid": os.getenv("OPENWEATHER_API_KEY"),
        "units": "metric",
    }
    cur = requests.get(f"{OWM}/weather", params=params, timeout=10)
    cur.raise_for_status()
    fc = requests.get(f"{OWM}/forecast", params=params, timeout=10)
    fc.raise_for_status()
    return cur.json(), fc.json()


def _news_raw(city: str):
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    query = f"Latest local news, events, and developments in {city}, India"
    try:
        resp = client.search(
            query=query,
            topic="news",
            days=7,
            search_depth="basic",
            max_results=7,
        )
        results = resp.get("results", [])
    except Exception:
        results = []
    if not results:
        resp = client.search(query=query, search_depth="basic", max_results=7)
        results = resp.get("results", [])
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_weather(city: str):
    return _weather_raw(city)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_news(city: str):
    return _news_raw(city)


# ----------------------------------------------------------------------
# WEATHER UI
# ----------------------------------------------------------------------
def weather_emoji(wid: int, night: bool = False) -> str:
    if 200 <= wid < 300:
        return "⛈️"
    if 300 <= wid < 400:
        return "🌦️"
    if 500 <= wid < 600:
        return "🌧️"
    if 600 <= wid < 700:
        return "❄️"
    if 700 <= wid < 800:
        return "🌫️"
    if wid == 800:
        return "🌙" if night else "☀️"
    if wid == 801:
        return "🌤️"
    if wid == 802:
        return "⛅"
    return "☁️"


def weather_gradient(wid: int, night: bool) -> str:
    if night:
        return "linear-gradient(160deg,#0f1b3d,#27316b)"
    if 200 <= wid < 300:
        return "linear-gradient(160deg,#2b2d42,#6c5b7b)"
    if 300 <= wid < 600:
        return "linear-gradient(160deg,#3a5a78,#6f8fa8)"
    if 600 <= wid < 700:
        return "linear-gradient(160deg,#8fb3cc,#d6e6f2)"
    if 700 <= wid < 800:
        return "linear-gradient(160deg,#7b8794,#aab4be)"
    if wid == 800:
        return "linear-gradient(160deg,#1e88e5,#f2a65a)"
    return "linear-gradient(160deg,#4f7cac,#9ab6cf)"


def build_forecast(cur, fc):
    offset = timedelta(seconds=cur.get("timezone", 0))
    days = {}
    for item in fc["list"]:
        local = datetime.fromtimestamp(item["dt"], tz=timezone.utc) + offset
        days.setdefault(local.date(), []).append((local, item))
    out = []
    for date, entries in list(days.items())[:5]:
        lo = min(e["main"]["temp_min"] for _, e in entries)
        hi = max(e["main"]["temp_max"] for _, e in entries)
        _, mid = min(entries, key=lambda x: abs(x[0].hour - 12))
        out.append(
            {
                "date": date,
                "lo": lo,
                "hi": hi,
                "id": mid["weather"][0]["id"],
                "desc": mid["weather"][0]["description"],
            }
        )
    return out


def render_weather(city: str):
    cur, fc = fetch_weather(city)
    offset = timedelta(seconds=cur.get("timezone", 0))
    wid = cur["weather"][0]["id"]
    icon_code = cur["weather"][0]["icon"]
    night = icon_code.endswith("n")
    desc = cur["weather"][0]["description"].title()
    main = cur["main"]
    wind_kmh = cur["wind"]["speed"] * 3.6
    visibility_km = cur.get("visibility", 0) / 1000
    clouds = cur.get("clouds", {}).get("all", 0)

    def clock(ts):
        return (
            datetime.fromtimestamp(ts, tz=timezone.utc) + offset
        ).strftime("%I:%M %p")

    now_local = datetime.now(timezone.utc) + offset
    sunrise = clock(cur["sys"]["sunrise"])
    sunset = clock(cur["sys"]["sunset"])

    tiles = [
        ("🌡️", "Feels like", f"{main['feels_like']:.0f}°C"),
        ("💧", "Humidity", f"{main['humidity']}%"),
        ("💨", "Wind", f"{wind_kmh:.0f} km/h"),
        ("🧭", "Pressure", f"{main['pressure']} hPa"),
        ("👁️", "Visibility", f"{visibility_km:.1f} km"),
        ("☁️", "Cloud cover", f"{clouds}%"),
        ("🌅", "Sunrise", sunrise),
        ("🌇", "Sunset", sunset),
    ]
    tiles_html = "".join(
        f'<div class="wx-tile"><div class="wx-tile-icon">{i}</div>'
        f'<div class="wx-tile-label">{l}</div>'
        f'<div class="wx-tile-val">{v}</div></div>'
        for i, l, v in tiles
    )

    forecast = build_forecast(cur, fc)
    fc_html = ""
    for n, d in enumerate(forecast):
        label = "Today" if n == 0 else d["date"].strftime("%a")
        fc_html += (
            f'<div class="wx-day"><div class="wx-day-name">{label}</div>'
            f'<div class="wx-day-icon">{weather_emoji(d["id"])}</div>'
            f'<div class="wx-day-temp"><b>{d["hi"]:.0f}°</b> '
            f'<span>{d["lo"]:.0f}°</span></div></div>'
        )

    card = (
        f'<div class="wx-hero" style="background:{weather_gradient(wid, night)}">'
        f'<div class="wx-city">{html.escape(cur["name"])}</div>'
        f'<div class="wx-time">{now_local.strftime("%A, %d %B, %I:%M %p")}</div>'
        f'<div class="wx-main"><div class="wx-emoji">{weather_emoji(wid, night)}</div>'
        f'<div class="wx-temp">{main["temp"]:.0f}°</div></div>'
        f'<div class="wx-desc">{html.escape(desc)}</div>'
        f'<div class="wx-range">High {main["temp_max"]:.0f}°  Low {main["temp_min"]:.0f}°</div>'
        f"</div>"
        f'<div class="wx-grid">{tiles_html}</div>'
        f'<div class="wx-forecast-title">5-day forecast</div>'
        f'<div class="wx-forecast">{fc_html}</div>'
    )
    st.markdown(card, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# NEWSPAPER UI
# ----------------------------------------------------------------------
def trim(text: str, limit: int = 340) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def article_html(r, lead=False):
    title = html.escape(r.get("title") or "Untitled")
    url = html.escape(r.get("url") or "#", quote=True)
    source = html.escape(urlparse(r.get("url", "")).netloc.replace("www.", ""))
    body = html.escape(trim(r.get("content", ""), 520 if lead else 300))
    cls = "np-lead" if lead else "np-story"
    return (
        f'<div class="{cls}"><div class="np-source">{source}</div>'
        f'<a class="np-headline" href="{url}" target="_blank">{title}</a>'
        f'<p class="np-body">{body}</p>'
        f'<a class="np-more" href="{url}" target="_blank">Continue reading</a></div>'
    )


def render_news(city: str):
    results = fetch_news(city)
    today = datetime.now().strftime("%A, %d %B %Y")
    masthead = (
        f'<div class="np-paper">'
        f'<div class="np-mast"><div class="np-title">The {html.escape(city.title())} Chronicle</div>'
        f'<div class="np-bar"><span>{today}</span>'
        f"<span>Local edition</span><span>Free to read</span></div></div>"
    )
    if not results:
        st.markdown(
            masthead
            + '<p class="np-body" style="text-align:center;padding:40px">'
            "No stories found today. Try another city or check your Tavily key.</p></div>",
            unsafe_allow_html=True,
        )
        return
    lead = article_html(results[0], lead=True)
    rest = "".join(article_html(r) for r in results[1:])
    st.markdown(
        masthead + lead + f'<div class="np-columns">{rest}</div></div>',
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------
# AGENT (for the chat tab)
# ----------------------------------------------------------------------
@tool
def get_weather(city: str) -> str:
    """Get current weather of an Indian city."""
    try:
        cur, _ = _weather_raw(city)
    except requests.RequestException as e:
        return f"Weather API error: {e}"
    m = cur["main"]
    return (
        f"Current weather in {city}: {cur['weather'][0]['description']}, "
        f"{m['temp']}°C (feels like {m['feels_like']}°C), humidity {m['humidity']}%, "
        f"wind {cur['wind']['speed'] * 3.6:.0f} km/h."
    )


@tool
def get_news(city: str) -> str:
    """Get the latest local news, events, and developments in an Indian city."""
    try:
        results = _news_raw(city)
    except Exception as e:
        return f"News search error: {e}"
    if not results:
        return f"No news found for {city}"
    items = [
        f"- {r.get('title')}\n URL: {r.get('url')}\n Summary: {trim(r.get('content', ''), 300)}"
        for r in results[:3]
    ]
    return f"Latest news in {city}:\n\n" + "\n\n".join(items)


@st.cache_resource
def get_agent():
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", temperature=0.2)
    return create_agent(
        model=llm,
        tools=[get_weather, get_news],
        system_prompt=(
            "You are a helpful City Intelligence Assistant. "
            "You can retrieve current weather and recent news for Indian cities. "
            "Use get_weather when the user asks about weather. "
            "Use get_news when the user asks about recent news or local events. "
            "Use tool results to provide accurate, concise answers. "
            "Never invent weather readings or news results."
        ),
    )


def extract_final_answer(result: dict) -> str:
    final = next(
        (m for m in reversed(result["messages"]) if m.type == "ai" and not m.tool_calls),
        None,
    )
    if final is None:
        return "No final response was returned."
    content = final.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        if parts:
            return "\n".join(parts)
    return str(content)


def tools_used(result: dict):
    names = []
    for m in result["messages"]:
        if m.type == "ai" and m.tool_calls:
            names += [c["name"] for c in m.tool_calls]
    return names


# ----------------------------------------------------------------------
# STYLES
# ----------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:wght@400;600&display=swap');

/* ---------- weather ---------- */
.wx-hero{border-radius:28px;padding:32px 36px;color:#fff;box-shadow:0 10px 30px rgba(0,0,0,.18)}
.wx-city{font-size:2rem;font-weight:700}
.wx-time{opacity:.85;margin-bottom:8px}
.wx-main{display:flex;align-items:center;gap:20px}
.wx-emoji{font-size:5rem;line-height:1}
.wx-temp{font-size:6.5rem;font-weight:200;line-height:1}
.wx-desc{font-size:1.5rem;margin-top:4px}
.wx-range{opacity:.9;margin-top:4px;white-space:pre}
.wx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:18px}
.wx-tile{background:rgba(127,127,127,.12);border-radius:18px;padding:16px}
.wx-tile-icon{font-size:1.4rem}
.wx-tile-label{opacity:.7;font-size:.85rem;margin-top:4px}
.wx-tile-val{font-size:1.4rem;font-weight:600}
.wx-forecast-title{font-weight:600;margin:24px 0 10px;font-size:1.1rem}
.wx-forecast{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:12px}
.wx-day{background:rgba(127,127,127,.12);border-radius:18px;padding:14px;text-align:center}
.wx-day-name{font-weight:600}
.wx-day-icon{font-size:2rem;margin:6px 0}
.wx-day-temp span{opacity:.6}

/* ---------- newspaper ---------- */
.np-paper{background:#e9e7df;color:#1c1c1c;padding:28px 36px 36px;border:1px solid #bdb9ab;
  box-shadow:0 12px 28px rgba(0,0,0,.22);font-family:'Source Serif 4',Georgia,serif}
.np-mast{text-align:center;border-bottom:4px double #1c1c1c;padding-bottom:10px;margin-bottom:22px}
.np-title{font-family:'Playfair Display',serif;font-weight:900;font-size:3.6rem;line-height:1.1}
.np-bar{display:flex;justify-content:space-between;border-top:1px solid #1c1c1c;
  margin-top:10px;padding-top:6px;font-size:.9rem;font-style:italic}
.np-lead{border-bottom:1px solid #1c1c1c;padding-bottom:20px;margin-bottom:22px}
.np-lead .np-headline{font-size:2.5rem}
.np-lead .np-body::first-letter{font-family:'Playfair Display',serif;font-weight:900;font-size:3.6rem;
  float:left;line-height:.85;padding:6px 8px 0 0}
.np-columns{column-count:3;column-gap:32px;column-rule:1px solid #1c1c1c}
.np-story{break-inside:avoid;padding-bottom:18px;margin-bottom:18px;border-bottom:1px solid #b5b1a3}
.np-source{font-style:italic;font-size:.85rem;color:#5a5648;margin-bottom:2px}
.np-headline{display:block;font-family:'Playfair Display',serif;font-weight:700;font-size:1.35rem;
  line-height:1.2;color:#1c1c1c !important;text-decoration:none !important}
.np-headline:hover{text-decoration:underline !important}
.np-body{text-align:justify;hyphens:auto;line-height:1.6;font-size:1rem;margin:8px 0}
.np-more{font-size:.9rem;font-style:italic;color:#7a1f1f !important}
@media (max-width:900px){.np-columns{column-count:1}.np-title{font-size:2.2rem}.wx-temp{font-size:4.5rem}}
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# PAGE
# ----------------------------------------------------------------------
st.title("🏙️ City Intelligence")

with st.form("city_form", border=False):
    c1, c2 = st.columns([5, 1])
    city_input = c1.text_input(
        "City", value=st.session_state.get("city", "Srinagar"),
        placeholder="Type an Indian city, for example Jalandhar",
        label_visibility="collapsed",
    )
    submitted = c2.form_submit_button("Search", use_container_width=True)

if submitted and city_input.strip():
    st.session_state["city"] = city_input.strip()
city = st.session_state.get("city", "Srinagar")

tab_weather, tab_news, tab_chat = st.tabs(["🌤️ Weather", "📰 News", "💬 Ask the agent"])

with tab_weather:
    try:
        with st.spinner("Fetching weather..."):
            render_weather(city)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            st.error(f"Could not find '{city}'. Check the spelling and try again.")
        else:
            st.error(f"Weather API error: {e}")
    except Exception as e:
        st.error(f"Could not load weather: {e}")

with tab_news:
    try:
        with st.spinner("Printing today's edition..."):
            render_news(city)
    except Exception as e:
        st.error(f"Could not load news: {e}")

with tab_chat:
    if "chat" not in st.session_state:
        st.session_state["chat"] = []
    for msg in st.session_state["chat"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("tools"):
                st.caption("Tools used: " + ", ".join(msg["tools"]))

    prompt = st.chat_input("Ask about weather or news in an Indian city")
    if prompt:
        st.session_state["chat"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state["chat"]
                    ]
                    result = get_agent().invoke({"messages": history})
                    answer = extract_final_answer(result)
                    used = tools_used(result)
                except Exception as e:
                    answer, used = f"Agent error: {e}", []
            st.markdown(answer)
            if used:
                st.caption("Tools used: " + ", ".join(used))
        st.session_state["chat"].append(
            {"role": "assistant", "content": answer, "tools": used}
        )