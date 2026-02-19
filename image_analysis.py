"""
Image Analysis Module for Card Grading

This module analyzes sports card images to extract condition metrics
that feed into the PSA grading system.
"""

import cv2
import numpy as np
from PIL import Image
import os


class CardImageAnalyzer:
    """Analyzes card images to determine condition metrics"""
    
    def __init__(self):
        self.min_dimension = 800  # Minimum resolution for accurate analysis
    
    def analyze_image(self, image_path):
        """
        Analyze a card image and return condition metrics
        
        Args:
            image_path (str): Path to the card image
            
        Returns:
            dict: Analysis results with condition metrics
        """
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        # Ensure minimum resolution
        height, width = image.shape[:2]
        if min(height, width) < self.min_dimension:
            print(f"Warning: Image resolution is low ({width}x{height}). Results may be less accurate.")
        
        # Perform various analyses
        corner_analysis = self._analyze_corners(image)
        edge_analysis = self._analyze_edges(image)
        surface_analysis = self._analyze_surface(image)
        centering_analysis = self._analyze_centering(image)
        print_quality_analysis = self._analyze_print_quality(image)
        
        return {
            'corners': corner_analysis,
            'edges': edge_analysis,
            'surface': surface_analysis,
            'centering': centering_analysis,
            'print_quality': print_quality_analysis,
            'image_dimensions': {'width': width, 'height': height}
        }
    
    def _analyze_corners(self, image):
        """
        Analyze corner condition
        
        Looks for:
        - Corner sharpness vs roundedness
        - White spots indicating wear
        - Damage/bent corners
        """
        height, width = image.shape[:2]
        
        # Define corner regions (10% of dimensions)
        corner_size_h = int(height * 0.1)
        corner_size_w = int(width * 0.1)
        
        corners = {
            'top_left': image[0:corner_size_h, 0:corner_size_w],
            'top_right': image[0:corner_size_h, width-corner_size_w:width],
            'bottom_left': image[height-corner_size_h:height, 0:corner_size_w],
            'bottom_right': image[height-corner_size_h:height, width-corner_size_w:width]
        }
        
        corner_scores = []
        worn_corners = 0
        
        for corner_name, corner_img in corners.items():
            # Convert to grayscale
            gray_corner = cv2.cvtColor(corner_img, cv2.COLOR_BGR2GRAY)
            
            # Detect edges to check sharpness
            edges = cv2.Canny(gray_corner, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # Check for white spots (wear indicators)
            # White pixels are typically indicative of wear on dark backgrounds
            white_pixels = np.sum(gray_corner > 200)
            white_ratio = white_pixels / gray_corner.size
            
            # Calculate corner score
            # Higher edge density = sharper corner = better
            # Lower white ratio = less wear = better
            sharpness_score = min(10, edge_density * 100)
            wear_score = max(0, 10 - (white_ratio * 50))
            
            corner_score = (sharpness_score * 0.6 + wear_score * 0.4)
            corner_scores.append(corner_score)
            
            # Count as worn if score is below threshold
            if corner_score < 7.0:
                worn_corners += 1
        
        # Average sharpness across all corners
        avg_sharpness = sum(corner_scores) / len(corner_scores)
        
        return {
            'sharpness': avg_sharpness,
            'worn_corners': worn_corners,
            'individual_scores': corner_scores
        }
    
    def _analyze_edges(self, image):
        """
        Analyze edge condition
        
        Looks for:
        - Edge whiteness (chipping)
        - Edge roughness
        - Edge wear
        """
        height, width = image.shape[:2]
        
        # Extract edge regions (5% border)
        border_size_h = int(height * 0.05)
        border_size_w = int(width * 0.05)
        
        # Get all four edges
        top_edge = image[0:border_size_h, :]
        bottom_edge = image[height-border_size_h:height, :]
        left_edge = image[:, 0:border_size_w]
        right_edge = image[:, width-border_size_w:width]
        
        edges_list = [top_edge, bottom_edge, left_edge, right_edge]
        
        whiteness_values = []
        roughness_values = []
        
        for edge_img in edges_list:
            gray_edge = cv2.cvtColor(edge_img, cv2.COLOR_BGR2GRAY)
            
            # Measure whiteness (potential chipping)
            white_pixels = np.sum(gray_edge > 220)
            whiteness_percent = (white_pixels / gray_edge.size) * 100
            whiteness_values.append(whiteness_percent)
            
            # Measure roughness using edge detection
            edges_detected = cv2.Canny(gray_edge, 50, 150)
            edge_variance = np.std(edges_detected)
            roughness = min(10, edge_variance / 10)
            roughness_values.append(roughness)
        
        return {
            'edge_whiteness': sum(whiteness_values) / len(whiteness_values),
            'roughness': sum(roughness_values) / len(roughness_values),
            'edge_details': {
                'top': whiteness_values[0],
                'bottom': whiteness_values[1],
                'left': whiteness_values[2],
                'right': whiteness_values[3]
            }
        }
    
    def _analyze_surface(self, image):
        """
        Analyze surface condition
        
        Looks for:
        - Scratches
        - Creases
        - Stains/discoloration
        - Print defects
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Detect scratches using line detection
        edges = cv2.Canny(gray, 30, 100)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, minLineLength=30, maxLineGap=10)
        
        scratch_count = 0
        if lines is not None:
            # Filter lines that might be scratches (not part of card design)
            for line in lines:
                x1, y1, x2, y2 = line[0]
                length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
                # Long, thin lines are potential scratches
                if length > 50:
                    scratch_count += 1
        
        # Limit scratch count to reasonable number (many lines are part of design)
        scratch_count = min(scratch_count // 10, 10)  # Scale down and cap
        
        # Detect creases using more aggressive edge detection
        strong_edges = cv2.Canny(gray, 100, 200)
        # Creases typically appear as strong continuous lines
        crease_lines = cv2.HoughLinesP(strong_edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=5)
        
        crease_count = 0
        if crease_lines is not None:
            crease_count = min(len(crease_lines) // 5, 5)  # Scale and cap
        
        # Detect stains using color analysis
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Look for unusual discoloration
        # This is a simplified approach - in practice, would need card-specific baseline
        mean_saturation = np.mean(hsv[:, :, 1])
        std_saturation = np.std(hsv[:, :, 1])
        
        # High variance in saturation might indicate staining
        stain_count = 0
        if std_saturation > 50:
            stain_count = min(int(std_saturation / 30), 5)
        
        # Detect print defects (spots, misalignment)
        # Using blob detection for spots
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 200, 255, cv2.THRESH_BINARY)
        
        # Count small bright spots that might be print defects
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        print_defects = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if 5 < area < 100:  # Small spots
                print_defects += 1
        
        print_defects = min(print_defects // 20, 5)  # Scale and cap
        
        return {
            'scratch_count': scratch_count,
            'crease_count': crease_count,
            'stain_count': stain_count,
            'print_defects': print_defects
        }
    
    def _analyze_centering(self, image):
        """
        Analyze centering of the card image/design
        
        Looks for:
        - Balance of borders on all sides
        - Image position within the card
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        height, width = image.shape[:2]
        
        # Try to detect the main content area (inner image on card)
        # Using edge detection and finding the largest rectangle
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Find the largest contour (likely the card border or main image)
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            
            # Calculate centering ratios
            left_border = x
            right_border = width - (x + w)
            top_border = y
            bottom_border = height - (y + h)
            
            # Calculate ratios (0-100, where 50 is perfect center)
            if left_border + right_border > 0:
                left_right_ratio = (left_border / (left_border + right_border)) * 100
            else:
                left_right_ratio = 50.0
            
            if top_border + bottom_border > 0:
                top_bottom_ratio = (top_border / (top_border + bottom_border)) * 100
            else:
                top_bottom_ratio = 50.0
        else:
            # If no contours found, assume decent centering
            left_right_ratio = 50.0
            top_bottom_ratio = 50.0
        
        return {
            'left_right_ratio': left_right_ratio,
            'top_bottom_ratio': top_bottom_ratio
        }
    
    def _analyze_print_quality(self, image):
        """
        Analyze print quality
        
        Looks for:
        - Focus/sharpness
        - Color accuracy (vibrance)
        - Registration (color alignment)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Measure focus/sharpness using Laplacian variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        focus_measure = laplacian.var()
        
        # Scale to 0-10 (typical variance range is 0-500 for cards)
        focus_score = min(10, focus_measure / 50)
        
        # Measure color accuracy by checking color distribution
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Good print has vibrant, well-distributed colors
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        
        mean_saturation = np.mean(saturation)
        mean_value = np.mean(value)
        
        # Score color accuracy (higher saturation and value = better)
        color_accuracy = min(10, (mean_saturation / 25) + (mean_value / 25))
        
        # Measure registration (color alignment)
        # Split into color channels and check alignment
        b, g, r = cv2.split(image)
        
        # Calculate correlation between channels (high = good registration)
        correlation_rg = np.corrcoef(r.flatten(), g.flatten())[0, 1]
        correlation_rb = np.corrcoef(r.flatten(), b.flatten())[0, 1]
        correlation_gb = np.corrcoef(g.flatten(), b.flatten())[0, 1]
        
        avg_correlation = (correlation_rg + correlation_rb + correlation_gb) / 3
        
        # Scale to 0-10 (correlation is typically 0.8-1.0 for good registration)
        registration_score = min(10, (avg_correlation - 0.7) * 33.3)
        
        return {
            'focus_score': max(1, focus_score),
            'color_accuracy': max(1, color_accuracy),
            'registration': max(1, registration_score)
        }


def analyze_card_images(front_image_path, back_image_path):
    """
    Analyze both front and back images of a card
    
    Args:
        front_image_path (str): Path to front image
        back_image_path (str): Path to back image
        
    Returns:
        tuple: (front_analysis, back_analysis)
    """
    analyzer = CardImageAnalyzer()
    
    front_analysis = analyzer.analyze_image(front_image_path)
    back_analysis = analyzer.analyze_image(back_image_path)
    
    return front_analysis, back_analysis


# Example usage
if __name__ == "__main__":
    # This would be used with actual card images
    print("Card Image Analyzer Module")
    print("Use analyze_card_images(front_path, back_path) to analyze card images")
