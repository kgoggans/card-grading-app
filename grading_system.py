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
    
    # Grade descriptions based on the provided criteria
    GRADE_DESCRIPTIONS = {
        10.0: {
            "PRISTINE": "Virtually flawless corners, edges, surface, and centering. Only non-human observable defects allowed.",
            "GEM MINT": "4 sharp corners with minor artifacts. Extremely attractive surface with possible slight print imperfection. Minor fill or fray on edges."
        },
        9.0: "Sharp square corners with light touches visible. Larger/deeper pits may be present. Visible but minor edge wear on 1-2 edges.",
        8.5: "Multiple light corner touches on front. Multiple surface defects presenting. Visible edge wear or light chipping on multiple edges.",
        8.0: "Minor corner wear starting to show. Several surface defects present. Edge wear and minor chipping on all four edges.",
        7.5: "Corners showing more wear, losing sharpness. Very minor dent possible on front. Edge wear and chipping worsening.",
        7.0: "Corners square but multiple showing fraying. Minor dent may impact front and back. Minor notch may be visible on edges.",
        6.5: "Corner may lose shape due to excessive wear. Short wrinkle possible on back under high-res. Minor notch on two edges.",
        6.0: "One corner may show slight rounding. Longer wrinkle present on back. Minor notches on three or more edges.",
        5.5: "Very minor corner rounding on 1-2 corners. Small wrinkle on front possible. Severe notch on two edges.",
        5.0: "Rounding of 1-2 corners more significant. Multiple small wrinkles on front. Notches and chipping visible on same edges.",
        4.5: "Corner clearly rounded with wear/fraying. Minor crease visible breaking stock. Roughness of edges worsening significantly.",
        4.0: "2-3 corners clearly rounded with wear. Minor crease visible on both sides. Edge wear evident with dirtiness to stock.",
        3.5: "All four corners rounded. Light wrinkle spanning 3/4 of back. Multiple minor creases potentially visible.",
        3.0: "Four rounded corners bordering on extreme. Heavier wrinkles or creases present. Significant fill and fray on edges.",
        2.5: "Up to four corners with extreme rounding. Wrinkle spanning length of card vertically. Defects creeping deeper from edges.",
        2.0: "All four corners showing extreme rounding and dirtiness. Multiple full-length wrinkles or heavier creases. Minor tear on edge.",
        1.5: "Corners appearing to fall apart. Staple holes allowing light through. Multiple minor tears to edges.",
        1.0: "Corners misshaped, parts fallen off. Tape or glue on front. Multiple portions of image worn away or obstructed."
    }
    
    @staticmethod
    def get_grade_from_score(total_score):
        """
        Get the grade information from a numerical score (100-1000)
        
        Args:
            total_score (int): Numerical score between 100-1000
            
        Returns:
            tuple: (numeric_grade, grade_name, description)
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
    def get_grade_description(grade, grade_name=None):
        """Get the description for a given grade"""
        if grade == 10.0 and grade_name:
            return PSAGradingCriteria.GRADE_DESCRIPTIONS[10.0].get(grade_name, "")
        return PSAGradingCriteria.GRADE_DESCRIPTIONS.get(grade, "Invalid grade")
    
    @staticmethod
    def calculate_overall_grade(category_scores):
        """
        Calculate overall grade based on category scores
        
        Args:
            category_scores (dict): Dictionary with category names and scores (0-1000)
            
        Returns:
            int: Overall numerical score (100-1000)
        """
        if not category_scores:
            return 100
            
        weighted_sum = 0
        total_weight = 0
        
        for category, score in category_scores.items():
            if category in PSAGradingCriteria.CATEGORY_WEIGHTS:
                weight = PSAGradingCriteria.CATEGORY_WEIGHTS[category]
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
    
    def __init__(self):
        self.criteria = PSAGradingCriteria()
    
    def analyze_corners(self, corner_data):
        """
        Analyze corner condition using the custom grading criteria
        
        Args:
            corner_data (dict): Data about corner condition
            
        Returns:
            int: Corner score (100-1000)
        """
        # Base scoring on corner sharpness and wear
        sharpness = corner_data.get('sharpness', 5)  # 0-10 scale
        worn_corners = corner_data.get('worn_corners', 0)  # 0-4
        
        # Start with a base score based on sharpness (map 0-10 to 100-1000)
        score = 100 + (sharpness / 10.0) * 900
        
        # Adjust based on worn corners according to criteria
        if worn_corners == 0:
            # Virtually flawless - PRISTINE to GEM MINT range
            score = max(score, 950)
        elif worn_corners == 1:
            # Light corner touches - MINT to NEAR MINT-MINT+ range
            score = min(score, 900)
            score = max(score, 850)
        elif worn_corners == 2:
            # Multiple corners showing wear - NEAR MINT to NEAR MINT+ range
            score = min(score, 799)
            score = max(score, 700)
        elif worn_corners == 3:
            # Significant corner wear - EXCELLENT-MINT+ to EXCELLENT range
            score = min(score, 649)
            score = max(score, 500)
        else:  # All 4 corners worn
            # All corners showing significant damage - VERY GOOD or below
            score = min(score, 449)
        
        return max(100, min(1000, int(score)))
    
    def analyze_edges(self, edge_data):
        """
        Analyze edge condition using the custom grading criteria
        
        Args:
            edge_data (dict): Data about edge condition
            
        Returns:
            int: Edge score (100-1000)
        """
        whiteness = edge_data.get('edge_whiteness', 0)  # 0-100 (% of edge that's white/chipped)
        roughness = edge_data.get('roughness', 0)  # 0-10 scale
        
        score = 1000
        
        # Deduct based on edge whiteness (chipping)
        if whiteness < 2:
            # Virtually flawless - PRISTINE range
            score = 1000
        elif whiteness < 5:
            # Minor fill or fray - GEM MINT range
            score = 970
        elif whiteness < 10:
            # Visible minor wear on 1-2 edges - MINT range
            score = 920
        elif whiteness < 15:
            # Visible wear on multiple edges - NEAR MINT-MINT+ range
            score = 870
        elif whiteness < 20:
            # Edge wear on all edges - NEAR MINT-MINT range
            score = 820
        elif whiteness < 25:
            # Edge wear worsening - NEAR MINT+ range
            score = 770
        elif whiteness < 30:
            # Minor notch visible - NEAR MINT range
            score = 720
        elif whiteness < 35:
            # Minor notch on two edges - EXCELLENT-MINT+ range
            score = 670
        elif whiteness < 40:
            # Notches on three or more edges - EXCELLENT-MINT range
            score = 620
        elif whiteness < 50:
            # Severe notching - EXCELLENT+ to EXCELLENT range
            score = 550
        else:
            # Severe edge damage - VERY GOOD or below
            score = 400
        
        # Deduct for roughness (more gradual impact)
        score -= roughness * 30
        
        return max(100, min(1000, int(score)))
    
    def analyze_surface(self, surface_data):
        """
        Analyze surface condition using the custom grading criteria
        
        Args:
            surface_data (dict): Data about surface condition
            
        Returns:
            int: Surface score (100-1000)
        """
        scratches = surface_data.get('scratch_count', 0)
        creases = surface_data.get('crease_count', 0)
        stains = surface_data.get('stain_count', 0)
        print_defects = surface_data.get('print_defects', 0)
        
        score = 1000
        
        # Deduct for scratches
        if scratches == 0:
            pass  # Pristine surface
        elif scratches <= 1:
            score -= 50  # Slight imperfection - GEM MINT
        elif scratches <= 2:
            score -= 100  # Larger pit or scratch - MINT
        elif scratches <= 3:
            score -= 150  # Multiple defects - NEAR MINT-MINT+
        elif scratches <= 5:
            score -= 200  # Several defects - NEAR MINT-MINT
        else:
            score -= 300  # Many defects
        
        # Deduct heavily for creases (major defect)
        if creases >= 1:
            # Presence of crease drops grade significantly
            score = min(score, 499)  # Max VERY GOOD-EXCELLENT+
            score -= creases * 100
        
        # Deduct for stains
        if stains > 0:
            score -= stains * 80
        
        # Deduct for print defects
        score -= print_defects * 40
        
        return max(100, min(1000, int(score)))
    
    def analyze_centering(self, centering_data):
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
        
        # Apply centering standards from the criteria
        if max_deviation <= 1:  # ~51/49
            score = 1000  # PRISTINE
        elif max_deviation <= 5:  # ~55/45
            score = 970  # GEM MINT
        elif max_deviation <= 10:  # ~60/40
            score = 920  # MINT
        elif max_deviation <= 12.5:  # ~62.5/37.5
            score = 870  # NEAR MINT-MINT+
        elif max_deviation <= 15:  # ~65/35
            score = 820  # NEAR MINT-MINT
        elif max_deviation <= 17.5:  # ~67.5/32.5
            score = 770  # NEAR MINT+
        elif max_deviation <= 20:  # ~70/30
            score = 720  # NEAR MINT
        elif max_deviation <= 22.5:  # ~72.5/27.5
            score = 670  # EXCELLENT-MINT+
        elif max_deviation <= 25:  # ~75/25
            score = 620  # EXCELLENT-MINT
        elif max_deviation <= 27.5:  # ~77.5/22.5
            score = 570  # EXCELLENT+
        elif max_deviation <= 30:  # ~80/20
            score = 520  # EXCELLENT
        elif max_deviation <= 32.5:  # ~82.5/17.5
            score = 470  # VERY GOOD-EXCELLENT+
        elif max_deviation <= 35:  # ~85/15
            score = 420  # VERY GOOD-EXCELLENT
        elif max_deviation <= 37.5:  # ~87.5/12.5
            score = 370  # VERY GOOD+
        elif max_deviation <= 40:  # ~90/10
            score = 320  # VERY GOOD
        elif max_deviation <= 42.5:  # ~92.5/7.5
            score = 270  # GOOD+
        elif max_deviation <= 45:  # ~95/5
            score = 220  # GOOD
        elif max_deviation <= 48.33:  # ~98.33/1.67
            score = 170  # FAIR
        else:
            score = 120  # POOR
        
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
            combined_scores[category] = min(front_score, back_score)
        
        # Calculate overall numerical score (100-1000)
        overall_score = self.criteria.calculate_overall_grade(combined_scores)
        
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
            'centering': self.analyze_centering(analysis_data.get('centering', {}))
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
