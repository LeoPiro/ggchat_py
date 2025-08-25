#!/usr/bin/env python3
"""
Standalone webview launcher for GG Map
This script is used by the compiled executable to open the map in a separate process
"""
import sys
import os
import webview

def main():
    if len(sys.argv) < 3:
        print("Usage: webview_launcher.py <url> <username>")
        sys.exit(1)
    
    url = sys.argv[1]
    username = sys.argv[2]
    
    try:
        # Set environment variables for HTTP support
        os.environ['WEBVIEW_ALLOW_HTTP'] = '1'
        os.environ['WEBVIEW_DISABLE_SECURITY'] = '1'
        os.environ['WEBVIEW_PRIVATE_MODE'] = '0'
        os.environ['WEBVIEW_INCOGNITO'] = '0'
        
        # Create and start webview window
        webview.create_window(
            title=f"GG Map - {username}",
            url=url,
            width=1200,
            height=800,
            resizable=True,
            on_top=False
        )
        
        # Try different GUI backends
        try:
            webview.start(debug=False, gui="edgechromium", private_mode=False)
        except Exception as e1:
            try:
                webview.start(debug=False, gui="edgehtml", private_mode=False)
            except Exception as e2:
                try:
                    webview.start(debug=False, gui="cef", private_mode=False)
                except Exception as e3:
                    webview.start(debug=False, private_mode=False)
                    
    except Exception as e:
        print(f"Webview initialization failed: {e}")
        # Fallback to browser
        import webbrowser
        webbrowser.open(url)

if __name__ == "__main__":
    main()
