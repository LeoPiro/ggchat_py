import os
import secrets
import time
import asyncio
import uvicorn
import httpx
import json

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError

import discord
from discord.ext import commands

# === ENVIRONMENT ===
CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
GUILD_ID      = os.environ.get("DISCORD_GUILD_ID")
CHANNEL_ID    = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
BOT_TOKEN     = os.environ.get("DISCORD_BOT_TOKEN")
REDIRECT_URI  = os.environ.get("REDIRECT_URI", "http://localhost:8080/callback")
JWT_SECRET    = os.environ.get("JWT_SECRET", secrets.token_urlsafe(32))

# Check if Discord integration is enabled
DISCORD_ENABLED = all([CLIENT_ID, CLIENT_SECRET, GUILD_ID, BOT_TOKEN, CHANNEL_ID])

# === FASTAPI APP ===
app = FastAPI()
oauth_states = {}  # Maps OAuth state -> JWT
connections  = set()  # WebSocket connections
map_connections = set()  # Map WebSocket connections
channel_ref  = None  # Holds Discord channel object once bot is ready

# Mount static files for serving map assets
app.mount("/static", StaticFiles(directory="."), name="static")

# === DISCORD BOT SETUP ===
if DISCORD_ENABLED:
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(command_prefix="!", intents=intents)
else:
    bot = None
    print("[INFO] Discord integration disabled - missing environment variables")

# === FASTAPI ROUTES ===
@app.get("/")
async def home():
    if DISCORD_ENABLED:
        return {"message": "GG Guild Server with Discord Integration", "map_url": "/map"}
    else:
        return {"message": "GG Guild Server - Map Only Mode", "map_url": "/map"}

if DISCORD_ENABLED:
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

@app.get("/map")
async def serve_map():
    """Serve the map client HTML file"""
    try:
        with open("map_client.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content)
    except FileNotFoundError:
        return HTMLResponse("<h1>Map client not found</h1>", status_code=404)

@app.websocket("/map")
async def map_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for map functionality"""
    await websocket.accept()
    
    user_data = {"username": None}
    websocket.user_data = user_data  # Store on websocket immediately
    map_connections.add(websocket)
    
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            
            if data["type"] == "join":
                user_data["username"] = data["user"]
                
                # Get current user list
                user_list = []
                for conn in map_connections:
                    if hasattr(conn, 'user_data') and conn.user_data.get("username"):
                        user_list.append(conn.user_data["username"])
                
                # Send current user list to new user
                await websocket.send_text(json.dumps({
                    "type": "user_list",
                    "users": user_list
                }))
                
                # Notify others of new user
                for conn in map_connections.copy():
                    if conn != websocket:
                        try:
                            await conn.send_text(json.dumps({
                                "type": "user_joined",
                                "user": user_data["username"]
                            }))
                        except:
                            map_connections.discard(conn)
                
            elif data["type"] == "ping":
                # Broadcast ping to all other connected map users
                ping_data = {
                    "type": "ping",
                    "user": data["user"],
                    "lat": data["lat"],
                    "lng": data["lng"],
                    "timestamp": data["timestamp"]
                }
                
                for conn in map_connections.copy():
                    if conn != websocket:  # Don't send back to sender
                        try:
                            await conn.send_text(json.dumps(ping_data))
                        except:
                            map_connections.discard(conn)
    
    except Exception as e:
        print(f"[DEBUG] Map WebSocket error: {e}")
    finally:
        map_connections.discard(websocket)
        
        # Notify others that user left
        if user_data["username"]:
            for conn in map_connections.copy():
                try:
                    await conn.send_text(json.dumps({
                        "type": "user_left",
                        "user": user_data["username"]
                    }))
                except:
                    map_connections.discard(conn)

# === DISCORD BOT EVENTS ===
if DISCORD_ENABLED and bot:
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
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)

    tasks = [server.serve()]
    
    if DISCORD_ENABLED and bot:
        print("[INFO] Starting with Discord integration")
        bot_task = asyncio.create_task(bot.start(BOT_TOKEN))
        tasks.append(bot_task)
    else:
        print("[INFO] Starting in map-only mode (Discord integration disabled)")
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
