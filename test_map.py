#!/usr/bin/env python3
"""
Test the GG Guild Map setup
"""

import asyncio
import websockets
import json
import time

async def test_map_connection():
    """Test connection to the map WebSocket endpoint"""
    uri = "ws://45.79.137.244:8888/map"
    
    try:
        print("🔌 Attempting to connect to map server...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to map server!")
            
            # Send join message
            join_msg = {
                "type": "join",
                "user": "TestUser"
            }
            await websocket.send(json.dumps(join_msg))
            print("📤 Sent join message")
            
            # Send a test ping
            ping_msg = {
                "type": "ping",
                "user": "TestUser",
                "lat": 500,
                "lng": 500,
                "timestamp": int(time.time() * 1000)
            }
            await websocket.send(json.dumps(ping_msg))
            print("📍 Sent test ping")
            
            # Listen for responses
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(response)
                print(f"📥 Received: {data}")
            except asyncio.TimeoutError:
                print("⏱️  No response received (timeout)")
            
            print("✅ Map connection test completed successfully!")
            
    except Exception as e:
        print(f"❌ Failed to connect to map server: {e}")
        print("💡 Make sure your server is running on 45.79.137.244:8888")

def test_local_files():
    """Test if local files are properly set up"""
    import os
    
    print("\n📁 Checking local files...")
    
    files_to_check = [
        ("server.py", "Main server file"),
        ("map_client.html", "Map client interface"),
        ("ggmap.png", "Game map image")
    ]
    
    all_good = True
    for filename, description in files_to_check:
        if os.path.exists(filename):
            print(f"✅ {filename} - {description}")
        else:
            print(f"❌ {filename} - {description} (MISSING)")
            all_good = False
    
    if all_good:
        print("✅ All required files are present!")
    else:
        print("❌ Some files are missing. Run setup_map.py for help.")
    
    return all_good

if __name__ == "__main__":
    print("🧪 GG Guild Map Test Suite")
    print("=" * 40)
    
    # Test local files first
    if test_local_files():
        print("\n🌐 Testing server connection...")
        asyncio.run(test_map_connection())
    else:
        print("\n⚠️  Skipping server test due to missing files")
    
    print("\n🎯 Test Summary:")
    print("- If all tests pass, your map should be accessible at:")
    print("  http://45.79.137.244:8888/map")
    print("- Share this URL with your guild members!")
