#!/usr/bin/env python3
"""
Create a simple ping sound file (light.wav) using Python
"""

try:
    import numpy as np
    import wave
    import struct
    
    def create_ping_sound():
        # Audio parameters
        sample_rate = 44100  # Sample rate in Hz
        duration = 0.3       # Duration in seconds
        frequency = 800      # Frequency in Hz
        
        # Generate time array
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        
        # Generate a simple tone with fade out
        fade_samples = int(0.1 * sample_rate)  # 0.1 second fade
        tone = np.sin(2 * np.pi * frequency * t)
        
        # Apply fade out
        for i in range(fade_samples):
            fade_factor = 1.0 - (i / fade_samples)
            if len(tone) - fade_samples + i < len(tone):
                tone[len(tone) - fade_samples + i] *= fade_factor
        
        # Convert to 16-bit integers
        tone = (tone * 32767).astype(np.int16)
        
        # Write to WAV file
        with wave.open('light.wav', 'w') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(tone.tobytes())
        
        print("✅ Created light.wav - Simple ping sound file")
        return True
        
    if __name__ == "__main__":
        import os
        if os.path.exists("light.wav"):
            print("ℹ️  light.wav already exists. Skipping creation.")
        else:
            create_ping_sound()
            
except ImportError:
    print("📦 NumPy not available. Creating placeholder instruction file...")
    
    with open("SOUND_SETUP.txt", "w", encoding="utf-8") as f:
        f.write("""Sound File Setup - light.wav
=============================

You need to provide a light.wav file for the ping sound effect.

Options:
1. Create/find a light.wav file (short ping/notification sound)
2. Place it in this directory: """ + os.getcwd() + """
3. The sound should be brief (0.1-0.5 seconds) for best effect

Recommended audio format:
- WAV format
- 16-bit, 44.1kHz
- Mono or stereo
- Duration: 0.1-0.5 seconds

You can:
- Record a simple "ping" or "ding" sound
- Download a free notification sound
- Use any short audio editing tool

The map will work without the sound file, but pings will be silent.
""")
    
    print("📄 Created SOUND_SETUP.txt with instructions")
    print("💡 Install numpy with: pip install numpy (to auto-generate sound)")
    
except Exception as e:
    print(f"❌ Error creating sound file: {e}")
    print("💡 You can manually create or find a light.wav file")
