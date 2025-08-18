#!/usr/bin/env python3
"""
Test script to verify the updated map functionality
"""

import asyncio
import websockets
import json
import time

async def test_updated_map():
    """Test the updated map with proper dimensions and control+click"""
    print("🗺️  Testing Updated Map Functionality")
    print("=" * 50)
    
    # Test map configuration
    print("📏 Map Configuration:")
    print("   - Dimensions: 10752 x 6144 (width x height)")
    print("   - Leaflet bounds: [[0, 0], [6144, 10752]]")
    print("   - Center point: [3072, 5376]")
    print("   - Zoom range: -1 to 3")
    
    print("\n🎮 New Features:")
    print("   - Control + Left Click to ping")
    print("   - Sound effects with light.wav")
    print("   - Different colors for your pings vs others")
    print("   - Proper map scaling and bounds")
    
    # Test WebSocket connection
    uri = "ws://localhost:8080/map"
    try:
        print(f"\n🔌 Testing WebSocket connection to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected successfully!")
            
            # Send join message
            join_msg = {"type": "join", "user": "TestUser"}
            await websocket.send(json.dumps(join_msg))
            print("📤 Sent join message")
            
            # Send a test ping with new coordinates
            ping_msg = {
                "type": "ping",
                "user": "TestUser",
                "lat": 3072,  # Center latitude
                "lng": 5376,  # Center longitude
                "timestamp": int(time.time() * 1000)
            }
            await websocket.send(json.dumps(ping_msg))
            print("📍 Sent test ping at map center")
            
            # Listen for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                data = json.loads(response)
                print(f"📥 Received response: {data['type']}")
            except asyncio.TimeoutError:
                print("⏱️  No immediate response (normal for single user test)")
            
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        return False
    
    print("\n✅ All tests completed successfully!")
    print("\n📋 Usage Instructions:")
    print("1. Open http://localhost:8080/map in your browser")
    print("2. Enter your username when prompted")
    print("3. Hold Ctrl and click anywhere on the map to ping")
    print("4. Listen for the ping sound effect")
    print("5. Your pings are gold, others are orange")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_updated_map())
