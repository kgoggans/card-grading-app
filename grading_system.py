import json
import os

"""
Custom Card Grading System Module

This module implements a comprehensive grading system for sports cards
using a 100-1000 point scale with 19 distinct grade levels.

Grading Scale:
- 10 PRISTINE (990-1000): Virtually flawless card
- 10 GEM MINT (950-989): Extremely high-grade card with minor imperfections
- 9 MINT (900-949): High-grade card with minimal wear
- 8.5 NEAR MINT-MINT+ (850-899): Very nice card with light wear
- 8 NEAR MINT-MINT (800-849): Nice card with some visible wear
- 7.5 NEAR MINT+ (750-799): Above average with moderate wear
- 7 NEAR MINT (700-749): Average collectible with visible wear
- 6.5 EXCELLENT-MINT+ (650-699): Below average with significant wear
- 6 EXCELLENT-MINT (600-649): Noticeable wear and defects
- 5.5 EXCELLENT+ (550-599): Heavy wear beginning to show
- 5 EXCELLENT (500-549): Substantial wear present
- 4.5 VERY GOOD-EXCELLENT+ (450-499): Significant damage visible
- 4 VERY GOOD-EXCELLENT (400-449): Heavy damage and wear
- 3.5 VERY GOOD+ (350-399): Very heavy damage
- 3 VERY GOOD (300-349): Extreme wear and damage
- 2.5 GOOD+ (250-299): Severe damage throughout
- 2 GOOD (200-249): Major structural issues
- 1.5 FAIR (150-199): Card integrity compromised
- 1 POOR (100-149): Barely recognizable condition
"""

class PSAGradingCriteria:
    """Defines the custom grading criteria and weights"""
    
    # Grading categories and their weights (must sum to 1.0)
    CATEGORY_WEIGHTS = {
        'corners': 0.25,    # Corner wear/damage
        'edges': 0.25,      # Edge wear/chipping
        'surface': 0.25,    # Surface scratches/wear/defects
        'centering': 0.25   # Centering of image
    }
    
    # Grade ranges: (min_score, max_score, numeric_grade, name)
    GRADE_RANGES = [
        (990, 1000, 10.0, "PRISTINE"),
        (950, 989, 10.0, "GEM MINT"),
        (900, 949, 9.0, "MINT"),
        (850, 899, 8.5, "NEAR MINT - MINT+"),
        (800, 849, 8.0, "NEAR MINT - MINT"),
        (750, 799, 7.5, "NEAR MINT+"),
        (700, 749, 7.0, "NEAR MINT"),
        (650, 699, 6.5, "EXCELLENT - MINT+"),
        (600, 649, 6.0, "EXCELLENT - MINT"),
        (550, 599, 5.5, "EXCELLENT+"),
        (500, 549, 5.0, "EXCELLENT"),
        (450, 499, 4.5, "VERY GOOD - EXCELLENT+"),
        (400, 449, 4.0, "VERY GOOD - EXCELLENT"),
        (350, 399, 3.5, "VERY GOOD+"),
        (300, 349, 3.0, "VERY GOOD"),
        (250, 299, 2.5, "GOOD+"),
        (200, 249, 2.0, "GOOD"),
        (150, 199, 1.5, "FAIR"),
        (100, 149, 1.0, "POOR")
    ]
    
    # Detailed grade descriptions based on comprehensive criteria
    GRADE_DESCRIPTIONS = {
        10.0: {
            "PRISTINE": {
                "overall": "Virtually flawless card with no visible flaws, sharp corners, perfect centering",
                "centering": "Front image centered within ~51/49, back within ~54.5/45.5 (Sports) or ~52/48 (TCG)",
                "corners": "Virtually flawless corners. No visible wear or fraying. Sharp and crisp with little to no fill or fray artifacts",
                "surface": "Flawless surface, exhibiting only Non-Human Observable Defects (NHOD's)",
                "edges": "Virtually flawless edges. Very minor fill or fray artifacts under high resolution"
            },
            "GEM MINT": {
                "overall": "Extremely high-grade card with 4 sharp corners and minor imperfections",
                "centering": "Front image centered within ~55/45, back within ~70/30 (Sports) or ~65/35 (TCG)",
                "corners": "4 sharp corners with minor fill or fray artifacts. Light corner touch or two may be apparent on reverse. Corners remain sharp & square",
                "surface": "Extremely attractive surface. Slight print imperfection under hi-res. Very minor defect: small pit, light scratch not penetrating gloss, or light print/refractor line. Back may have multiple print lines and larger, deeper pit",
                "edges": "Edge may display minor fill or fray. Very minor edge surface wear under high resolution"
            }
        },
        9.0: {
            "overall": "High-grade card with minimal wear and sharp square corners",
            "centering": "Front image centered within ~60/40, back within ~90/10 (Sports) or ~75/25 (TCG)",
            "corners": "Sharp square corners. Up to two very light corner touches visible on front where stock is compromised. Multiple corner touches on back. More significant fill or fray artifacts under high resolution",
            "surface": "Larger and deeper pit may be present. May have 2-3 small pits and/or longer scratch not penetrating gloss. Light but present print or refractor line running length of card. Minor print imperfection or multiple spots. Small scratch penetrating gloss on back. Multiple, more visible print lines",
            "edges": "Visible but minor edge surface wear on one or two edges. More significant fill or fray artifacts under high resolution"
        },
        8.5: {
            "overall": "Very nice card with light wear and multiple light corner touches",
            "centering": "Front image centered within ~62.5/37.5, back within ~95/5 (Sports) or ~85/15 (TCG)",
            "corners": "Corners appear sharp and square. Multiple light corner touches on front where stock is compromised. Small amount of missing stock may be present on back corners. Fray artifacts become more visible",
            "surface": "Multiple surface defects presenting. Small scratch penetrates gloss. Multiple refractor or print lines. Very minor scuffing might be present. Subtle focus imperfections around image or logos",
            "edges": "Visible edge surface wear or light chipping on multiple edges on front. Fray artifacts may become more visible"
        },
        8.0: {
            "overall": "Nice card with some visible wear on corners and edges",
            "centering": "Front image centered within ~65/35. For TCG, backs centered within ~95/5. Back may show tiny sliver of border but not miscut",
            "corners": "Corner may start showing minor wear. Other corners square but display light touches on front. Back corners show more wear. Fray artifacts more visible and significant, very minor fill areas under high resolution",
            "surface": "Several defects present. Combination depends on size, area, location. Minor but larger areas of print imperfections. Minor roller line might be visible on front or back",
            "edges": "Edge surface wear and minor chipping on all four edges. Fray artifacts more visible and significant, very minor fill areas under high resolution. Minor lifting to edge may start becoming visible"
        },
        7.5: {
            "overall": "Above average card showing more wear and losing sharpness",
            "centering": "Image centered within ~67.5/32.5 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Corners show more wear and may lose sharpness. All four front corners may have touches where stock is compromised. Slight fraying on corner surface",
            "surface": "Very minor dent to front surface might be visible. All defects become more prevalent. Multiple visible defects in and around facial region (most impactful)",
            "edges": "Edge surface wear and chipping worsen. Areas of fray become larger and visible. More significant lifting to an edge or minor lifting on multiple edges. Edges lose smoothness and show rougher appearance"
        },
        7.0: {
            "overall": "Average collectible with visible wear and fraying corners",
            "centering": "Image centered within ~70/30 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Corners square but multiple corners display fraying on surfaces. Slight bend or hit to corner compromising card surface might be present. Larger fray artifacts on corners edge clearly visible",
            "surface": "Minor dent might impact both front and back. Multiple print dots (print defects) throughout card visible",
            "edges": "Minor 'notch' impacting edge surface might become visible. Lifting to all four edges visible. Edge surface wear and chipping completely visible"
        },
        6.5: {
            "overall": "Below average card with corner shape loss and significant wear",
            "centering": "Image centered within ~72.5/27.5 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Corner may lose shape due to excessive corner surface wear, bend, dinged corner, or larger fill area distorting appearance. Three or four corners showing significant fraying or chipping",
            "surface": "All above defects visible and worsening. Very short wrinkle coming off edge on back under high resolution. Small area of water damage on back",
            "edges": "Minor notch on two edges might be present. Fray artifacts clearly visible, areas of fill giving appearance of waviness to edge"
        },
        6.0: {
            "overall": "Card with noticeable wear including slight corner rounding",
            "centering": "Image centered within ~75/25 on front. Back may show tiny sliver of border but not miscut",
            "corners": "One corner may show slight rounding. Fraying more prevalent on multiple corners. Multiple corners showing more significant wear on front and back. Slight bend or ding clearly present on corner",
            "surface": "Longer, more visible wrinkle on back. Light staining may appear on back. Larger dent or multiple minor dents. More significant surface scuffs in single area. Focus off demonstrating two-for-one effect on objects (eyes, buttons, letters, logo)",
            "edges": "Minor notches on three or more edges, or one severe notch on single edge. Larger areas of chipping significantly impacting card surface. Roughness worsening"
        },
        5.5: {
            "overall": "Card with heavy wear beginning to show and minor corner rounding",
            "centering": "Image centered within ~77.5/22.5 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Very minor corner rounding on one or two corners. More severe bend or slight wrinkle may be present on corner surface",
            "surface": "Small wrinkle on front may be present. Multiple small wrinkles on back possible. Light staining to front visible. Small area of water damage present on front",
            "edges": "Severe notch on two edges present. Larger areas of chipping on multiple edges impacting card surface may be apparent"
        },
        5.0: {
            "overall": "Card with substantial wear and loss of corner squareness",
            "centering": "Image centered within ~80/20 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Rounding of corner or two becomes more significant. Larger areas of corner surface wear or chipping visible. All four corners lost squareness due to surface wear, dings, or fill issues. Excessive fray artifacts visible and distracting on multiple corners",
            "surface": "Multiple small wrinkles on front. Larger area of staining visible. Multiple areas of surface scuffing visible. Loss of original gloss becomes visible",
            "edges": "Notches and chipping visible on same edge or edges. Fray, fill, and roughness significantly impacting edge"
        },
        4.5: {
            "overall": "Card with significant damage including clearly rounded corner",
            "centering": "Image centered within ~82.5/17.5 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Corner clearly rounded accompanied by corner surface wear, fraying, or chipping. Multiple corners with bends or dings impacting corner surface",
            "surface": "Minor crease visible, breaking stock on front or back. Crease usually has minor impact on opposite side. Larger wrinkle spanning into facial scoring region",
            "edges": "Roughness of edge worsens. Notches and chipping on multiple edges, front and back. Fray artifacts large and distracting to edge appearance"
        },
        4.0: {
            "overall": "Card with heavy damage and multiple rounded corners",
            "centering": "Image centered within ~85/15 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Two or three corners clearly rounded with areas of corner surface wear, fraying, or chipping. Bends, dings, and surface wear more prevalent if corners not rounded. Corner surface area impacted on multiple corners",
            "surface": "Minor crease visible on both sides possibly. Wrinkle spanning vertically or horizontally approximately halfway across card clearly visible. Larger staining areas on front, multiple larger areas on back. Water damage over larger portion",
            "edges": "Edge surface wear evident with dirtiness to underlying stock"
        },
        3.5: {
            "overall": "Card with very heavy damage and all corners rounded",
            "centering": "Image centered within ~87.5/12.5 on front. Back may show tiny sliver of border but not miscut",
            "corners": "All four corners rounded. All aspects of corners worsen. Bends slightly larger, dings more visible, corner surface further impacted",
            "surface": "Light wrinkle spanning approximately three-quarters of back horizontally. Multiple minor creases potentially visible. Scuffing more severe, surface on back may be worn away hindering ability to read bio or stats",
            "edges": "All above defects persist. Noticeable areas of fill visible from excessive wear and handling"
        },
        3.0: {
            "overall": "Card with extreme wear and four rounded corners bordering extreme",
            "centering": "Image centered within ~90/10 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Four rounded corners bordering on extreme rounding where roundness appears outside corner area. Corner fraying becomes 'dirty' as underlying stock exposed for significant time. Significant bends causing multiple corners to display severe surface defects",
            "surface": "Heavier wrinkles or creases present. Just one wrinkle spanning horizontally across card visible. May be wrinkle spanning approximately three-quarters of back vertically. Most card gloss now gone",
            "edges": "All edge defects worsen. Significant fill and fray artifacts, severe notches, large chipping areas, dirtiness to underlying stock, and roughness present"
        },
        2.5: {
            "overall": "Card with severe damage throughout and extreme corner rounding",
            "centering": "Image centered within ~92.5/7.5 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Up to four rounded corners showing extreme rounding. Roundness gets outside corner areas, impacting card edges",
            "surface": "Wrinkles and creases become heavier. Wrinkle spanning length of card vertically present. Significant print defects, stains, focus issues. Scuffing to point where word or number worn away on back or parts of image become blurry or unrecognizable on front",
            "edges": "All defects above present, but aspects of one or more creeping deeper into card surface from one edge, impacting overall appeal"
        },
        2.0: {
            "overall": "Card with major structural issues and extreme corner rounding",
            "centering": "Image centered within ~95/5 on front. Back may show tiny sliver of border but not miscut",
            "corners": "All four corners showing extreme rounding and dirtiness",
            "surface": "Multiple full-length wrinkles or heavier creases persist. May exhibit pinhole allowing light through puncture area. Minor area of glue on reverse",
            "edges": "All defects present, aspects creeping deeper into card surface from multiple edges, more severely impacting appeal. One edge may exhibit minor tear"
        },
        1.5: {
            "overall": "Card with integrity compromised and corners falling apart",
            "centering": "Image centered within ~98.33/1.67 on front. Back may show tiny sliver of border but not miscut",
            "corners": "Continued worsening of corner rounding. Corner may appear to be falling apart as stock is compromised and worn to point of hanging on by fiber",
            "surface": "Several characteristics mentioned above present. May exhibit staple holes allowing light through puncture areas. Scotch tape residue relegated to back",
            "edges": "All defects present, aspects creeping even deeper into card surface from all edges, severely impacting appeal. Portions of image may be worn away or obstructed. More significant tear to one edge or multiple minor tears"
        },
        1.0: {
            "overall": "Card in barely recognizable condition with misshaped corners",
            "centering": "Front and/or back may show tiny sliver of border, but not miscut or show portion of another card",
            "corners": "Corners not just rounded but misshaped. Parts of corners fallen off or torn off from excessive wear and handling",
            "surface": "Combination of any significant flaws mentioned above present. Tape or glue may be present on front",
            "edges": "All above defects present. Multiple portions of image worn away or obstructed by edge defects. Larger tear(s) present"
        }
    }
    
    @staticmethod
    def get_grade_from_score(total_score):
        """
        Get the grade information from a numerical score (100-1000)
        
        Args:
            total_score (int): Numerical score between 100-1000
            
        Returns:
            tuple: (numeric_grade, grade_name, description_dict)
        """
        total_score = max(100, min(1000, total_score))
        
        for min_score, max_score, numeric_grade, grade_name in PSAGradingCriteria.GRADE_RANGES:
            if min_score <= total_score <= max_score:
                # Handle special case for grade 10 which has two levels
                if numeric_grade == 10.0:
                    desc = PSAGradingCriteria.GRADE_DESCRIPTIONS[10.0][grade_name]
                    return numeric_grade, grade_name, desc
                else:
                    desc = PSAGradingCriteria.GRADE_DESCRIPTIONS[numeric_grade]
                    return numeric_grade, grade_name, desc
        
        # Fallback
        return 1.0, "POOR", PSAGradingCriteria.GRADE_DESCRIPTIONS[1.0]
    
    @staticmethod
    def format_description(description):
        """
        Format description for display - converts dict to string if needed
        
        Args:
            description: Either a string or dict with detailed criteria
            
        Returns:
            str: Formatted description string
        """
        if isinstance(description, dict):
            # Return the overall description
            return description.get('overall', str(description))
        return description
    
    @staticmethod
    def get_detailed_criteria(description):
        """
        Get detailed criteria from description if available
        
        Args:
            description: Either a string or dict with detailed criteria
            
        Returns:
            dict: Dictionary with detailed criteria or None
        """
        if isinstance(description, dict):
            return description
        return None
    
    @staticmethod
    def calculate_overall_grade(category_scores, weights=None):
        """
        Calculate overall grade based on category scores.
        
        Args:
            category_scores (dict): Dictionary with category names and scores (0-1000)
            weights (dict|None): Optional custom weight dict; falls back to CATEGORY_WEIGHTS
            
        Returns:
            int: Overall numerical score (100-1000)
        """
        if not category_scores:
            return 100

        effective_weights = weights if weights is not None else PSAGradingCriteria.CATEGORY_WEIGHTS
            
        weighted_sum = 0
        total_weight = 0
        
        for category, score in category_scores.items():
            if category in effective_weights:
                weight = effective_weights[category]
                weighted_sum += score * weight
                total_weight += weight
        
        if total_weight == 0:
            return 100
            
        overall_score = weighted_sum / total_weight
        
        # Round to nearest integer
        overall_score = round(overall_score)
        
        # Ensure score is within valid range
        overall_score = max(100, min(1000, overall_score))
        
        return overall_score


class CardGrader:
    """Main class for grading sports cards"""

    # Path to calibration file (sibling of this module inside project root)
    _CALIBRATION_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'training_data', 'calibration.json'
    )
    
    def __init__(self):
        self.criteria = PSAGradingCriteria()
        self._load_calibration()

    def _load_calibration(self):
        """Load calibrated weights and bias from training_data/calibration.json."""
        self.calibrated_weights = dict(PSAGradingCriteria.CATEGORY_WEIGHTS)  # defaults
        self.score_bias = 0.0
        self.calibration_meta = None
        try:
            if os.path.exists(self._CALIBRATION_PATH):
                with open(self._CALIBRATION_PATH, 'r') as f:
                    data = json.load(f)
                if 'category_weights' in data:
                    loaded = {k: float(v) for k, v in data['category_weights'].items()}
                    # Only accept if all 4 categories present and sane
                    cats = {'corners', 'edges', 'surface', 'centering'}
                    if cats.issubset(loaded.keys()):
                        self.calibrated_weights = loaded
                if 'score_bias' in data:
                    self.score_bias = float(data['score_bias'])
                self.calibration_meta = data
        except Exception:
            pass  # silently fall back to defaults
    
    def analyze_corners(self, corner_data):
        """
        Analyze corner condition using the detailed corners grading criteria
        
        Based on precise corner grading scale:
        - PRISTINE (990-1000): Virtually flawless, no visible wear
        - GEM MINT (950-989): 4 sharp corners, minor fill/fray, light touch on reverse
        - MINT (900-949): Sharp/square, up to 2 light touches on front
        - And so on through all 19 grade levels
        
        Args:
            corner_data (dict): Data about corner condition including:
                - sharpness (0-10): Overall corner sharpness
                - worn_corners (0-4): Number of corners showing wear
                - rounding_level (0-10): Degree of corner rounding (0=none, 10=extreme)
                - fraying (0-10): Degree of fraying visible
                - missing_stock (bool): Whether missing stock is present
                
        Returns:
            int: Corner score (100-1000)
        """
        sharpness = corner_data.get('sharpness', 5)  # 0-10 scale
        worn_corners = corner_data.get('worn_corners', 0)  # 0-4
        rounding_level = corner_data.get('rounding_level', 0)  # 0-10 scale
        fraying = corner_data.get('fraying', 0)  # 0-10 scale
        missing_stock = corner_data.get('missing_stock', False)
        
        # Start with base score from sharpness
        base_score = 100 + (sharpness / 10.0) * 900
        
        # Apply grading criteria based on corner conditions
        # PRISTINE (990-1000): Virtually flawless, no visible wear/fraying
        if worn_corners == 0 and sharpness >= 9.5 and fraying < 0.5 and rounding_level == 0:
            score = 995
            
        # GEM MINT (950-989): 4 sharp corners, minor artifacts, light touch on reverse
        elif worn_corners <= 1 and sharpness >= 9.0 and rounding_level == 0 and fraying < 2:
            score = 970
            
        # MINT (900-949): Sharp/square, up to 2 light touches on front, multiple on back
        elif worn_corners <= 2 and sharpness >= 8.0 and rounding_level <= 0.8:
            score = 925
            
        # NEAR MINT-MINT+ (850-899): Multiple light touches on front, small missing stock on back
        elif worn_corners <= 2 and sharpness >= 7.5 and rounding_level <= 1.5:
            if missing_stock:
                score = 860
            else:
                score = 875
                
        # NEAR MINT-MINT (800-849): Corner may start showing minor wear
        elif worn_corners <= 3 and sharpness >= 7.0 and rounding_level <= 2.5:
            score = 825
            
        # NEAR MINT+ (750-799): Corners lose sharpness, all 4 may have touches
        elif worn_corners <= 3 and sharpness >= 6.2 and rounding_level <= 3.5:
            score = 775
            
        # NEAR MINT (700-749): Corners square but showing fraying, slight bend possible
        elif worn_corners <= 4 and sharpness >= 5.5 and rounding_level <= 4.0:
            score = 725
            
        # EXCELLENT-MINT+ (650-699): Corner losing shape, 3-4 corners with significant fraying
        elif rounding_level <= 4 and (worn_corners >= 3 or fraying >= 6):
            score = 675
            
        # EXCELLENT-MINT (600-649): One corner showing slight rounding
        elif rounding_level <= 5 and worn_corners >= 2:
            score = 625
            
        # EXCELLENT+ (550-599): Very minor rounding on 1-2 corners
        elif rounding_level <= 6 and worn_corners >= 2:
            score = 575
            
        # EXCELLENT (500-549): Rounding of 1-2 corners more significant, all 4 lost squareness
        elif rounding_level <= 7 and worn_corners == 4:
            score = 525
            
        # VERY GOOD-EXCELLENT+ (450-499): Corner clearly rounded with wear/fraying
        elif rounding_level <= 8 and worn_corners >= 2:
            score = 475
            
        # VERY GOOD-EXCELLENT (400-449): 2-3 corners clearly rounded
        elif rounding_level <= 8 and worn_corners >= 3:
            score = 425
            
        # VERY GOOD+ (350-399): All four corners rounded
        elif rounding_level <= 9 and worn_corners == 4:
            score = 375
            
        # VERY GOOD (300-349): Four rounded corners bordering on extreme
        elif rounding_level >= 9 and worn_corners == 4:
            score = 325
            
        # GOOD (200-249): All four corners extreme rounding and dirtiness
        elif rounding_level >= 9.5 and fraying >= 9:
            score = 225

        # GOOD+ (250-299): Extreme rounding getting outside corner areas
        elif rounding_level >= 9.5:
            score = 275
            
        # FAIR (150-199): Corners falling apart, stock hanging by fiber
        elif rounding_level >= 9.8:
            score = 175
            
        # POOR (100-149): Corners misshaped, parts fallen off
        else:
            score = int(max(
                250,
                base_score
                - (worn_corners * 35)
                - (rounding_level * 20)
                - (fraying * 15)
                - (80 if missing_stock else 0)
            ))
        
        # Adjust based on additional factors
        # Deduct for excessive fraying
        if fraying > 5:
            score -= (fraying - 5) * 20
            
        # Ensure score stays within valid range
        return max(100, min(1000, int(score)))
    
    def analyze_edges(self, edge_data):
        """
        Analyze edge condition using the detailed edges grading criteria
        
        Based on precise edges grading scale:
        - PRISTINE (990-1000): Virtually flawless edges, very minor fill/fray under high res
        - GEM MINT (950-989): Minor fill or fray, very minor edge surface wear
        - MINT (900-949): Visible but minor edge wear on 1-2 edges
        - And so on through all 19 grade levels
        
        Args:
            edge_data (dict): Data about edge condition including:
                - edge_whiteness (0-100): % of edge that's white/chipped
                - roughness (0-10): Edge roughness scale
                - notch_count (0-10): Number/severity of notches
                - lifting (0-10): Degree of edge lifting
                - tears (0-10): Presence and severity of tears
                - dirtiness (0-10): Dirtiness of underlying stock
                
        Returns:
            int: Edge score (100-1000)
        """
        whiteness = edge_data.get('edge_whiteness', 0)  # 0-100 (% of edge that's white/chipped)
        roughness = edge_data.get('roughness', 0)  # 0-10 scale
        notch_count = edge_data.get('notch_count', 0)  # 0-10 scale
        lifting = edge_data.get('lifting', 0)  # 0-10 scale
        tears = edge_data.get('tears', 0)  # 0-10 scale
        dirtiness = edge_data.get('dirtiness', 0)  # 0-10 scale
        
        # PRISTINE (990-1000): Virtually flawless edges
        if whiteness < 1 and roughness < 0.5 and notch_count == 0 and tears == 0:
            score = 995
            
        # GEM MINT (950-989): Minor fill or fray, very minor edge surface wear
        elif whiteness < 3 and roughness < 1.5 and notch_count == 0 and tears == 0:
            score = 970
            
        # MINT (900-949): Visible but minor edge wear on 1-2 edges
        elif whiteness < 8 and roughness < 3 and notch_count == 0 and tears == 0:
            score = 925
            
        # NEAR MINT-MINT+ (850-899): Visible edge wear or light chipping on multiple edges
        elif whiteness < 15 and roughness < 4 and notch_count == 0 and lifting < 2:
            score = 875
            
        # NEAR MINT-MINT (800-849): Edge wear and minor chipping on all 4 edges
        elif whiteness < 20 and roughness < 5 and notch_count == 0 and lifting < 3:
            score = 825
            
        # NEAR MINT+ (750-799): Edge wear/chipping worsen, lifting on edges, rougher
        elif whiteness < 25 and roughness < 6 and notch_count == 0 and lifting < 5:
            score = 775
            
        # NEAR MINT (700-749): Minor notch might be visible, lifting to all 4 edges
        elif whiteness < 30 and roughness < 7 and notch_count <= 1 and lifting < 7:
            score = 725
            
        # EXCELLENT-MINT+ (650-699): Minor notch on 2 edges, fray clearly visible
        elif whiteness < 35 and roughness < 7.5 and notch_count <= 2 and tears == 0:
            score = 675
            
        # EXCELLENT-MINT (600-649): Minor notches on 3+ edges or 1 severe notch
        elif whiteness < 40 and roughness < 8 and notch_count <= 4 and tears == 0:
            score = 625
            
        # EXCELLENT+ (550-599): Severe notch on 2 edges, larger chipping on multiple edges
        elif whiteness < 45 and roughness < 8.5 and notch_count <= 5 and tears == 0:
            score = 575
            
        # EXCELLENT (500-549): Notches and chipping on same edges, significant impact
        elif whiteness < 50 and roughness < 9 and notch_count <= 6 and tears == 0:
            score = 525
            
        # VERY GOOD-EXCELLENT+ (450-499): Roughness worsens, notches/chipping on multiple edges
        elif whiteness < 55 and roughness < 9.5 and tears < 1:
            score = 475
            
        # VERY GOOD-EXCELLENT (400-449): Edge surface wear evident, dirtiness to stock
        elif whiteness < 60 and dirtiness < 7 and tears < 2:
            score = 425
            
        # VERY GOOD+ (350-399): All above persist, noticeable fill areas from excessive wear
        elif whiteness < 65 and dirtiness < 8 and tears < 3:
            score = 375
            
        # VERY GOOD (300-349): All defects worsen significantly
        elif whiteness < 70 and dirtiness < 9 and tears < 4:
            score = 325
            
        # GOOD+ (250-299): Defects creeping deeper into surface from one edge
        elif whiteness < 75 and tears < 5:
            score = 275
            
        # GOOD (200-249): Defects creeping deeper from multiple edges, minor tear
        elif whiteness < 80 and tears < 6:
            score = 225
            
        # FAIR (150-199): Defects creeping even deeper from all edges, significant tear
        elif whiteness < 85 and tears < 8:
            score = 175
            
        # POOR (100-149): Multiple portions of image worn away, larger tears
        else:
            score = 125
        
        # Apply additional deductions based on severity
        # Deduct for excessive roughness
        if roughness > 7:
            score -= (roughness - 7) * 15
            
        # Deduct for tears (major defect)
        if tears > 0:
            score -= tears * 30
            
        # Deduct for excessive dirtiness
        if dirtiness > 5:
            score -= (dirtiness - 5) * 20
        
        # Ensure score stays within valid range
        return max(100, min(1000, int(score)))
    
    def analyze_surface(self, surface_data):
        """
        Analyze surface condition using the detailed surface grading criteria
        
        Based on precise surface grading scale:
        - PRISTINE (990-1000): Flawless surface with only NHODs
        - GEM MINT (950-989): Extremely attractive, slight print imperfection, very minor defect
        - MINT (900-949): Larger pit, 2-3 small pits, longer scratch not penetrating gloss
        - And so on through all 19 grade levels
        
        Args:
            surface_data (dict): Data about surface condition including:
                - scratch_count (0-20): Number of scratches
                - scratches_penetrate_gloss (bool): Whether scratches penetrate gloss
                - pit_count (0-20): Number of pits/defects
                - pit_size (0-10): Size of pits (0=none, 10=very large)
                - crease_count (0-10): Number of creases
                - wrinkle_count (0-10): Number of wrinkles
                - wrinkle_length (0-10): Length of wrinkles (0=none, 10=full length)
                - stain_count (0-10): Number of stains
                - water_damage (0-10): Degree of water damage
                - print_defects (0-10): Number/severity of print defects
                - gloss_loss (0-10): Loss of original gloss (0=perfect, 10=all gone)
                - dent_count (0-10): Number of dents
                - scuffing (0-10): Degree of scuffing
                
        Returns:
            int: Surface score (100-1000)
        """
        scratches = surface_data.get('scratch_count', 0)
        scratches_penetrate = surface_data.get('scratches_penetrate_gloss', False)
        pit_count = surface_data.get('pit_count', 0)
        pit_size = surface_data.get('pit_size', 0)
        creases = surface_data.get('crease_count', 0)
        wrinkles = surface_data.get('wrinkle_count', 0)
        wrinkle_length = surface_data.get('wrinkle_length', 0)
        stains = surface_data.get('stain_count', 0)
        water_damage = surface_data.get('water_damage', 0)
        print_defects = surface_data.get('print_defects', 0)
        gloss_loss = surface_data.get('gloss_loss', 0)
        dents = surface_data.get('dent_count', 0)
        scuffing = surface_data.get('scuffing', 0)

        defect_index = (
            (scratches * 0.8) +
            (creases * 4.0) +
            (wrinkles * 1.5) +
            (wrinkle_length * 1.2) +
            (stains * 2.0) +
            (water_damage * 2.5) +
            (print_defects * 1.2) +
            (gloss_loss * 0.8) +
            (dents * 1.2) +
            (scuffing * 1.0) +
            (pit_count * 0.8) +
            (pit_size * 0.8)
        )
        
        # PRISTINE (990-1000): Flawless surface, only NHODs
        if (scratches == 0 and pit_count == 0 and creases == 0 and wrinkles == 0 and 
            stains == 0 and dents == 0 and print_defects < 0.5):
            score = 995
            
        # GEM MINT (950-989): Extremely attractive, slight print imperfection, very minor defect
        elif (pit_count <= 1 and pit_size <= 2 and scratches <= 1 and not scratches_penetrate and
              creases == 0 and wrinkles == 0 and print_defects <= 2):
            score = 970
            
        # MINT (900-949): Larger/deeper pit, 2-3 small pits, longer scratch not penetrating gloss
        elif (pit_count <= 3 and scratches <= 2 and creases == 0 and 
              wrinkles == 0 and print_defects <= 4):
            score = 925
            
        # NEAR MINT-MINT+ (850-899): Multiple surface defects, small scratch penetrates gloss
        elif (scratches <= 4 and creases == 0 and wrinkles == 0 and 
              scuffing <= 2 and print_defects <= 6):
            score = 875
            
        # NEAR MINT-MINT (800-849): Several defects present, minor roller line possible
        elif (scratches <= 6 and creases == 0 and wrinkles == 0 and 
              print_defects <= 8 and dents <= 1):
            score = 825
            
        # NEAR MINT+ (750-799): Very minor dent on front, multiple visible defects
        elif (dents <= 1 and creases == 0 and wrinkles <= 1 and wrinkle_length <= 2):
            score = 775
            
        # NEAR MINT (700-749): Minor dent impacts front and back, multiple print dots
        elif (dents <= 2 and creases == 0 and wrinkles <= 1 and print_defects <= 12):
            score = 725
            
        # EXCELLENT-MINT+ (650-699): Very short wrinkle on back, small water damage on back
        elif (wrinkles <= 2 and wrinkle_length <= 3 and creases == 0 and 
              water_damage <= 2 and stains <= 1):
            score = 675
            
        # EXCELLENT-MINT (600-649): Longer wrinkle on back, light staining, larger dent
        elif (wrinkles <= 3 and wrinkle_length <= 5 and creases == 0 and 
              stains <= 2 and dents <= 3 and scuffing <= 5):
            score = 625
            
        # EXCELLENT+ (550-599): Small wrinkle on front, light staining on front
        elif (wrinkles <= 4 and creases == 0 and stains <= 3 and 
              water_damage <= 4 and gloss_loss <= 3):
            score = 575
            
        # EXCELLENT (500-549): Multiple small wrinkles on front, loss of gloss visible
        elif (wrinkles <= 6 and creases == 0 and stains <= 4 and 
              gloss_loss <= 5 and scuffing <= 7):
            score = 525
            
        # VERY GOOD-EXCELLENT+ (450-499): Minor crease visible breaking stock
        elif (creases <= 1 and wrinkles <= 8 and wrinkle_length <= 7):
            score = 475
            
        # VERY GOOD-EXCELLENT (400-449): Minor crease on both sides, wrinkle halfway across
        elif (creases <= 2 and wrinkles <= 10 and wrinkle_length <= 8 and 
              stains <= 6 and water_damage <= 7):
            score = 425
            
        # VERY GOOD+ (350-399): Light wrinkle 3/4 of back, multiple minor creases
        elif (wrinkles <= 12 and wrinkle_length <= 9 and creases <= 3 and 
              scuffing <= 9):
            score = 375
            
        # VERY GOOD (300-349): Heavier wrinkles/creases, wrinkle spanning horizontally, most gloss gone
        elif (wrinkles <= 15 and wrinkle_length <= 9.5 and creases <= 4 and 
              gloss_loss >= 7):
            score = 325
            
        # GOOD+ (250-299): Wrinkle spanning length vertically, significant defects
        elif (wrinkle_length >= 9 and creases <= 6 and scuffing >= 8):
            score = 275
            
        # GOOD (200-249): Multiple full-length wrinkles, pinhole or glue on reverse
        elif (wrinkles >= 15 or creases >= 5):
            score = 225
            
        # FAIR (150-199): Several characteristics, staple holes, tape residue on back
        elif (wrinkles >= 18 or creases >= 7):
            score = 175
            
        # POOR (100-149): Combination of significant flaws, tape/glue on front
        else:
            score = int(max(180, 980 - (defect_index * 32)))
        
        # Apply additional deductions
        # Heavy penalty for creases (major defect)
        if creases > 0:
            score -= creases * 80
            
        # Deduct for wrinkles based on length
        if wrinkles > 0:
            score -= wrinkles * 10
            score -= wrinkle_length * 15
            
        # Deduct for stains and water damage
        if stains > 0:
            score -= stains * 30
        if water_damage > 0:
            score -= water_damage * 35
            
        # Deduct for gloss loss
        if gloss_loss > 5:
            score -= (gloss_loss - 5) * 25
            
        # Deduct for excessive scuffing
        if scuffing > 5:
            score -= (scuffing - 5) * 20
        
        # Ensure score stays within valid range
        return max(100, min(1000, int(score)))
    
    def analyze_centering(self, centering_data, side='front'):
        """
        Analyze centering using the custom grading criteria
        
        Args:
            centering_data (dict): Data about centering
            
        Returns:
            int: Centering score (100-1000)
        """
        left_right_ratio = centering_data.get('left_right_ratio', 50.0)  # % (50 is perfect)
        top_bottom_ratio = centering_data.get('top_bottom_ratio', 50.0)  # % (50 is perfect)
        
        # Calculate deviation from perfect centering (50/50)
        lr_deviation = abs(50.0 - left_right_ratio)
        tb_deviation = abs(50.0 - top_bottom_ratio)
        
        max_deviation = max(lr_deviation, tb_deviation)
        
        # PSA centering standards differ significantly for front vs back
        # Front: tight (55/45 = deviation of 5 for PSA 10)
        # Back: lenient (70/30 = deviation of 20 for PSA 10)
        if side == 'back':
            thresholds = [
                (20,    1000),  # PSA PRISTINE: 70/30
                (25,     970),  # PSA GEM MINT: 75/25
                (30,     920),  # PSA MINT: 80/20
                (32.5,   870),  # PSA NM-MT+
                (35,     820),  # PSA NM-MT
                (37.5,   770),  # PSA NM+
                (40,     720),  # PSA NM
                (42.5,   670),  # PSA EX-MT+
                (45,     620),  # PSA EX-MT
                (47.5,   570),  # PSA EX+
                (48.33,  520),  # PSA EX
                (49.0,   470),  # PSA VG-EX+
            ]
        else:
            thresholds = [
                (1,     1000),  # PSA PRISTINE: 51/49
                (5,      970),  # PSA GEM MINT: 55/45
                (10,     920),  # PSA MINT: 60/40
                (12.5,   870),  # PSA NM-MT+: 62.5/37.5
                (15,     820),  # PSA NM-MT: 65/35
                (17.5,   770),  # PSA NM+: 67.5/32.5
                (20,     720),  # PSA NM: 70/30
                (22.5,   670),  # PSA EX-MT+
                (25,     620),  # PSA EX-MT
                (27.5,   570),  # PSA EX+
                (30,     520),  # PSA EX
                (32.5,   470),  # PSA VG-EX+
                (35,     420),  # PSA VG-EX
                (37.5,   370),  # PSA VG+
                (40,     320),  # PSA VG
                (42.5,   270),  # PSA GOOD+
                (45,     220),  # PSA GOOD
                (48.33,  170),  # PSA FAIR
            ]

        score = 120  # POOR fallback
        for dev_limit, dev_score in thresholds:
            if max_deviation <= dev_limit:
                score = dev_score
                break
        
        return int(score)
    
    def grade_card(self, front_analysis, back_analysis):
        """
        Grade a card based on front and back analysis
        
        Args:
            front_analysis (dict): Analysis results for front of card
            back_analysis (dict): Analysis results for back of card
            
        Returns:
            dict: Grading results with overall grade and details
        """
        # Analyze both sides
        front_scores = self._analyze_side(front_analysis, 'front')
        back_scores = self._analyze_side(back_analysis, 'back')
        
        # Take the worse score for each category (card is only as good as its worst side)
        combined_scores = {}
        for category in self.criteria.CATEGORY_WEIGHTS.keys():
            front_score = front_scores.get(category, 100)
            back_score = back_scores.get(category, 100)
            worse_score = min(front_score, back_score)
            better_score = max(front_score, back_score)
            combined_scores[category] = int(round((worse_score * 0.7) + (better_score * 0.3)))
        
        # Calculate overall numerical score using calibrated category weights
        overall_score = self.criteria.calculate_overall_grade(
            combined_scores, weights=self.calibrated_weights
        )
        # Apply learned score bias (shifts all predictions up or down)
        overall_score = max(100, min(1000, round(overall_score + self.score_bias)))
        
        # Get grade information from the score
        numeric_grade, grade_name, description = self.criteria.get_grade_from_score(overall_score)
        
        return {
            'score': overall_score,
            'grade': numeric_grade,
            'grade_name': grade_name,
            'description': description,
            'category_scores': combined_scores,
            'front_scores': front_scores,
            'back_scores': back_scores,
            'details': self._generate_grading_details(combined_scores, numeric_grade, grade_name)
        }
    
    def _analyze_side(self, analysis_data, side_name):
        """Analyze one side of the card"""
        scores = {
            'corners': self.analyze_corners(analysis_data.get('corners', {})),
            'edges': self.analyze_edges(analysis_data.get('edges', {})),
            'surface': self.analyze_surface(analysis_data.get('surface', {})),
            'centering': self.analyze_centering(analysis_data.get('centering', {}), side=side_name)
        }
        return scores
    
    def _generate_grading_details(self, scores, final_grade, grade_name):
        """Generate detailed explanation of the grade"""
        details = []
        
        for category, score in scores.items():
            category_name = category.replace('_', ' ').title()
            # Map score to description
            _, cat_grade_name, _ = self.criteria.get_grade_from_score(score)
            details.append(f"{category_name}: {score}/1000 ({cat_grade_name})")
        
        # Add overall assessment based on grade level
        if final_grade >= 9.5:
            assessment = "This card is in exceptional condition approaching perfection."
        elif final_grade >= 8.5:
            assessment = "This card is in excellent condition with minimal wear."
        elif final_grade >= 7.0:
            assessment = "This card is in good condition with minor to moderate wear."
        elif final_grade >= 5.0:
            assessment = "This card shows moderate to significant wear but remains collectible."
        elif final_grade >= 3.0:
            assessment = "This card shows heavy wear and damage."
        else:
            assessment = "This card shows severe damage and structural issues."
        
        details.append(f"\nOverall Assessment: {assessment}")
        
        return "\n".join(details)


# Example usage
if __name__ == "__main__":
    grader = CardGrader()
    
    # Example: Grade a card with specific condition data
    front_data = {
        'corners': {'sharpness': 9.0, 'worn_corners': 1},
        'edges': {'edge_whiteness': 8, 'roughness': 2},
        'surface': {'scratch_count': 2, 'crease_count': 0, 'stain_count': 0, 'print_defects': 0},
        'centering': {'left_right_ratio': 52, 'top_bottom_ratio': 48}
    }
    
    back_data = {
        'corners': {'sharpness': 8.5, 'worn_corners': 1},
        'edges': {'edge_whiteness': 10, 'roughness': 2},
        'surface': {'scratch_count': 1, 'crease_count': 0, 'stain_count': 0, 'print_defects': 0},
        'centering': {'left_right_ratio': 50, 'top_bottom_ratio': 50}
    }
    
    result = grader.grade_card(front_data, back_data)
    
    print(f"Numerical Score: {result['score']}/1000")
    print(f"Grade: {result['grade']} - {result['grade_name']}")
    print(f"Description: {result['description']}")
    print(f"\nDetailed Scores:")
    print(result['details'])
    
    result = grader.grade_card(front_data, back_data)
    
    print(f"PSA Grade: {result['grade']}")
    print(f"Description: {result['description']}")
    print(f"\nDetailed Scores:")
    print(result['details'])
