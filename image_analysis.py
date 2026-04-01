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
        self.enable_auto_crop = True
    
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

        # Try to isolate the card region from background if photo is not tightly cropped
        if self.enable_auto_crop:
            image = self._extract_card_region(image)
        
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

    def _extract_card_region(self, image):
        """Attempt to crop image to the main card region."""
        height, width = image.shape[:2]
        image_area = float(height * width)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image

        best_rect = None
        best_score = -1
        expected_ratio = 2.5 / 3.5  # Typical card width/height

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < image_area * 0.2:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            if w <= 0 or h <= 0:
                continue

            ratio = w / float(h)
            ratio_error = abs(ratio - expected_ratio)

            # Prefer larger contours with card-like aspect ratio
            score = (area / image_area) - (ratio_error * 0.6)
            if score > best_score:
                best_score = score
                best_rect = (x, y, w, h)

        if best_rect is None:
            return image

        x, y, w, h = best_rect

        # Small safety padding around detected card
        pad_x = int(w * 0.02)
        pad_y = int(h * 0.02)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(width, x + w + pad_x)
        y2 = min(height, y + h + pad_y)

        cropped = image[y1:y2, x1:x2]
        if cropped.size == 0:
            return image
        return cropped

    def _calculate_chip_ratio(self, image_region, min_component=5, max_component=200):
        """Estimate edge/corner chipping by detecting small bright low-saturation artifacts."""
        hsv = cv2.cvtColor(image_region, cv2.COLOR_BGR2HSV)
        low_saturation = hsv[:, :, 1] < 40
        high_value = hsv[:, :, 2] > 210
        candidate = (low_saturation & high_value).astype(np.uint8) * 255

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)

        chip_pixels = 0
        for label_index in range(1, num_labels):
            area = stats[label_index, cv2.CC_STAT_AREA]
            if min_component <= area <= max_component:
                chip_pixels += area

        total_pixels = float(image_region.shape[0] * image_region.shape[1])
        if total_pixels == 0:
            return 0.0
        return chip_pixels / total_pixels
    
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
        chip_ratios = []
        edge_densities = []
        
        for corner_name, corner_img in corners.items():
            # Convert to grayscale
            gray_corner = cv2.cvtColor(corner_img, cv2.COLOR_BGR2GRAY)
            
            # Detect edges to check sharpness
            edges = cv2.Canny(gray_corner, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            edge_densities.append(edge_density)

            # Corner keypoint density helps distinguish true sharp corners from flat regions
            features = cv2.goodFeaturesToTrack(gray_corner, maxCorners=12, qualityLevel=0.01, minDistance=3)
            feature_count = 0 if features is None else len(features)
            feature_density = feature_count / 12.0
            
            # Estimate chipping from small bright low-saturation artifacts
            chip_ratio = self._calculate_chip_ratio(corner_img, min_component=3, max_component=120)
            chip_ratios.append(chip_ratio)
            
            # Calculate corner score
            # Higher edge density = sharper corner = better
            # Lower chip ratio = less wear = better
            sharpness_score = min(10, (edge_density * 700) + (feature_density * 4))
            wear_score = max(0, 10 - (chip_ratio * 3500))
            
            corner_score = (sharpness_score * 0.7 + wear_score * 0.3)
            corner_scores.append(corner_score)
            
            # Count as worn if score is below threshold
            if corner_score < 6.0:
                worn_corners += 1
        
        # Average sharpness across all corners
        avg_sharpness = sum(corner_scores) / len(corner_scores)
        avg_chip_ratio = float(np.mean(chip_ratios)) if chip_ratios else 0.0
        avg_edge_density = float(np.mean(edge_densities)) if edge_densities else 0.0

        # Derive grading inputs expected by CardGrader
        # Lower edge density generally means more rounded corners.
        rounding_level = max(0.0, min(10.0, (8.7 - avg_sharpness) * 1.3))
        fraying = max(0.0, min(10.0, avg_chip_ratio * 5000.0))
        missing_stock = any(value > 0.004 for value in chip_ratios)
        
        return {
            'sharpness': avg_sharpness,
            'worn_corners': worn_corners,
            'individual_scores': corner_scores,
            'rounding_level': rounding_level,
            'fraying': fraying,
            'missing_stock': missing_stock,
            'avg_chip_ratio': avg_chip_ratio,
            'avg_edge_density': avg_edge_density
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
        is_horizontal = [True, True, False, False]

        whiteness_values = []
        roughness_values = []
        notch_values = []
        lifting_values = []
        tear_values = []
        dirtiness_values = []

        for idx, edge_img in enumerate(edges_list):
            horizontal = is_horizontal[idx]
            gray_edge = cv2.cvtColor(edge_img, cv2.COLOR_BGR2GRAY)

            chip_ratio = self._calculate_chip_ratio(edge_img, min_component=5, max_component=250)
            whiteness_percent = chip_ratio * 100
            whiteness_values.append(whiteness_percent)

            edges_detected = cv2.Canny(gray_edge, 50, 150)
            edge_density = np.sum(edges_detected > 0) / edges_detected.size
            roughness = min(10, edge_density * 35)
            roughness_values.append(roughness)

            notch_values.append(self._estimate_notches(gray_edge, horizontal))
            lifting_values.append(self._estimate_lifting(edge_img, horizontal))
            tear_values.append(self._estimate_tears(gray_edge, horizontal))
            dirtiness_values.append(self._estimate_dirtiness(edge_img))

        return {
            'edge_whiteness': sum(whiteness_values) / len(whiteness_values),
            'roughness':      sum(roughness_values) / len(roughness_values),
            'notch_count':    min(8, sum(notch_values)),
            'lifting':        min(10.0, sum(lifting_values) / len(lifting_values)),
            'tears':          min(6, sum(tear_values)),
            'dirtiness':      min(10.0, sum(dirtiness_values) / len(dirtiness_values)),
            'edge_details': {
                'top':    whiteness_values[0],
                'bottom': whiteness_values[1],
                'left':   whiteness_values[2],
                'right':  whiteness_values[3],
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
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h, w = gray.shape[:2]

        # Focus on inner region to reduce border/background noise in surface grading.
        margin_y = int(h * 0.08)
        margin_x = int(w * 0.08)
        roi_gray = gray[margin_y:h-margin_y, margin_x:w-margin_x]
        roi_hsv = hsv[margin_y:h-margin_y, margin_x:w-margin_x]

        if roi_gray.size == 0:
            roi_gray = gray
            roi_hsv = hsv

        # Scratch detection: prefer long, oblique, high-contrast lines to avoid printed text/borders.
        edges = cv2.Canny(roi_gray, 35, 110)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=65, minLineLength=70, maxLineGap=8)
        scratch_lines = 0
        longest_line = 0.0
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                dx = float(x2 - x1)
                dy = float(y2 - y1)
                length = float(np.hypot(dx, dy))
                if length < 70:
                    continue
                angle = abs(np.degrees(np.arctan2(dy, dx)))
                # Exclude near-horizontal/vertical lines which are often design elements.
                if angle < 8 or angle > 82:
                    continue
                scratch_lines += 1
                longest_line = max(longest_line, length)
        scratch_count = min(scratch_lines // 12, 6)

        # Crease/wrinkle estimation from very strong long lines.
        strong_edges = cv2.Canny(roi_gray, 120, 220)
        crease_lines = cv2.HoughLinesP(strong_edges, 1, np.pi / 180, threshold=130, minLineLength=140, maxLineGap=3)
        strong_crease_lines = 0
        if crease_lines is not None:
            for line in crease_lines:
                x1, y1, x2, y2 = line[0]
                if np.hypot(x2 - x1, y2 - y1) > 170:
                    strong_crease_lines += 1
        crease_count = min(strong_crease_lines // 8, 3)

        wrinkle_count = min(6, crease_count + max(0, scratch_count - 2) // 2)
        roi_diag = float(np.hypot(roi_gray.shape[1], roi_gray.shape[0]))
        wrinkle_length = 0.0 if roi_diag == 0 else min(10.0, (longest_line / roi_diag) * 12.0)

        # Stain detection from low-saturation darker blotches.
        sat = roi_hsv[:, :, 1]
        val = roi_hsv[:, :, 2]
        stain_mask = ((sat < 45) & (val < 130)).astype(np.uint8) * 255
        stain_mask = cv2.morphologyEx(stain_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        stain_mask = cv2.morphologyEx(stain_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(stain_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        stain_pixels = 0
        total_roi = float(roi_gray.shape[0] * roi_gray.shape[1])
        for contour in contours:
            area = cv2.contourArea(contour)
            if 30 <= area <= (total_roi * 0.06):
                stain_pixels += area
        stain_ratio = 0.0 if total_roi == 0 else stain_pixels / total_roi
        stain_count = min(5, int(stain_ratio * 220))

        # Print defect / pit estimation using local high-frequency outliers.
        blur = cv2.GaussianBlur(roi_gray, (5, 5), 0)
        high_freq = cv2.absdiff(roi_gray, blur)
        threshold_value = np.percentile(high_freq, 99.2)
        defect_mask = (high_freq > threshold_value).astype(np.uint8) * 255
        defect_mask = cv2.morphologyEx(defect_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        defect_contours, _ = cv2.findContours(defect_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        defect_components = 0
        for contour in defect_contours:
            area = cv2.contourArea(contour)
            if 3 <= area <= 80:
                defect_components += 1
        print_defects = min(6, defect_components // 35)
        pit_count = min(6, defect_components // 50)
        pit_size = min(10.0, max(0.0, (threshold_value - 12.0) / 6.0))

        # Dent/scuff/gloss approximations.
        dent_count = min(4, max(0, (crease_count + scratch_count) // 3))
        edge_noise_density = np.sum(edges > 0) / edges.size if edges.size else 0
        scuffing = min(10.0, max(0.0, (edge_noise_density - 0.06) * 90.0))
        std_value = float(np.std(val))
        mean_sat = float(np.mean(sat))
        mean_val = float(np.mean(val))
        # Gloss loss: worn matte surfaces have lower mean value and lower saturation.
        # Formula gives 0 for bright/saturated (good gloss) and increases as surface dulls.
        gloss_loss = min(10.0, max(0.0, ((160.0 - mean_val) / 15.0) + ((40.0 - mean_sat) / 12.0)))

        water_damage = min(10.0, stain_count * 0.5 if stain_count >= 3 else 0.0)
        scratches_penetrate_gloss = bool(scratch_count >= 4 or crease_count > 0)

        return {
            'scratch_count': int(scratch_count),
            'scratches_penetrate_gloss': scratches_penetrate_gloss,
            'pit_count': int(pit_count),
            'pit_size': float(round(pit_size, 2)),
            'crease_count': int(crease_count),
            'wrinkle_count': int(wrinkle_count),
            'wrinkle_length': float(round(wrinkle_length, 2)),
            'stain_count': int(stain_count),
            'water_damage': float(round(water_damage, 2)),
            'print_defects': int(print_defects),
            'gloss_loss': float(round(gloss_loss, 2)),
            'dent_count': int(dent_count),
            'scuffing': float(round(scuffing, 2))
        }
    
    def _analyze_centering(self, image):
        """
        Analyze centering of the card image/design
        
        Looks for:
        - Balance of card borders on all sides
        - Position of inner printed area within the detected card
        """
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        centering_method = 'content-contour'
        centering_reliable = True
        centering_note = 'Measured from detected inner content borders.'

        # Build a mask for "printed content" (ink/artwork) as opposed to plain border.
        # Combines color richness (saturation) + texture (gradient magnitude).
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        magnitude = cv2.magnitude(grad_x, grad_y)

        sat = hsv[:, :, 1]
        sat_threshold = max(20, float(np.percentile(sat, 60)))
        grad_threshold = max(12.0, float(np.percentile(magnitude, 70)))

        color_mask = sat > sat_threshold
        texture_mask = magnitude > grad_threshold
        content_mask = (color_mask | texture_mask).astype(np.uint8) * 255

        # Remove noisy dots and fill holes so contours represent meaningful regions.
        kernel_open = np.ones((3, 3), np.uint8)
        kernel_close = np.ones((7, 7), np.uint8)
        content_mask = cv2.morphologyEx(content_mask, cv2.MORPH_OPEN, kernel_open)
        content_mask = cv2.morphologyEx(content_mask, cv2.MORPH_CLOSE, kernel_close)

        contours, _ = cv2.findContours(content_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            min_area = (width * height) * 0.12
            candidate = None
            candidate_area = -1

            for contour in contours:
                area = cv2.contourArea(contour)
                if area >= min_area and area > candidate_area:
                    candidate = contour
                    candidate_area = area

            if candidate is not None:
                x, y, w, h = cv2.boundingRect(candidate)

                touches_edge = (
                    x <= 2 or y <= 2 or
                    (x + w) >= (width - 2) or
                    (y + h) >= (height - 2)
                )
                oversized_inner = (w >= int(width * 0.96)) or (h >= int(height * 0.96))

                if touches_edge or oversized_inner:
                    left_right_ratio = 60.0
                    top_bottom_ratio = 60.0
                    centering_method = 'neutral-fallback'
                    centering_reliable = False
                    centering_note = 'Inner-content region touched image edge; centering may be affected by framing.'
                    return {
                        'left_right_ratio': left_right_ratio,
                        'top_bottom_ratio': top_bottom_ratio,
                        'centering_method': centering_method,
                        'centering_reliable': centering_reliable,
                        'centering_note': centering_note
                    }

                left_border = max(0, x)
                right_border = max(0, width - (x + w))
                top_border = max(0, y)
                bottom_border = max(0, height - (y + h))

                lr_total = left_border + right_border
                tb_total = top_border + bottom_border

                # If detected inner content nearly touches one axis edge, treat as unreliable.
                if lr_total < max(8, int(width * 0.015)):
                    left_right_ratio = 50.0
                else:
                    left_right_ratio = (left_border / lr_total) * 100

                if tb_total < max(8, int(height * 0.015)):
                    top_bottom_ratio = 50.0
                else:
                    top_bottom_ratio = (top_border / tb_total) * 100
            else:
                left_right_ratio = 60.0
                top_bottom_ratio = 60.0
        else:
            left_right_ratio = 60.0
            top_bottom_ratio = 60.0

        # If contour-based estimate looks extreme, use border-transition fallback.
        if (
            left_right_ratio < 15.0 or left_right_ratio > 85.0 or
            top_bottom_ratio < 15.0 or top_bottom_ratio > 85.0
        ):
            fallback_lr, fallback_tb = self._estimate_centering_from_border_transitions(gray)
            left_right_ratio = fallback_lr
            top_bottom_ratio = fallback_tb
            centering_method = 'border-transition-fallback'

            if fallback_lr == 60.0 and fallback_tb == 60.0:
                centering_reliable = False
                centering_note = 'Centering fallback could not detect stable border transitions; framing may influence results.'
            else:
                centering_note = 'Used border-transition fallback due extreme contour estimate.'

        # Clamp to sane range to prevent outlier spikes from dominating final grade
        left_right_ratio = max(5.0, min(95.0, float(left_right_ratio)))
        top_bottom_ratio = max(5.0, min(95.0, float(top_bottom_ratio)))
        
        return {
            'left_right_ratio': left_right_ratio,
            'top_bottom_ratio': top_bottom_ratio,
            'centering_method': centering_method,
            'centering_reliable': centering_reliable,
            'centering_note': centering_note
        }

    def _estimate_centering_from_border_transitions(self, gray):
        """Estimate centering from strongest border->content transitions on each side."""
        height, width = gray.shape[:2]

        # Mean intensity projections
        col_mean = gray.mean(axis=0).astype(np.float32)
        row_mean = gray.mean(axis=1).astype(np.float32)

        # Smooth 1D signals
        col_mean = cv2.GaussianBlur(col_mean.reshape(1, -1), (1, 9), 0).flatten()
        row_mean = cv2.GaussianBlur(row_mean.reshape(-1, 1), (9, 1), 0).flatten()

        col_diff = np.abs(np.diff(col_mean))
        row_diff = np.abs(np.diff(row_mean))

        x_limit = max(10, int(width * 0.35))
        y_limit = max(10, int(height * 0.35))

        left_region = col_diff[:x_limit]
        right_region = col_diff[max(0, len(col_diff) - x_limit):]
        top_region = row_diff[:y_limit]
        bottom_region = row_diff[max(0, len(row_diff) - y_limit):]

        if len(left_region) == 0 or len(right_region) == 0 or len(top_region) == 0 or len(bottom_region) == 0:
            return 60.0, 60.0

        left_idx = int(np.argmax(left_region))
        right_local_idx = int(np.argmax(right_region))
        top_idx = int(np.argmax(top_region))
        bottom_local_idx = int(np.argmax(bottom_region))

        right_idx = len(col_diff) - len(right_region) + right_local_idx
        bottom_idx = len(row_diff) - len(bottom_region) + bottom_local_idx

        left_border = max(0, left_idx)
        right_border = max(0, width - right_idx - 1)
        top_border = max(0, top_idx)
        bottom_border = max(0, height - bottom_idx - 1)

        # Validate transition strength to avoid noisy fallback outputs.
        strength = np.array([
            left_region[left_idx],
            right_region[right_local_idx],
            top_region[top_idx],
            bottom_region[bottom_local_idx]
        ])
        if np.median(strength) < 2.0:
            return 60.0, 60.0

        lr_total = left_border + right_border
        tb_total = top_border + bottom_border

        if lr_total < max(8, int(width * 0.015)) or tb_total < max(8, int(height * 0.015)):
            return 60.0, 60.0

        left_right_ratio = (left_border / lr_total) * 100
        top_bottom_ratio = (top_border / tb_total) * 100
        return float(left_right_ratio), float(top_bottom_ratio)
    
    def _estimate_notches(self, gray_strip: np.ndarray, horizontal: bool) -> int:
        """Count notch-like dips in the edge brightness profile."""
        if gray_strip.size == 0:
            return 0
        # 1-D projection along the long axis
        profile = np.mean(gray_strip, axis=0 if horizontal else 1).astype(np.float32)
        if len(profile) < 20:
            return 0
        # Smooth to reduce noise
        kernel = np.ones(7, dtype=np.float32) / 7
        smoothed = np.convolve(profile, kernel, mode='same')
        baseline = float(np.percentile(smoothed, 75))
        threshold = baseline - 25.0
        below = smoothed < threshold
        if not np.any(below):
            return 0
        groups, in_dip = 0, False
        for val in below:
            if val and not in_dip:
                groups += 1
                in_dip = True
            elif not val:
                in_dip = False
        return min(groups, 6)

    def _estimate_lifting(self, edge_img: np.ndarray, horizontal: bool) -> float:
        """Estimate edge-lifting from a strong perpendicular brightness gradient in the inner strip."""
        gray = cv2.cvtColor(edge_img, cv2.COLOR_BGR2GRAY)
        if horizontal:
            grad = cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
            inner = np.abs(grad[gray.shape[0] // 2:, :])
        else:
            grad = cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
            inner = np.abs(grad[:, gray.shape[1] // 2:])
        if inner.size == 0:
            return 0.0
        return min(10.0, float(np.percentile(inner, 95)) / 25.0)

    def _estimate_tears(self, gray_strip: np.ndarray, horizontal: bool) -> int:
        """Detect tear-like perpendicular linear features in an edge strip."""
        if gray_strip.size == 0:
            return 0
        edges = cv2.Canny(gray_strip, 80, 200)
        min_len = max(8, min(gray_strip.shape[:2]) // 3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=20,
                                 minLineLength=min_len, maxLineGap=3)
        if lines is None:
            return 0
        tear_count = 0
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if horizontal:
                if 70 <= angle <= 110:
                    tear_count += 1
            else:
                if angle <= 20 or angle >= 160:
                    tear_count += 1
        return min(3, tear_count)

    def _estimate_dirtiness(self, edge_img: np.ndarray) -> float:
        """Estimate dirtiness from dark, low-saturation regions in an edge strip."""
        if edge_img.size == 0:
            return 0.0
        hsv = cv2.cvtColor(edge_img, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        dirty_mask = (sat < 35) & (val < 90)
        dirty_ratio = float(np.sum(dirty_mask)) / float(dirty_mask.size)
        return min(10.0, dirty_ratio * 300.0)

    def analyze_image_array(self, image: np.ndarray) -> dict:
        """Analyze a card image from a numpy array (BGR) rather than a file path."""
        if image is None or image.size == 0:
            raise ValueError("Empty image array")

        if self.enable_auto_crop:
            image = self._extract_card_region(image)

        height, width = image.shape[:2]
        if min(height, width) < self.min_dimension:
            print(f"Warning: Image resolution is low ({width}x{height}). Results may be less accurate.")

        return {
            'corners':      self._analyze_corners(image),
            'edges':        self._analyze_edges(image),
            'surface':      self._analyze_surface(image),
            'centering':    self._analyze_centering(image),
            'print_quality': self._analyze_print_quality(image),
            'image_dimensions': {'width': width, 'height': height},
        }

    def extract_card_from_slab(self, image):
        """
        Extract the actual card image from inside a PSA/BGS slab photo.

        Returns dict:
            card_image: cropped numpy array of just the card
            label_image: cropped numpy array of just the label area
            label_end_y: pixel row where label ends
            card_bounds: (x1, y1, x2, y2) of extracted card region
            method: str describing detection method used
        """
        h, w = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # --- Step 1: Find where the label ends ---
        # PSA labels are colorful (high saturation). Card area has lower saturation (mostly white border).
        sat_profile = np.mean(hsv[:, :, 1], axis=1).astype(np.float32)
        # Smooth the profile
        sat_profile = np.convolve(sat_profile, np.ones(5)/5, mode='same')

        label_end_y = int(h * 0.22)  # default fallback
        top_sat = float(np.mean(sat_profile[:max(1, int(h * 0.08))]))

        # Search for the drop in saturation that signals end of label
        for i in range(int(h * 0.08), int(h * 0.40)):
            if sat_profile[i] < top_sat * 0.45:
                label_end_y = i
                break

        # --- Step 2: Isolate the card window region (below label, inset from slab borders) ---
        # PSA slab plastic border is roughly 7-9% on left/right, 3% on bottom
        border_x = int(w * 0.08)
        border_bottom = int(h * 0.04)
        gap_after_label = int(h * 0.015)

        card_top    = label_end_y + gap_after_label
        card_bottom = h - border_bottom
        card_left   = border_x
        card_right  = w - border_x

        # --- Step 3: Try to refine with edge detection inside the window region ---
        window = image[card_top:card_bottom, card_left:card_right]
        if window.size > 0:
            gray_win = cv2.cvtColor(window, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray_win, 40, 120)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges, kernel, iterations=1)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            win_h, win_w = window.shape[:2]
            win_area = float(win_h * win_w)
            expected_ratio = 2.5 / 3.5

            best_rect = None
            best_score = -1
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < win_area * 0.25:
                    continue
                x, y, cw, ch = cv2.boundingRect(contour)
                if cw <= 0 or ch <= 0:
                    continue
                ratio = cw / float(ch)
                ratio_err = abs(ratio - expected_ratio)
                score = (area / win_area) - (ratio_err * 0.5)
                if score > best_score:
                    best_score = score
                    best_rect = (x, y, cw, ch)

            if best_rect is not None:
                rx, ry, rw, rh = best_rect
                # Only use if it's a significant portion of the window and not the whole window
                if rw * rh > win_area * 0.3 and (rw < win_w * 0.98 or rh < win_h * 0.98):
                    # Map back to full image coordinates
                    card_left   = card_left + rx
                    card_top    = card_top + ry
                    card_right  = card_left + rw
                    card_bottom = card_top + rh
                    method = 'edge-detection'
                else:
                    method = 'proportional'
            else:
                method = 'proportional'
        else:
            method = 'proportional'

        # Clamp
        card_left   = max(0, card_left)
        card_top    = max(0, card_top)
        card_right  = min(w, card_right)
        card_bottom = min(h, card_bottom)

        card_image  = image[card_top:card_bottom, card_left:card_right]
        label_image = image[0:label_end_y, :]

        if card_image.size == 0:
            card_image = image  # fallback: use full image
            method = 'fallback-full'

        return {
            'card_image':  card_image,
            'label_image': label_image,
            'label_end_y': label_end_y,
            'card_bounds': (card_left, card_top, card_right, card_bottom),
            'method':      method,
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


def analyze_slab_images(front_slab_path, back_slab_path):
    """
    Extract card regions from front and back slab photos and analyze them.
    Returns (front_analysis, back_analysis, slab_info_dict).
    """
    analyzer = CardImageAnalyzer()

    front_img = cv2.imread(front_slab_path)
    back_img  = cv2.imread(back_slab_path)

    if front_img is None:
        raise ValueError(f"Could not load front slab image: {front_slab_path}")
    if back_img is None:
        raise ValueError(f"Could not load back slab image: {back_slab_path}")

    front_slab = analyzer.extract_card_from_slab(front_img)
    back_slab  = analyzer.extract_card_from_slab(back_img)

    # Analyze the extracted card regions (not the full slab)
    front_analysis = analyzer.analyze_image_array(front_slab['card_image'])
    back_analysis  = analyzer.analyze_image_array(back_slab['card_image'])

    slab_info = {
        'front_method':      front_slab['method'],
        'back_method':       back_slab['method'],
        'front_card_bounds': front_slab['card_bounds'],
        'back_card_bounds':  back_slab['card_bounds'],
        'front_label_end_y': front_slab['label_end_y'],
    }

    return front_analysis, back_analysis, slab_info


# Example usage
if __name__ == "__main__":
    # This would be used with actual card images
    print("Card Image Analyzer Module")
    print("Use analyze_card_images(front_path, back_path) to analyze card images")
