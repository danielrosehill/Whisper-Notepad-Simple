#!/usr/bin/env python3
"""
Simple script to create an icon for Whisper Notepad Simple
This creates a basic icon.ico file that can be used by PyInstaller
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # Create a list of sizes for the icon (Windows typically uses these sizes)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Create a base image with transparency
    base_size = max(sizes)
    base_img = Image.new('RGBA', base_size, color=(0, 0, 0, 0))
    
    # Create a drawing context
    draw = ImageDraw.Draw(base_img)
    
    # Draw a rounded rectangle for the notepad
    padding = base_size[0] // 10
    width, height = base_size[0] - 2*padding, base_size[1] - 2*padding
    rect_coords = [(padding, padding), (base_size[0] - padding, base_size[1] - padding)]
    draw.rounded_rectangle(rect_coords, fill=(255, 255, 255), outline=(70, 70, 70), width=3, radius=15)
    
    # Draw some lines to represent text
    line_padding = width // 5
    line_height = height // 8
    line_start = padding + line_padding
    line_width = width - 2*line_padding
    
    # Draw 4 lines of "text"
    for i in range(4):
        y_pos = padding + line_height*2 + i*line_height*1.5
        draw.line([(line_start, y_pos), (line_start + line_width, y_pos)], fill=(70, 70, 70), width=3)
    
    # Draw a microphone icon at the top
    mic_radius = width // 8
    mic_x, mic_y = base_size[0] // 2, padding + line_height
    draw.ellipse([(mic_x - mic_radius, mic_y - mic_radius), 
                  (mic_x + mic_radius, mic_y + mic_radius)], 
                 fill=(52, 152, 219))
    
    # Resize for all the required sizes
    images = []
    for size in sizes:
        images.append(base_img.resize(size, Image.LANCZOS))
    
    # Save as ICO file
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    images[0].save(icon_path, format='ICO', sizes=sizes, append_images=images[1:])
    print(f"Icon created at {icon_path}")

if __name__ == "__main__":
    try:
        create_icon()
    except Exception as e:
        print(f"Error creating icon: {e}")
        print("You may need to install Pillow: pip install pillow")
