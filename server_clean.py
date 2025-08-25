import os
import secrets
import time
import asyncio
import uvicorn
import httpx
import json
import base64
import io
import re
from typing import List, Dict, Tuple

from fastapi import FastAPI, Request, WebSocket, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError

import discord
from discord.ext import commands

# OCR and image processing
try:
    import cv2
    import numpy as np
    from PIL import Image
    IMAGE_MATCHING_AVAILABLE = True
except ImportError:
    IMAGE_MATCHING_AVAILABLE = False
    print("[WARNING] Image matching dependencies not available. Install with: pip install opencv-python-headless pillow")

# Discord configuration - should be set as environment variables
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "YOUR_DISCORD_CLIENT_ID_HERE")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "YOUR_DISCORD_CLIENT_SECRET_HERE")
DISCORD_REDIRECT_URI = "http://localhost:8000/callback"

# FastAPI app
app = FastAPI()

# In-memory session storage
sessions = {}

# Discord intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# Discord bot token - should be set as environment variable
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")

# Initialize the Discord bot
bot = commands.Bot(command_prefix='!', intents=intents)

# Basic routes and functions (existing code continues here...)
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>GGChat</title>
    </head>
    <body>
        <h1>Welcome to GGChat</h1>
        <a href="/start">Login with Discord</a>
    </body>
    </html>
    """

# Discord OAuth routes
@app.get("/start")
async def start():
    state = secrets.token_urlsafe(32)
    sessions[state] = {"created_at": time.time()}
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify&state={state}"
    return HTMLResponse(f'<script>window.location.href = "{auth_url}";</script>')

@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if not code or not state or state not in sessions:
        return HTMLResponse("Authorization failed", status_code=400)
    
    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        }
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            response = await client.post("https://discord.com/api/oauth2/token", data=token_data, headers=headers)
            response.raise_for_status()
            token_response = response.json()
            
            access_token = token_response["access_token"]
            
            # Get user info
            user_headers = {"Authorization": f"Bearer {access_token}"}
            user_response = await client.get("https://discord.com/api/users/@me", headers=user_headers)
            user_response.raise_for_status()
            user_data = user_response.json()
            
            # Create JWT token
            jwt_payload = {
                "user_id": user_data["id"],
                "username": user_data["username"],
                "exp": time.time() + 3600  # 1 hour expiration
            }
            jwt_token = jwt.encode(jwt_payload, "your_secret_key", algorithm="HS256")
            
            # Clean up session
            del sessions[state]
            
            return HTMLResponse(f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Login Successful</title>
                </head>
                <body>
                    <h1>Welcome, {user_data['username']}!</h1>
                    <script>
                        localStorage.setItem('jwt_token', '{jwt_token}');
                        setTimeout(() => window.location.href = '/chat', 1000);
                    </script>
                </body>
                </html>
            """)
        
        except Exception as e:
            print(f"OAuth error: {e}")
            return HTMLResponse("Authentication failed", status_code=400)

@app.get("/token/{state}")
async def get_token(state: str):
    return sessions.get(state, {})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                
                if message.get("type") == "auth":
                    token = message.get("token")
                    try:
                        payload = jwt.decode(token, "your_secret_key", algorithms=["HS256"])
                        await websocket.send_text(json.dumps({
                            "type": "auth_success", 
                            "user": payload
                        }))
                    except JWTError:
                        await websocket.send_text(json.dumps({
                            "type": "auth_error", 
                            "message": "Invalid token"
                        }))
                
                elif message.get("type") == "chat_message":
                    # Echo message back for now
                    await websocket.send_text(json.dumps({
                        "type": "message",
                        "content": message.get("content", ""),
                        "username": message.get("username", "Unknown"),
                        "timestamp": time.time()
                    }))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error", 
                    "message": "Invalid JSON"
                }))
                
    except Exception as e:
        print(f"WebSocket error: {e}")

# Map-related routes
@app.get("/map")
async def serve_map():
    return HTMLResponse(open("map_client.html").read())

@app.websocket("/ws/map")
async def map_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            else:
                await websocket.send_text(json.dumps({
                    "type": "echo",
                    "data": message
                }))
    except Exception as e:
        print(f"Map WebSocket error: {e}")

# Image matching functionality
if IMAGE_MATCHING_AVAILABLE:
    
    def find_image_in_map(query_image: Image.Image, map_image_path: str = "ggmap.png") -> dict:
        """
        Simple template matching for finding image locations on the map
        """
        try:
            # Load the base map image
            if not os.path.exists(map_image_path):
                return {"error": f"Base map image not found: {map_image_path}"}
            
            base_map = cv2.imread(map_image_path)
            if base_map is None:
                return {"error": f"Could not load base map: {map_image_path}"}
            
            # Convert PIL query image to OpenCV format
            query_cv = cv2.cvtColor(np.array(query_image), cv2.COLOR_RGB2BGR)
            
            # Get dimensions
            query_h, query_w = query_cv.shape[:2]
            map_h, map_w = base_map.shape[:2]
            original_map_h = map_h
            
            print(f"[DEBUG] Query size: {query_w}x{query_h}, Map size: {map_w}x{map_h}")
            
            # Crop map to exclude restricted areas
            max_x = 4600
            max_y = 4000
            
            if map_w > max_x:
                base_map = base_map[:, :max_x]
                map_w = max_x
                print(f"[DEBUG] Cropped map width to x={max_x}")
            
            if map_h > max_y:
                base_map = base_map[:max_y, :]
                map_h = max_y
                print(f"[DEBUG] Cropped map height to y={max_y}")
            
            # Check if query image is too large
            if query_w > map_w or query_h > map_h:
                return {
                    "matches": [],
                    "message": "Query image is larger than the searchable map area",
                    "query_size": [query_w, query_h],
                    "map_size": [map_w, map_h]
                }
            
            # Scale down for performance if needed
            scale_factor = 1.0
            max_dimension = 2048
            
            if map_w > max_dimension or map_h > max_dimension:
                scale_factor = max_dimension / max(map_w, map_h)
                new_map_w = int(map_w * scale_factor)
                new_map_h = int(map_h * scale_factor)
                base_map_scaled = cv2.resize(base_map, (new_map_w, new_map_h))
                query_cv_scaled = cv2.resize(query_cv, 
                    (int(query_w * scale_factor), int(query_h * scale_factor)))
                print(f"[DEBUG] Scaled to: {new_map_w}x{new_map_h}, scale: {scale_factor:.3f}")
            else:
                base_map_scaled = base_map
                query_cv_scaled = query_cv
            
            # Simple template matching - focus on accuracy over performance
            best_matches = []
            
            # Try different matching methods
            methods = [
                (cv2.TM_CCOEFF_NORMED, "correlation", 0.4),
                (cv2.TM_CCORR_NORMED, "cross_correlation", 0.4),
                (cv2.TM_SQDIFF_NORMED, "squared_diff", 0.6)
            ]
            
            for method, name, threshold in methods:
                print(f"[DEBUG] Trying {name} method")
                
                try:
                    result = cv2.matchTemplate(base_map_scaled, query_cv_scaled, method)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                    
                    # For SQDIFF, lower values are better
                    if method == cv2.TM_SQDIFF_NORMED:
                        confidence = 1.0 - min_val
                        best_match_loc = min_loc
                        threshold = 1.0 - threshold
                    else:
                        confidence = max_val
                        best_match_loc = max_loc
                    
                    print(f"[DEBUG] {name}: confidence={confidence:.3f}, threshold={threshold:.3f}")
                    
                    if confidence >= threshold:
                        # Calculate center coordinates
                        center_x = int((best_match_loc[0] + query_cv_scaled.shape[1] // 2) / scale_factor)
                        center_y = int((best_match_loc[1] + query_cv_scaled.shape[0] // 2) / scale_factor)
                        
                        # Skip if out of bounds
                        if center_x > 4600:
                            print(f"[DEBUG] Skipping match beyond x=4600: {center_x}")
                            continue
                        
                        # Convert to Leaflet coordinates
                        leaflet_lat = original_map_h - center_y
                        leaflet_lng = center_x
                        
                        match_info = {
                            "confidence": float(confidence),
                            "raw_confidence": float(confidence),
                            "method": name,
                            "pixel_location": [center_x, center_y],
                            "leaflet_location": [leaflet_lat, leaflet_lng]
                        }
                        best_matches.append(match_info)
                        
                        print(f"[DEBUG] Found match: {confidence:.3f} at ({center_x}, {center_y})")
                
                except Exception as e:
                    print(f"[DEBUG] Method {name} failed: {e}")
                    continue
            
            # Sort by confidence
            best_matches.sort(key=lambda x: x['confidence'], reverse=True)
            
            if best_matches:
                return {
                    "matches": best_matches[:3],  # Return top 3 matches
                    "total_found": len(best_matches),
                    "method_used": "simple_template_matching",
                    "query_size": [query_w, query_h],
                    "map_size": [map_w, map_h],
                    "scale_factor": scale_factor
                }
            else:
                return {
                    "matches": [],
                    "message": "No suitable matches found",
                    "query_size": [query_w, query_h],
                    "map_size": [map_w, map_h]
                }
                
        except Exception as e:
            print(f"[ERROR] Image matching failed: {e}")
            import traceback
            traceback.print_exc()
            return {"error": f"Image matching failed: {str(e)}"}

    def find_image_in_map_debug(query_image: Image.Image, map_image_path: str = "ggmap.png") -> dict:
        """Debug version that saves intermediate images and provides detailed analysis"""
        try:
            # Load the base map image
            if not os.path.exists(map_image_path):
                return {"error": f"Base map image not found: {map_image_path}"}
            
            base_map = cv2.imread(map_image_path)
            if base_map is None:
                return {"error": f"Could not load base map: {map_image_path}"}
            
            # Convert query image to OpenCV format
            query_array = np.array(query_image)
            if len(query_array.shape) == 3:
                query_cv = cv2.cvtColor(query_array, cv2.COLOR_RGB2BGR)
            else:
                query_cv = query_array
            
            # Save debug images
            cv2.imwrite("debug_query.png", query_cv)
            print(f"[DEBUG] Saved query image as debug_query.png ({query_cv.shape})")
            
            # Get dimensions
            query_h, query_w = query_cv.shape[:2]
            map_h, map_w = base_map.shape[:2]
            max_x = 4600
            max_y = 4000
            original_map_h = map_h  # Store original height for coordinate conversion
            
            print(f"[DEBUG] Original sizes - Query: {query_w}x{query_h}, Map: {map_w}x{map_h}")
            
            # Crop map to exclude areas beyond boundaries
            if map_w > max_x:
                base_map = base_map[:, :max_x]
                map_w = max_x
                print(f"[DEBUG] Cropped map width to x={max_x}")
            
            if map_h > max_y:
                base_map = base_map[:max_y, :]
                map_h = max_y
                print(f"[DEBUG] Cropped map height to y={max_y}")
            
            print(f"[DEBUG] Final cropped map size: {map_w}x{map_h}")
            cv2.imwrite("debug_cropped_map.png", base_map)
            
            # Scale if needed
            scale_factor = 1.0
            max_dimension = 2048
            if map_w > max_dimension or map_h > max_dimension:
                scale_factor = max_dimension / max(map_w, map_h)
                new_map_w = int(map_w * scale_factor)
                new_map_h = int(map_h * scale_factor)
                base_map_scaled = cv2.resize(base_map, (new_map_w, new_map_h))
                query_cv_scaled = cv2.resize(query_cv, 
                    (int(query_w * scale_factor), int(query_h * scale_factor)))
                print(f"[DEBUG] Scaled to: Map {new_map_w}x{new_map_h}, Query {query_cv_scaled.shape}")
            else:
                base_map_scaled = base_map
                query_cv_scaled = query_cv
            
            cv2.imwrite("debug_scaled_map.png", base_map_scaled)
            cv2.imwrite("debug_scaled_query.png", query_cv_scaled)
            
            # Try simple template matching with very low threshold
            result = cv2.matchTemplate(base_map_scaled, query_cv_scaled, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            print(f"[DEBUG] Template matching result: min={min_val:.3f}, max={max_val:.3f}")
            print(f"[DEBUG] Best match location: {max_loc}")
            
            # Create visualization of the match result
            result_vis = cv2.normalize(result, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
            cv2.imwrite("debug_match_heatmap.png", result_vis)
            
            # Draw rectangle on map showing best match
            map_with_match = base_map_scaled.copy()
            top_left = max_loc
            bottom_right = (top_left[0] + query_cv_scaled.shape[1], top_left[1] + query_cv_scaled.shape[0])
            cv2.rectangle(map_with_match, top_left, bottom_right, (0, 255, 0), 3)
            cv2.imwrite("debug_map_with_match.png", map_with_match)
            
            # Calculate actual coordinates
            center_x = int((max_loc[0] + query_cv_scaled.shape[1] // 2) / scale_factor)
            center_y = int((max_loc[1] + query_cv_scaled.shape[0] // 2) / scale_factor)
            leaflet_lat = original_map_h - center_y  # Use original map height for proper coordinate conversion
            leaflet_lng = center_x
            
            debug_result = {
                "debug_analysis": {
                    "max_confidence": float(max_val),
                    "min_confidence": float(min_val),
                    "best_location_scaled": list(max_loc),
                    "best_location_original": [center_x, center_y],
                    "leaflet_coords": [leaflet_lat, leaflet_lng],
                    "scale_factor": scale_factor,
                    "query_size": [query_w, query_h],
                    "map_size_original": [10752, 6144],
                    "map_size_cropped": [map_w, map_h],
                    "would_pass_threshold_0.15": max_val >= 0.15,
                    "would_pass_threshold_0.2": max_val >= 0.2,
                    "would_pass_threshold_0.25": max_val >= 0.25,
                    "would_pass_threshold_0.3": max_val >= 0.3
                },
                "debug_files": [
                    "debug_uploaded_original.png",
                    "debug_query.png", 
                    "debug_cropped_map.png",
                    "debug_scaled_map.png",
                    "debug_scaled_query.png",
                    "debug_match_heatmap.png",
                    "debug_map_with_match.png"
                ],
                "matches": [],
                "message": f"Debug analysis complete. Best confidence: {max_val:.3f}"
            }
            
            # If there's any reasonable match, include it
            if max_val >= 0.1:  # Very low threshold for debug
                debug_result["matches"] = [{
                    "confidence": float(max_val),
                    "method": "debug_simple_match",
                    "pixel_location": [center_x, center_y],
                    "leaflet_location": [leaflet_lat, leaflet_lng],
                    "bounds": {
                        "top_left": [int(max_loc[0] / scale_factor), int(max_loc[1] / scale_factor)],
                        "bottom_right": [int((max_loc[0] + query_cv_scaled.shape[1]) / scale_factor), 
                                       int((max_loc[1] + query_cv_scaled.shape[0]) / scale_factor)]
                    }
                }]
            
            return debug_result
            
        except Exception as e:
            print(f"[DEBUG ERROR] {e}")
            import traceback
            traceback.print_exc()
            return {"error": f"Debug matching failed: {str(e)}"}

    # Image matching endpoints
    @app.post("/api/match-image")
    async def match_image_endpoint(request: Request):
        """Image matching endpoint for finding image locations on the map"""
        try:
            body = await request.body()
            data = json.loads(body)
            
            if "image" not in data:
                return JSONResponse({"error": "No image data provided"}, status_code=400)
            
            # Decode base64 image
            image_data = data["image"]
            if image_data.startswith("data:image"):
                image_data = image_data.split(",")[1]
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            
            # Save uploaded image for debugging
            image.save("debug_uploaded_original.png")
            print(f"[DEBUG] Uploaded image saved: {image.size}")
            
            # Perform image matching
            result = find_image_in_map(image)
            return JSONResponse(result)
            
        except Exception as e:
            print(f"[ERROR] Match image endpoint: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse({"error": f"Image processing failed: {str(e)}"}, status_code=500)

    @app.post("/api/match-image-debug")
    async def match_image_debug_endpoint(request: Request):
        """Debug version of image matching with detailed analysis"""
        try:
            body = await request.body()
            data = json.loads(body)
            
            if "image" not in data:
                return JSONResponse({"error": "No image data provided"}, status_code=400)
            
            # Decode base64 image
            image_data = data["image"]
            if image_data.startswith("data:image"):
                image_data = image_data.split(",")[1]
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            
            # Save uploaded image for debugging
            image.save("debug_uploaded_original.png")
            print(f"[DEBUG] Debug uploaded image saved: {image.size}")
            
            # Perform debug image matching
            result = find_image_in_map_debug(image)
            return JSONResponse(result)
            
        except Exception as e:
            print(f"[DEBUG ERROR] Debug match endpoint: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse({"error": f"Debug image processing failed: {str(e)}"}, status_code=500)

else:
    @app.post("/api/match-image")
    async def match_image_disabled():
        return JSONResponse({
            "error": "Image matching functionality not available. Please install required dependencies."
        }, status_code=503)
    
    @app.post("/api/match-image-debug") 
    async def match_image_debug_disabled():
        return JSONResponse({
            "error": "Debug image matching functionality not available. Please install required dependencies."
        }, status_code=503)

# Serve debug images
@app.get("/{filename}")
async def serve_debug_image(filename: str):
    if filename.startswith("debug_") and filename.endswith(".png"):
        if os.path.exists(filename):
            from fastapi.responses import FileResponse
            return FileResponse(filename)
    return JSONResponse({"error": "File not found"}, status_code=404)

# Discord bot events
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    print(f'Message from {message.author}: {message.content}')
    
    if message.content.startswith('!hello'):
        await message.channel.send(f'Hello {message.author}!')
    
    await bot.process_commands(message)

# Main function
async def main():
    # Start the Discord bot in the background
    bot_task = asyncio.create_task(bot.start(DISCORD_BOT_TOKEN))
    
    # Start the FastAPI server
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        # Clean shutdown
        await bot.close()
        bot_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
