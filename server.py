import os
import secrets
import time
import asyncio
import uvicorn
import httpx
import json
import base64
import io
import cv2
import numpy as np
import pytesseract
from PIL import Image

from fastapi import FastAPI, Request, WebSocket, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError
from pydantic import BaseModel

import discord
from discord.ext import commands

# === ENVIRONMENT ===
CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
GUILD_ID      = os.environ.get("GUILD_ID")
TOKEN         = os.environ.get("DISCORD_TOKEN")
FIXER_TOKEN   = os.environ.get("FIXER_TOKEN")

def enhance_image_features(image):
    """
    Enhanced preprocessing to improve feature detection
    """
    try:
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(image)
        
        # Apply slight Gaussian blur to reduce noise
        enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)
        
        return enhanced
    except Exception as e:
        print(f"Enhancement error: {e}")
        return image

def verify_match_quality(map_img, template, x, y, w, h):
    """
    More lenient verification to reduce false negatives
    """
    try:
        # Extract the matched region from the map
        if x < 0 or y < 0 or x + w >= map_img.shape[1] or y + h >= map_img.shape[0]:
            return False
            
        matched_region = map_img[y:y+h, x:x+w]
        
        # Resize to match template if needed
        if matched_region.shape != template.shape:
            matched_region = cv2.resize(matched_region, (template.shape[1], template.shape[0]))
        
        # Calculate basic correlation - more lenient threshold
        correlation = cv2.matchTemplate(matched_region, template, cv2.TM_CCOEFF_NORMED)[0, 0]
        
        # Much more lenient verification - if template matching found it, it's probably good
        return correlation > 0.3  # Lowered from 0.5 to 0.3
        
    except Exception as e:
        print(f"Verification error: {e}")
        return True  # Default to accepting if verification fails

def remove_duplicate_matches(matches, min_distance=50):
    """
    Remove matches that are too close to each other, keeping the one with highest confidence
    """
    if not matches:
        return matches
    
    filtered_matches = []
    for match in matches:
        # Check if this match is too close to any already filtered match
        is_duplicate = False
        for existing_match in filtered_matches:
            distance = ((match["x"] - existing_match["x"]) ** 2 + 
                       (match["y"] - existing_match["y"]) ** 2) ** 0.5
            if distance < min_distance:
                # If current match has higher confidence, replace the existing one
                if match["confidence"] > existing_match["confidence"]:
                    filtered_matches.remove(existing_match)
                    break
                else:
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            filtered_matches.append(match)
    
    return filtered_matches

TOKEN         = os.environ.get("DISCORD_TOKEN")
FIXER_TOKEN   = os.environ.get("FIXER_TOKEN")
GUILD_ID      = int(os.environ.get("DISCORD_GUILD_ID"))
CHANNEL_ID    = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
BOT_TOKEN     = os.environ.get("DISCORD_BOT_TOKEN")
REDIRECT_URI  = os.environ.get("REDIRECT_URI", "http://localhost:8888/callback")
JWT_SECRET    = os.environ.get("JWT_SECRET", secrets.token_urlsafe(32))

# Check if Discord integration is enabled
DISCORD_ENABLED = all([CLIENT_ID, CLIENT_SECRET, GUILD_ID, BOT_TOKEN, CHANNEL_ID])

# === PYDANTIC MODELS ===
class OCRRequest(BaseModel):
    image_data: str  # Base64 encoded image
    threshold: float = 0.6  # Matching threshold
    enable_features: bool = True  # Enable feature-based matching

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

@app.post("/api/ocr")
async def perform_ocr(request: OCRRequest):
    """
    Memory-optimized image matching for server deployment
    """
    try:
        print(f"OCR request received. Threshold: {request.threshold}, Features: {request.enable_features}")
        
        # Check if image data is reasonable size
        image_data_size = len(request.image_data)
        if image_data_size > 10_000_000:  # 10MB limit
            print(f"Image too large: {image_data_size} bytes")
            raise HTTPException(status_code=400, detail="Image too large (max 10MB)")
        
        # Decode base64 image
        try:
            image_data = base64.b64decode(request.image_data.split(',')[1] if ',' in request.image_data else request.image_data)
            print(f"Image data decoded, size: {len(image_data)} bytes")
        except Exception as e:
            print(f"Error decoding image: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid image data: {str(e)}")
        
        # Convert to PIL Image
        try:
            pasted_image = Image.open(io.BytesIO(image_data))
            print(f"PIL image created, size: {pasted_image.size}, mode: {pasted_image.mode}")
            
            # Limit image dimensions to prevent memory issues
            max_dimension = 500
            if max(pasted_image.size) > max_dimension:
                ratio = max_dimension / max(pasted_image.size)
                new_size = tuple(int(dim * ratio) for dim in pasted_image.size)
                pasted_image = pasted_image.resize(new_size, Image.Resampling.LANCZOS)
                print(f"Image resized to: {pasted_image.size}")
                
        except Exception as e:
            print(f"Error creating PIL image: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")
        
        # Convert to RGB if necessary
        if pasted_image.mode != 'RGB':
            pasted_image = pasted_image.convert('RGB')
            print("Converted image to RGB")
        
        # Convert to numpy array for OpenCV
        try:
            pasted_array = np.array(pasted_image)
            print(f"Numpy array created, shape: {pasted_array.shape}")
        except Exception as e:
            print(f"Error converting to numpy array: {e}")
            raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")
        
        # Load the main map image
        map_image_path = "ggmap.png"
        if not os.path.exists(map_image_path):
            print(f"Map image not found at: {map_image_path}")
            raise HTTPException(status_code=404, detail="Map image not found")
        
        try:
            map_image = cv2.imread(map_image_path)
            if map_image is None:
                print("Failed to load map image with cv2.imread")
                raise HTTPException(status_code=500, detail="Failed to load map image")
            
            # Convert BGR to RGB for consistency
            map_image = cv2.cvtColor(map_image, cv2.COLOR_BGR2RGB)
            print(f"Map image loaded, shape: {map_image.shape}")
        except Exception as e:
            print(f"Error loading map image: {e}")
            raise HTTPException(status_code=500, detail=f"Error loading map image: {str(e)}")
        
        # Perform template matching with timeout protection
        try:
            print("Starting memory-optimized template matching...")
            matches = find_image_matches(pasted_array, map_image, 
                                       threshold=0.1,  # Always use low threshold, return best matches
                                       enable_features=request.enable_features)
            print(f"Template matching completed, found {len(matches)} matches")
        except Exception as e:
            print(f"Error in template matching: {e}")
            import traceback
            traceback.print_exc()
            # Return partial results if available
            matches = []
            raise HTTPException(status_code=500, detail=f"Template matching failed: {str(e)}")
        
        return JSONResponse({
            "success": True,
            "matches": matches,
            "message": f"Found {len(matches)} potential matches (showing best candidates)"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error in OCR: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "matches": []
        }, status_code=500)

def find_image_matches(template, map_image, threshold=0.6, enable_features=True):
    """
    Ultra-memory-efficient matching for very low memory servers
    """
    matches = []
    
    try:
        print("Starting ultra-memory-efficient template matching...")
        
        # Convert to grayscale for template matching
        template_gray = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)
        map_gray = cv2.cvtColor(map_image, cv2.COLOR_RGB2GRAY)
        
        # Get template dimensions
        template_h, template_w = template_gray.shape
        map_h, map_w = map_gray.shape
        
        print(f"Template size: {template_w}x{template_h}, Map size: {map_w}x{map_h}")
        
        # Skip if template is too small
        if template_w < 10 or template_h < 10:
            print("Template too small for matching")
            return matches
        
        # VERY aggressive downsampling for ultra-low memory
        # Target: keep everything under 5MB
        target_pixels = 1_000_000  # 1 million pixels max
        current_pixels = map_w * map_h
        
        downsample_factor = max(4.0, (current_pixels / target_pixels) ** 0.5)
        downsample_factor = min(downsample_factor, 8.0)  # Cap at 8x
        
        print(f"Using aggressive downsample factor: {downsample_factor:.2f}")
        
        # Downsample to tiny sizes
        new_map_w = max(200, int(map_w / downsample_factor))
        new_map_h = max(150, int(map_h / downsample_factor))
        new_template_w = max(10, int(template_w / downsample_factor))
        new_template_h = max(10, int(template_h / downsample_factor))
        
        print(f"Tiny map size: {new_map_w}x{new_map_h}")
        print(f"Tiny template size: {new_template_w}x{new_template_h}")
        
        # Create tiny versions
        map_tiny = cv2.resize(map_gray, (new_map_w, new_map_h), interpolation=cv2.INTER_AREA)
        template_tiny = cv2.resize(template_gray, (new_template_w, new_template_h), interpolation=cv2.INTER_AREA)
        
        # Simple enhancement (avoid memory-intensive operations)
        map_tiny = cv2.GaussianBlur(map_tiny, (3, 3), 0)
        template_tiny = cv2.GaussianBlur(template_tiny, (3, 3), 0)
        
        # Use only 2-3 scales to minimize memory
        scales = [0.9, 1.0, 1.1]
        print(f"Using minimal scales: {scales}")
        
        all_matches = []
        
        for scale in scales:
            print(f"Processing scale {scale}")
            
            if scale != 1.0:
                scaled_w = max(8, int(new_template_w * scale))
                scaled_h = max(8, int(new_template_h * scale))
                
                if scaled_w >= new_map_w * 0.8 or scaled_h >= new_map_h * 0.8:
                    continue
                
                scaled_template = cv2.resize(template_tiny, (scaled_w, scaled_h))
            else:
                scaled_template = template_tiny
                scaled_w, scaled_h = new_template_w, new_template_h
            
            try:
                # Single template matching operation
                result = cv2.matchTemplate(map_tiny, scaled_template, cv2.TM_CCOEFF_NORMED)
                
                # Get only top 5 matches per scale
                result_flat = result.flatten()
                if len(result_flat) > 0:
                    top_indices = np.argpartition(result_flat, -5)[-5:]
                    
                    for idx in top_indices:
                        confidence = result_flat[idx]
                        if confidence > 0.05:  # Ultra-low threshold
                            y_coord, x_coord = np.unravel_index(idx, result.shape)
                            
                            # Scale back to original coordinates
                            orig_x = int((x_coord + scaled_w // 2) * downsample_factor)
                            orig_y = int((y_coord + scaled_h // 2) * downsample_factor)
                            orig_w = int(scaled_w * downsample_factor)
                            orig_h = int(scaled_h * downsample_factor)
                            
                            all_matches.append({
                                "x": orig_x,
                                "y": orig_y,
                                "confidence": float(confidence),
                                "width": orig_w,
                                "height": orig_h,
                                "scale": float(scale)
                            })
                
                del result  # Immediate cleanup
                
            except Exception as e:
                print(f"Error at scale {scale}: {e}")
                continue
        
        print(f"Found {len(all_matches)} potential matches")
        
        # Sort and take best matches
        all_matches.sort(key=lambda x: x["confidence"], reverse=True)
        
        # Convert to final format (no verification to save memory)
        for match in all_matches[:10]:  # Limit to top 10
            try:
                leaflet_lat = 6144 - match["y"]
                leaflet_lng = match["x"]
                
                if 0 <= leaflet_lng <= 10752 and 0 <= leaflet_lat <= 6144:
                    matches.append({
                        "x": match["x"],
                        "y": match["y"],
                        "lat": float(leaflet_lat),
                        "lng": float(leaflet_lng),
                        "confidence": match["confidence"],
                        "width": match["width"],
                        "height": match["height"],
                        "scale": match["scale"],
                        "method": "ULTRA_MEMORY_EFFICIENT"
                    })
            except Exception as e:
                print(f"Error converting match: {e}")
                continue
        
        print(f"Ultra-efficient matching completed, found {len(matches)} matches")
        
        # Skip feature matching to save memory
        if enable_features and len(matches) < 2 and template_w < 100 and template_h < 100:
            print("Adding minimal feature matching...")
            try:
                # Use extremely small images for features
                feature_map = cv2.resize(map_gray, (map_w // 8, map_h // 8))
                feature_template = cv2.resize(template_gray, (template_w // 4, template_h // 4))
                
                feature_matches = find_feature_matches_minimal(feature_template, feature_map)
                
                # Scale back up
                for match in feature_matches:
                    match["x"] *= 8
                    match["y"] *= 8
                    match["lat"] = 6144 - match["y"]
                    match["lng"] = match["x"]
                    match["width"] *= 4
                    match["height"] *= 4
                
                matches.extend(feature_matches)
                print(f"Minimal feature matching added {len(feature_matches)} matches")
            except Exception as e:
                print(f"Feature matching failed: {e}")
        
        # Simple duplicate removal
        if len(matches) > 1:
            filtered_matches = []
            for match in matches:
                is_duplicate = False
                for existing in filtered_matches:
                    dist = ((match["x"] - existing["x"]) ** 2 + (match["y"] - existing["y"]) ** 2) ** 0.5
                    if dist < 100:
                        if match["confidence"] > existing["confidence"]:
                            filtered_matches.remove(existing)
                            break
                        else:
                            is_duplicate = True
                            break
                if not is_duplicate:
                    filtered_matches.append(match)
            matches = filtered_matches
        
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        matches = matches[:8]  # Strict limit
        
        print(f"Final result: {len(matches)} matches")
        if matches:
            print(f"Best confidence: {matches[0]['confidence']:.3f}")
        
    except Exception as e:
        print(f"Template matching error: {str(e)}")
        import traceback
        traceback.print_exc()
        
    return matches

def find_feature_matches_minimal(template, map_image):
    """
    Extremely minimal feature matching for ultra-low memory
    """
    matches = []
    
    try:
        # Use very few features
        orb = cv2.ORB_create(nfeatures=100)
        
        kp1, des1 = orb.detectAndCompute(template, None)
        kp2, des2 = orb.detectAndCompute(map_image, None)
        
        if des1 is None or des2 is None or len(kp1) < 4:
            return matches
        
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        orb_matches = bf.match(des1, des2)
        
        if len(orb_matches) < 4:
            return matches
        
        # Take only top 10 matches
        orb_matches = sorted(orb_matches, key=lambda x: x.distance)[:10]
        
        src_pts = np.float32([kp1[m.queryIdx].pt for m in orb_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in orb_matches]).reshape(-1, 1, 2)
        
        if len(src_pts) >= 4:
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 2.0)
            
            if M is not None and mask is not None:
                h, w = template.shape
                corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
                transformed_corners = cv2.perspectiveTransform(corners, M)
                
                center_x = np.mean(transformed_corners[:, 0, 0])
                center_y = np.mean(transformed_corners[:, 0, 1])
                
                inliers = np.sum(mask)
                confidence = min(0.8, inliers / len(orb_matches))
                
                if confidence > 0.2:
                    matches.append({
                        "x": int(center_x),
                        "y": int(center_y),
                        "lat": 0,  # Will be calculated later
                        "lng": 0,  # Will be calculated later
                        "confidence": float(confidence),
                        "width": w,
                        "height": h,
                        "scale": 1.0,
                        "method": "MINIMAL_ORB"
                    })
        
    except Exception as e:
        print(f"Minimal feature matching error: {e}")
    
    return matches

def find_feature_matches_optimized(template, map_image):
    """
    Optimized feature-based matching using ORB
    """
    matches = []
    
    try:
        # Initialize ORB detector with moderate features for balance
        orb = cv2.ORB_create(nfeatures=400)
        
        # Find keypoints and descriptors
        kp1, des1 = orb.detectAndCompute(template, None)
        kp2, des2 = orb.detectAndCompute(map_image, None)
        
        if des1 is None or des2 is None or len(kp1) < 8:
            print("Insufficient features for ORB matching")
            return matches
        
        # Create BFMatcher object
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        
        # Match descriptors
        orb_matches = bf.match(des1, des2)
        
        if len(orb_matches) < 8:
            print("Insufficient ORB matches found")
            return matches
        
        # Sort matches by distance and take top matches
        orb_matches = sorted(orb_matches, key=lambda x: x.distance)[:25]
        
        # Extract coordinates
        src_pts = np.float32([kp1[m.queryIdx].pt for m in orb_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in orb_matches]).reshape(-1, 1, 2)
        
        # Find homography to locate the template in the map
        if len(src_pts) >= 4:
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 4.0)
            
            if M is not None and mask is not None:
                # Get template corners
                h, w = template.shape
                corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
                
                # Transform corners to map coordinates
                transformed_corners = cv2.perspectiveTransform(corners, M)
                
                # Calculate center and confidence
                center_x = np.mean(transformed_corners[:, 0, 0])
                center_y = np.mean(transformed_corners[:, 0, 1])
                
                # Calculate confidence based on inlier ratio
                inliers = np.sum(mask)
                confidence = min(0.92, inliers / len(orb_matches))
                
                if confidence > 0.25:  # Lower threshold for better recall
                    leaflet_lat = 6144 - center_y
                    leaflet_lng = center_x
                    
                    # Validate coordinates
                    if 0 <= leaflet_lng <= 10752 and 0 <= leaflet_lat <= 6144:
                        matches.append({
                            "x": int(center_x),
                            "y": int(center_y),
                            "lat": float(leaflet_lat),
                            "lng": float(leaflet_lng),
                            "confidence": float(confidence),
                            "width": w,
                            "height": h,
                            "scale": 1.0,
                            "method": "ORB_FEATURES"
                        })
                        
                        print(f"ORB feature match found with {inliers} inliers, confidence: {confidence:.3f}")
        
    except Exception as e:
        print(f"Feature matching error: {e}")
    
    return matches

def enhance_image_features(image):
    """
    Enhance image features for better template matching
    """
    try:
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(image, (3, 3), 0)
        
        # Apply Contrast Limited Adaptive Histogram Equalization (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)
        
        return enhanced
        
    except Exception as e:
        print(f"Error enhancing image: {e}")
        return image

def verify_match_quality(map_image, template, x, y, w, h):
    """
    Verify match quality using additional metrics
    """
    try:
        # Extract the matched region
        if x + w > map_image.shape[1] or y + h > map_image.shape[0]:
            return False
            
        matched_region = map_image[y:y+h, x:x+w]
        
        if matched_region.shape != template.shape:
            return False
        
        # Calculate structural similarity
        # Simple correlation coefficient check
        correlation = cv2.matchTemplate(matched_region, template, cv2.TM_CCOEFF_NORMED)
        
        # If correlation is high enough, it's a good match
        return correlation[0][0] > 0.5
        
    except Exception as e:
        print(f"Error verifying match: {e}")
        return True  # Default to accepting the match

def remove_duplicate_matches(matches, min_distance=30):
    """
    Remove matches that are too close to each other, keeping the one with higher confidence
    """
    if not matches:
        return matches
    
    # Sort by confidence first
    sorted_matches = sorted(matches, key=lambda x: x["confidence"], reverse=True)
    filtered_matches = []
    
    for match in sorted_matches:
        # Check if this match is too close to any already accepted match
        is_duplicate = False
        for accepted_match in filtered_matches:
            distance = np.sqrt((match["x"] - accepted_match["x"])**2 + (match["y"] - accepted_match["y"])**2)
            if distance < min_distance:
                # If it's the same method and very close, it's definitely a duplicate
                if match.get("method") == accepted_match.get("method") and distance < min_distance * 0.5:
                    is_duplicate = True
                    break
                # If different methods but very close and similar confidence, prefer feature-based
                elif distance < min_distance:
                    if match.get("method") == "ORB_FEATURES" and accepted_match.get("method") != "ORB_FEATURES":
                        # Replace the existing match with the feature-based one
                        filtered_matches.remove(accepted_match)
                        break
                    else:
                        is_duplicate = True
                        break
        
        if not is_duplicate:
            filtered_matches.append(match)
    
    return filtered_matches

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
    config = uvicorn.Config(app, host="0.0.0.0", port=8888, log_level="info")
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
