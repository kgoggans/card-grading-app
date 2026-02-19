#!/usr/bin/env python3
"""
Test script for card grading system

Creates a test image and runs it through the grading pipeline
"""

import numpy as np
from PIL import Image
import os
from image_analysis import CardImageAnalyzer
from grading_system import CardGrader

def create_test_card_image(filename, quality='good'):
    """
    Create a synthetic test card image
    
    Args:
        filename (str): Output filename
        quality (str): 'perfect', 'good', 'fair', or 'poor'
    """
    # Standard card dimensions (approximately 2.5" x 3.5" at 300 DPI)
    width, height = 750, 1050
    
    # Create base image with white background
    img = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    # Add border (typical card border)
    border_color = [200, 200, 200]
    border_width = 30
    img[0:border_width, :] = border_color
    img[height-border_width:height, :] = border_color
    img[:, 0:border_width] = border_color
    img[:, width-border_width:width] = border_color
    
    # Add main image area with gradient (simulating card design)
    for y in range(border_width, height - border_width):
        gradient = int(100 + (y / height) * 100)
        img[y, border_width:width-border_width] = [gradient, gradient + 20, gradient + 40]
    
    # Add some "text" (colored rectangles representing text/graphics)
    # Player name area
    img[100:150, 100:400] = [50, 50, 200]
    # Stats area
    img[height-250:height-150, 100:width-100] = [200, 200, 220]
    
    # Add defects based on quality
    if quality == 'good':
        # Minor corner wear on one corner
        for i in range(20):
            for j in range(20):
                if i + j < 20:
                    img[i, j] = [240, 240, 240]
    elif quality == 'fair':
        # Corner wear on multiple corners
        for i in range(30):
            for j in range(30):
                if i + j < 30:
                    img[i, j] = [240, 240, 240]
                    img[height-i-1, j] = [240, 240, 240]
        # Add some edge whitening
        img[40:height-40, 0:5] = [250, 250, 250]
    elif quality == 'poor':
        # Heavy corner wear
        for i in range(50):
            for j in range(50):
                if i + j < 50:
                    img[i, j] = [230, 230, 230]
                    img[i, width-j-1] = [230, 230, 230]
                    img[height-i-1, j] = [230, 230, 230]
                    img[height-i-1, width-j-1] = [230, 230, 230]
        # Edge whitening
        img[40:height-40, 0:10] = [250, 250, 250]
        img[40:height-40, width-10:width] = [250, 250, 250]
        # Add a crease (diagonal line)
        for i in range(100, 300):
            img[i*3:i*3+3, i:i+2] = [220, 220, 220]
    
    # Convert to PIL Image and save
    pil_img = Image.fromarray(img)
    pil_img.save(filename)
    print(f"Created test image: {filename} (quality: {quality})")


def test_grading_system():
    """Test the complete grading system with synthetic images"""
    print("=" * 60)
    print("Card Grading System Test")
    print("=" * 60)
    
    # Create test directory
    test_dir = "test_images"
    os.makedirs(test_dir, exist_ok=True)
    
    # Test different quality levels
    test_cases = [
        ('perfect', 'Perfect condition card'),
        ('good', 'Good condition with minor wear'),
        ('fair', 'Fair condition with moderate wear'),
        ('poor', 'Poor condition with significant damage')
    ]
    
    for quality, description in test_cases:
        print(f"\n{'-' * 60}")
        print(f"Testing: {description}")
        print(f"{'-' * 60}")
        
        # Create test images
        front_path = os.path.join(test_dir, f"card_front_{quality}.png")
        back_path = os.path.join(test_dir, f"card_back_{quality}.png")
        
        create_test_card_image(front_path, quality)
        create_test_card_image(back_path, quality)
        
        # Analyze images
        print("\nAnalyzing images...")
        analyzer = CardImageAnalyzer()
        front_analysis = analyzer.analyze_image(front_path)
        back_analysis = analyzer.analyze_image(back_path)
        
        # Grade card
        grader = CardGrader()
        result = grader.grade_card(front_analysis, back_analysis)
        
        # Display results
        print(f"\n✓ PSA Grade: {result['grade']}")
        print(f"  {result['description']}")
        print(f"\n  Category Scores:")
        for category, score in result['category_scores'].items():
            print(f"    {category.replace('_', ' ').title()}: {score:.1f}/10")
        
        print(f"\n  Analysis:")
        for line in result['details'].split('\n'):
            if line.strip():
                print(f"    {line}")
    
    print(f"\n{'=' * 60}")
    print("Test Complete!")
    print(f"Test images saved in: {test_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    test_grading_system()
