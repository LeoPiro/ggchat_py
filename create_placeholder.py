#!/usr/bin/env python3
"""
Create a placeholder map image for testing
"""

try:
    from PIL import Image, ImageDraw, ImageFont
    import os
    
    def create_placeholder_map():
        # Create a 1000x1000 image with a dark green background
        width, height = 1000, 1000
        img = Image.new('RGB', (width, height), color='#2d4a2d')
        draw = ImageDraw.Draw(img)
        
        # Draw a simple grid
        grid_size = 100
        for x in range(0, width, grid_size):
            draw.line([(x, 0), (x, height)], fill='#3d5a3d', width=1)
        for y in range(0, height, grid_size):
            draw.line([(0, y), (width, y)], fill='#3d5a3d', width=1)
        
        # Draw some water areas (blue rectangles)
        water_areas = [
            (50, 50, 250, 150),    # Top left lake
            (300, 200, 500, 300),  # Central river
            (700, 600, 950, 800),  # Bottom right sea
        ]
        
        for area in water_areas:
            draw.rectangle(area, fill='#1565c0')
        
        # Draw some land features (brown rectangles for mountains)
        mountain_areas = [
            (600, 100, 800, 300),  # North mountains
            (100, 400, 300, 600),  # West mountains
            (400, 700, 600, 900),  # South mountains
        ]
        
        for area in mountain_areas:
            draw.rectangle(area, fill='#5d4037')
        
        # Add some text labels
        try:
            # Try to use a larger font if available
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            # Fall back to default font
            font = ImageFont.load_default()
        
        # Label areas
        labels = [
            (150, 100, "Northern Lake", 'white'),
            (400, 250, "Great River", 'white'),
            (825, 700, "Eastern Sea", 'white'),
            (700, 200, "Dragon Mountains", 'yellow'),
            (200, 500, "Iron Hills", 'yellow'),
            (500, 800, "Shadow Peaks", 'yellow'),
            (500, 500, "PLACEHOLDER MAP", 'red'),
            (450, 530, "Replace with ggmap.png", 'red'),
        ]
        
        for x, y, text, color in labels:
            # Draw text with a black outline for better visibility
            for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                draw.text((x+dx, y+dy), text, fill='black', font=font)
            draw.text((x, y), text, fill=color, font=font)
        
        # Save the image
        img.save('ggmap.png')
        print("✅ Created placeholder ggmap.png (1000x1000)")
        print("🔄 Replace this with your actual game map when ready")
        
        return True
        
    if __name__ == "__main__":
        if os.path.exists("ggmap.png"):
            print("ℹ️  ggmap.png already exists. Skipping placeholder creation.")
        else:
            create_placeholder_map()
            
except ImportError:
    print("📦 PIL (Pillow) not installed. Creating simple placeholder...")
    print("💡 Run: pip install Pillow")
    print("📄 Or manually create/copy ggmap.png to this directory")
    
    # Create a simple text file instead
    with open("ggmap_placeholder.txt", "w") as f:
        f.write("""PLACEHOLDER FOR GGMAP.PNG
==========================

This is where your game map image should go.

Instructions:
1. Transfer ggmap.png from /root/maps/ggmap.png on your server
2. Place it in this directory: """ + os.getcwd() + """
3. The file should be named exactly: ggmap.png
4. Recommended size: 1000x1000 pixels or larger

Once you have the real map image, delete this placeholder file.
""")
