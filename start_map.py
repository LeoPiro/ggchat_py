#!/usr/bin/env python3
"""
GG Guild Map Server Launcher
Starts the map server with proper configuration
"""

import os
import sys
import asyncio
import subprocess

def check_requirements():
    """Check if all requirements are met"""
    requirements = {
        'ggmap.png': 'Map image file',
        'server.py': 'Main server script',
        'map_client.html': 'Map client interface'
    }
    
    missing = []
    for file, desc in requirements.items():
        if not os.path.exists(file):
            missing.append(f"{file} ({desc})")
    
    if missing:
        print("❌ Missing required files:")
        for item in missing:
            print(f"   - {item}")
        return False
    return True

def check_environment():
    """Check if environment variables are set"""
    required_env = [
        'DISCORD_CLIENT_ID',
        'DISCORD_CLIENT_SECRET', 
        'DISCORD_GUILD_ID',
        'DISCORD_CHANNEL_ID',
        'DISCORD_BOT_TOKEN'
    ]
    
    missing_env = []
    for env_var in required_env:
        if not os.environ.get(env_var):
            missing_env.append(env_var)
    
    if missing_env:
        print("⚠️  Missing environment variables (needed for Discord integration):")
        for env_var in missing_env:
            print(f"   - {env_var}")
        print("\n💡 The map will still work for basic functionality,")
        print("   but Discord integration won't be available.")
        
        response = input("\n🤔 Continue anyway? (y/N): ").lower()
        if response != 'y':
            return False
    
    return True

def start_server():
    """Start the map server"""
    print("🚀 Starting GG Guild Map Server...")
    print("📍 Server will be available at: http://45.79.137.244:8888/map")
    print("🔗 Direct map access: http://45.79.137.244:8888/map")
    print("💬 Chat integration: http://45.79.137.244:8888/")
    print("\n⚡ Starting server... (Press Ctrl+C to stop)")
    
    try:
        # Import and run the server
        import server
        asyncio.run(server.main())
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        print("💡 Check your configuration and try again")

def main():
    print("🗺️  GG Guild Map Server Launcher")
    print("=" * 40)
    
    # Check files
    if not check_requirements():
        print("\n🔧 Run setup_map.py to fix missing files")
        return
    
    print("✅ All required files found!")
    
    # Check environment (optional for map functionality)
    check_environment()
    
    print("\n" + "=" * 40)
    start_server()

if __name__ == "__main__":
    main()
