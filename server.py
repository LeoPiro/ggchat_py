import os
import secrets
import time
import asyncio
import uvicorn
import httpx

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from jose import jwt, JWTError

import discord
from discord.ext import commands

# === ENVIRONMENT ===
CLIENT_ID     = os.environ["DISCORD_CLIENT_ID"]
CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
GUILD_ID      = os.environ["DISCORD_GUILD_ID"]
CHANNEL_ID    = int(os.environ["DISCORD_CHANNEL_ID"])
BOT_TOKEN     = os.environ["DISCORD_BOT_TOKEN"]
REDIRECT_URI  = os.environ.get("REDIRECT_URI", "http://localhost:8800/callback")
JWT_SECRET    = os.environ.get("JWT_SECRET", secrets.token_urlsafe(32))

# === FASTAPI APP ===
app = FastAPI()
oauth_states = {}  # Maps OAuth state -> JWT
connections  = set()  # WebSocket connections
channel_ref  = None  # Holds Discord channel object once bot is ready

# === DISCORD BOT SETUP ===
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# === FASTAPI ROUTES ===
@app.get("/start")
async def start():
    state = secrets.token_urlsafe(16)
    oauth_states[state] = None
    scope = "identify guilds.members.read"
    auth_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code&scope={scope}&state={state}"
    )
    return {"auth_url": auth_url, "state": state}

@app.get("/callback")
async def callback(request: Request):
    code  = request.query_params.get("code")
    state = request.query_params.get("state")
    print(f"[DEBUG] Received code: {code}, state: {state}")

    if state not in oauth_states:
        return HTMLResponse("Invalid state", status_code=400)

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify guilds.members.read",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://discord.com/api/oauth2/token",
            data=data, headers=headers
        )
        print(f"[DEBUG] Token response status: {token_resp.status_code}")
        print(f"[DEBUG] Token response body: {token_resp.text}")
        token_json = token_resp.json()
        access_token = token_json.get("access_token")

    if not access_token:
        return HTMLResponse("Token exchange failed", status_code=400)

    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user = user_resp.json()
        user_id = user.get("id")
        print(f"[DEBUG] User response: {user_resp.status_code}, {user}")

        # ✅ Use bot token for member check
        member_resp = await client.get(
            f"https://discord.com/api/guilds/{GUILD_ID}/members/{user_id}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"}
        )
        print(f"[DEBUG] Member check status: {member_resp.status_code}")
        print(f"[DEBUG] Member check body: {member_resp.text}")

    if member_resp.status_code != 200:
        print("[!] Member check failed — user is not in the guild or bot lacks permissions.")
        return HTMLResponse("Not a guild member", status_code=403)

    member = member_resp.json()
    display_name = member.get("nick") or user.get("username")

    payload = {
        "user_id": user_id,
        "username": display_name,
        "guild_id": GUILD_ID,
        "exp": time.time() + 60 * 60 * 24 * 7
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    oauth_states[state] = token
    return HTMLResponse("<h3>Authentication successful! You can close this window.</h3>")

@app.get("/token")
async def get_token(state: str):
    token = oauth_states.get(state)
    return {"token": token}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global channel_ref
    await websocket.accept()
    token = websocket.query_params.get("token")
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (JWTError, TypeError):
        await websocket.close(code=1008)
        return

    connections.add(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            msg = f"[{data['username']}] {text}"

            # Send to WebSocket clients
            # First, send to the sender (so they see their own message)
            try:
                await websocket.send_text(msg)
            except:
                connections.discard(websocket)

            # Then send to all *other* clients
            for conn in connections.copy():
                if conn != websocket:
                    try:
                        await conn.send_text(msg)
                    except:
                        connections.discard(conn)

            # Send to Discord channel
            if channel_ref:
                try:
                    await channel_ref.send(msg)
                except Exception as e:
                    print(f"[!] Failed to send to Discord: {e}")
    except Exception:
        pass
    finally:
        connections.discard(websocket)

# === DISCORD BOT EVENTS ===
@bot.event
async def on_ready():
    global channel_ref
    print(f"[+] Discord bot connected as {bot.user}")
    channel_ref = bot.get_channel(CHANNEL_ID)
    if not channel_ref:
        print(f"[!] Failed to find channel with ID {CHANNEL_ID}")
    else:
        print(f"[+] Bound to channel: {channel_ref.name}")

@bot.event
async def on_message(message):
    print(f"[DEBUG] Received message from {message.author}: {message.content}")

    # Skip messages from the GGCHAT bot itself
    if message.author.id == bot.user.id:
        print("[DEBUG] Ignoring GGCHAT bot message")
        return

    if message.channel.id != CHANNEL_ID:
        print(f"[DEBUG] Ignoring message from different channel: {message.channel.id}")
        return

    msg = f"[{message.author.display_name}] {message.content}"
    for conn in connections.copy():
        try:
            await conn.send_text(msg)
        except:
            connections.discard(conn)


# === MAIN ENTRY ===
async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=8800, log_level="info")
    server = uvicorn.Server(config)

    bot_task = asyncio.create_task(bot.start(BOT_TOKEN))
    api_task = asyncio.create_task(server.serve())
    await asyncio.gather(bot_task, api_task)

if __name__ == "__main__":
    asyncio.run(main())
