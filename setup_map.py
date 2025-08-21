#!/usr/bin/env python3
"""
GG Guild Map Setup Script
This script helps you set up the map files and configuration.
"""

import os
import shutil
from pathlib import Path

def setup_map():
    print("🗺️  GG Guild Map Setup")
    print("=" * 40)
    
    # Check if ggmap.png exists
    if not os.path.exists("ggmap.png"):
        print("❌ ggmap.png not found in current directory")
        print("📋 Please copy your ggmap.png file to this directory:")
        print(f"   {os.getcwd()}")
        print("\n💡 You mentioned it's located at /root/maps/ggmap.png on your server")
        print("   You'll need to transfer it to this location for the map to work.")
        
        # Create a placeholder
        print("\n📄 Creating placeholder instructions file...")
        with open("MAP_SETUP_INSTRUCTIONS.txt", "w", encoding="utf-8") as f:
            f.write("""GG Guild Map Setup Instructions
================================

1. Copy your game map image (ggmap.png) to this directory:
   """ + os.getcwd() + """

2. The map image should be named exactly: ggmap.png

3. Start your server with:
   python server.py

4. Access the map at:
   http://45.79.137.244:8888/map

5. To add more layers or points of interest, edit the map_client.html file
   and modify the samplePOIs array and layerConfig object.

Current server setup:
- Server URL: 45.79.137.244:8888
- Map endpoint: /map
- WebSocket endpoint: /map (for real-time pings)

Layer configuration:
- Dockmasters (blue anchor)
- GG Runes (green stone) 
- Witcher Runes (orange lightning)
- Resources (purple gem)
- Dungeons (red castle)
""")
        print("✅ Created MAP_SETUP_INSTRUCTIONS.txt")
    else:
        print("✅ ggmap.png found!")
        
        # Check image size
        try:
            from PIL import Image
            with Image.open("ggmap.png") as img:
                width, height = img.size
                print(f"📐 Image dimensions: {width}x{height}")
                
                # Update the map bounds in the HTML file if needed
                if os.path.exists("map_client.html"):
                    print("🔧 You may need to adjust the map bounds in map_client.html")
                    print(f"   Current bounds are set to [[0, 0], [1000, 1000]]")
                    print(f"   Consider changing to [[0, 0], [{height}, {width}]] for proper scaling")
        except ImportError:
            print("📦 Install Pillow (pip install Pillow) to check image dimensions")
        except Exception as e:
            print(f"⚠️  Could not analyze image: {e}")
    
    # Check if server files are ready
    if os.path.exists("server.py"):
        print("✅ server.py found!")
    else:
        print("❌ server.py not found")
    
    if os.path.exists("map_client.html"):
        print("✅ map_client.html found!")
    else:
        print("❌ map_client.html not found")
    
    print("\n🚀 Setup Status:")
    print("1. Copy ggmap.png to this directory")
    print("2. Run: python server.py")
    print("3. Navigate to: http://45.79.137.244:8888/map")
    print("4. Share the URL with your guild members!")
    
    print("\n🎮 Map Features:")
    print("- Real-time location pinging")
    print("- Multiple selectable layers (Dockmasters, Runes, etc.)")
    print("- Online user list")
    print("- Custom points of interest")
    
    return True

if __name__ == "__main__":
    setup_map()
