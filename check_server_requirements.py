#!/usr/bin/env python3
"""
Check server requirements and suggest optimizations for OCR functionality
"""

import psutil
import cv2
import numpy as np
from PIL import Image

def check_system_requirements():
    """Check if the system meets requirements for OCR processing"""
    
    print("=== Server Requirements Check ===")
    
    # Check available memory
    memory = psutil.virtual_memory()
    print(f"Total RAM: {memory.total / 1024**3:.1f} GB")
    print(f"Available RAM: {memory.available / 1024**3:.1f} GB")
    print(f"Memory usage: {memory.percent}%")
    
    # Check if we have enough memory for large image processing
    if memory.available < 2 * 1024**3:  # Less than 2GB available
        print("⚠️  WARNING: Low memory detected!")
        print("   Recommended: At least 2GB available RAM")
        print("   Current: {:.1f}GB available".format(memory.available / 1024**3))
        return False
    
    # Test OpenCV functionality
    try:
        test_img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        gray = cv2.cvtColor(test_img, cv2.COLOR_RGB2GRAY)
        result = cv2.matchTemplate(gray[:50, :50], gray[25:75, 25:75], cv2.TM_CCOEFF_NORMED)
        print("✅ OpenCV template matching: OK")
    except Exception as e:
        print(f"❌ OpenCV test failed: {e}")
        return False
    
    # Test ORB features
    try:
        orb = cv2.ORB_create(nfeatures=100)
        kp, des = orb.detectAndCompute(gray, None)
        print("✅ ORB feature detection: OK")
    except Exception as e:
        print(f"❌ ORB test failed: {e}")
        return False
    
    print("✅ All requirements met!")
    return True

def suggest_optimizations():
    """Suggest optimizations based on system specs"""
    
    memory = psutil.virtual_memory()
    available_gb = memory.available / 1024**3
    
    print("\n=== Optimization Suggestions ===")
    
    if available_gb < 1:
        print("💡 Very low memory - consider these settings:")
        print("   - Max image dimension: 200px")
        print("   - Disable feature matching")
        print("   - Use only 2 scales: [0.75, 1.0]")
        print("   - Max matches per scale: 3")
        
    elif available_gb < 2:
        print("💡 Low memory - recommended settings:")
        print("   - Max image dimension: 300px")
        print("   - Limit feature matching")
        print("   - Use 3 scales: [0.75, 1.0, 1.25]")
        print("   - Max matches per scale: 5")
        
    elif available_gb < 4:
        print("💡 Moderate memory - current settings should work:")
        print("   - Max image dimension: 500px")
        print("   - Feature matching enabled")
        print("   - Use 3 scales: [0.75, 1.0, 1.25]")
        print("   - Max matches per scale: 5")
        
    else:
        print("💡 Good memory - can use higher quality settings:")
        print("   - Max image dimension: 800px")
        print("   - Full feature matching enabled")
        print("   - Use 5 scales: [0.5, 0.75, 1.0, 1.25, 1.5]")
        print("   - Max matches per scale: 10")

def test_image_processing():
    """Test actual image processing with a sample"""
    
    print("\n=== Image Processing Test ===")
    
    try:
        # Create a test image similar to what might be uploaded
        test_size = (200, 200, 3)
        test_img = np.random.randint(0, 255, test_size, dtype=np.uint8)
        
        # Add some pattern to make matching meaningful
        cv2.rectangle(test_img, (50, 50), (150, 150), (255, 255, 255), -1)
        cv2.circle(test_img, (100, 100), 30, (0, 0, 0), -1)
        
        print(f"Test image created: {test_img.shape}")
        
        # Test conversion to grayscale
        gray = cv2.cvtColor(test_img, cv2.COLOR_RGB2GRAY)
        print("✅ RGB to grayscale conversion: OK")
        
        # Test template matching on a subset
        template = gray[75:125, 75:125]
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= 0.8)
        print(f"✅ Template matching test: Found {len(locations[0])} matches")
        
        # Test memory usage during processing
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024**2
        print(f"✅ Memory usage during test: {memory_mb:.1f} MB")
        
        if memory_mb > 500:
            print("⚠️  High memory usage detected during test")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Image processing test failed: {e}")
        return False

if __name__ == "__main__":
    requirements_ok = check_system_requirements()
    processing_ok = test_image_processing()
    suggest_optimizations()
    
    print(f"\n=== Final Assessment ===")
    if requirements_ok and processing_ok:
        print("🎉 System ready for OCR functionality!")
    else:
        print("⚠️  System may have issues with OCR processing")
        print("   Consider upgrading server resources or using lower quality settings")
