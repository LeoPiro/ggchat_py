import os
import secrets
import time
import asyncio
import uvicorn
import httpx
import json
import yaml

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
REDIRECT_URI  = os.environ.get("REDIRECT_URI", "http://localhost:8888/callback")
JWT_SECRET    = os.environ.get("JWT_SECRET", secrets.token_urlsafe(32))
DKP_FILE_PATH = os.environ.get("DKP_FILE_PATH", "/root/GG_Discord/GGDiscordBot/cogs/dkp.yaml")

# Check if Discord integration is enabled
DISCORD_ENABLED = all([CLIENT_ID, CLIENT_SECRET, GUILD_ID, BOT_TOKEN, CHANNEL_ID])

# === FASTAPI APP ===
app = FastAPI()
oauth_states = {}  # Maps OAuth state -> JWT
connections  = set()  # WebSocket connections
map_connections = set()  # Map WebSocket connections
channel_ref  = None  # Holds Discord channel object once bot is ready
active_polls = {}  # Maps poll_id -> {question, votes: {username: vote}, creator, timestamp}
dkp_data = {}  # Cached DKP data {username: points}
dkp_last_updated = 0  # Timestamp of last DKP file read

# Mount static files for serving map assets
app.mount("/static", StaticFiles(directory="."), name="static")

# === DKP FUNCTIONS ===
def load_dkp_data():
    """Load DKP data from YAML file"""
    global dkp_data, dkp_last_updated
    try:
        if os.path.exists(DKP_FILE_PATH):
            with open(DKP_FILE_PATH, 'r') as f:
                dkp_data = yaml.safe_load(f) or {}
            dkp_last_updated = time.time()
            print(f"[DKP] Loaded {len(dkp_data)} DKP entries")
        else:
            print(f"[DKP] File not found: {DKP_FILE_PATH}")
            dkp_data = {}
    except Exception as e:
        print(f"[DKP] Error loading DKP data: {e}")
        dkp_data = {}

def get_user_dkp(username):
    """Get DKP for a specific user"""
    # Refresh DKP data if it's older than 5 minutes
    if time.time() - dkp_last_updated > 300:  # 5 minutes
        load_dkp_data()
    
    return dkp_data.get(username.lower(), 0)

# Load DKP data on startup
load_dkp_data()

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

            # ✅ Use bot token for member check
            member_resp = await client.get(
                f"https://discord.com/api/guilds/{GUILD_ID}/members/{user_id}",
                headers={"Authorization": f"Bot {BOT_TOKEN}"}
            )

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
    
    @app.get("/dkp")
    async def get_dkp(username: str):
        """Get DKP for a specific user"""
        dkp = get_user_dkp(username)
        return {"username": username, "dkp": dkp}

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
                
                # Check if it's a JSON message (poll command)
                try:
                    json_data = json.loads(text)
                    if json_data.get("type") == "poll_create":
                        # Handle poll creation
                        poll_id = f"poll_{int(time.time())}_{secrets.token_urlsafe(8)}"
                        active_polls[poll_id] = {
                            "question": json_data["question"],
                            "votes": {},
                            "creator": data['username'],
                            "timestamp": time.time()
                        }
                        
                        # Broadcast poll to all clients
                        poll_msg = json.dumps({
                            "type": "poll",
                            "poll_id": poll_id,
                            "question": json_data["question"],
                            "creator": data['username'],
                            "votes": {}
                        })
                        
                        for conn in connections.copy():
                            try:
                                await conn.send_text(poll_msg)
                            except:
                                connections.discard(conn)
                        
                        # Send to Discord channel
                        if channel_ref:
                            try:
                                await channel_ref.send(f"📊 **Poll from {data['username']}:** {json_data['question']}")
                            except Exception as e:
                                print(f"[!] Failed to send poll to Discord: {e}")
                        continue
                    
                    elif json_data.get("type") == "poll_vote":
                        # Handle poll vote
                        poll_id = json_data["poll_id"]
                        vote = json_data["vote"]  # "up" or "down"
                        
                        if poll_id in active_polls:
                            active_polls[poll_id]["votes"][data['username']] = vote
                            
                            # Broadcast vote update to all clients
                            vote_msg = json.dumps({
                                "type": "poll_update",
                                "poll_id": poll_id,
                                "votes": active_polls[poll_id]["votes"]
                            })
                            
                            for conn in connections.copy():
                                try:
                                    await conn.send_text(vote_msg)
                                except:
                                    connections.discard(conn)
                        continue
                    
                except (json.JSONDecodeError, KeyError):
                    # Not a JSON message or not a poll command, treat as regular message
                    pass
                
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
        pass  # Connection closed
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
        # Skip messages from the GGCHAT bot itself
        if message.author.id == bot.user.id:
            return

        if message.channel.id != CHANNEL_ID:
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
