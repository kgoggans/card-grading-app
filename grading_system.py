"""
PSA Grading System Module

This module implements the PSA (Professional Sports Authenticator) grading standards
for sports cards. PSA uses a 1-10 scale with half-point increments.

PSA Grading Scale:
- PSA 10 (Gem Mint): Perfect card with no visible flaws
- PSA 9 (Mint): Near-perfect with minimal wear
- PSA 8 (NM-MT): Very slight wear on corners/edges
- PSA 7 (Near Mint): Minor defects visible
- PSA 6 (EX-MT): Noticeable wear but still attractive
- PSA 5 (EX): Moderate wear on corners/edges
- PSA 4 (VG-EX): Significant wear but no major creases
- PSA 3 (VG): Heavy wear with possible light creases
- PSA 2 (Good): Very heavy wear with creases
- PSA 1 (Poor): Extremely poor condition
"""

class PSAGradingCriteria:
    """Defines the PSA grading criteria and weights"""
    
    # Grading categories and their weights
    CATEGORY_WEIGHTS = {
        'corners': 0.25,      # Corner wear/damage
        'edges': 0.20,        # Edge wear/chipping
        'surface': 0.25,      # Surface scratches/wear
        'centering': 0.15,    # Centering of image
        'print_quality': 0.15 # Print defects/quality
    }
    
    # Grade descriptions
    GRADE_DESCRIPTIONS = {
        10: "Gem Mint - Perfect card with no visible flaws, sharp corners, perfect centering",
        9: "Mint - Near-perfect with only minimal wear under close inspection",
        8: "Near Mint-Mint - Very slight wear on corners or edges, minimal surface issues",
        7: "Near Mint - Minor defects visible, slight corner/edge wear",
        6: "Excellent-Mint - Noticeable wear but still attractive, minor surface issues",
        5: "Excellent - Moderate wear on corners and edges, some surface wear",
        4: "Very Good-Excellent - Significant wear but no major creases, visible surface issues",
        3: "Very Good - Heavy wear with possible light creases, noticeable surface damage",
        2: "Good - Very heavy wear with creases, significant surface damage",
        1: "Poor - Extremely poor condition with major damage"
    }
    
    @staticmethod
    def get_grade_description(grade):
        """Get the description for a given grade"""
        return PSAGradingCriteria.GRADE_DESCRIPTIONS.get(grade, "Invalid grade")
    
    @staticmethod
    def calculate_overall_grade(category_scores):
        """
        Calculate overall grade based on category scores
        
        Args:
            category_scores (dict): Dictionary with category names and scores (0-10)
            
        Returns:
            float: Overall grade (1-10)
        """
        if not category_scores:
            return 1.0
            
        weighted_sum = 0
        total_weight = 0
        
        for category, score in category_scores.items():
            if category in PSAGradingCriteria.CATEGORY_WEIGHTS:
                weight = PSAGradingCriteria.CATEGORY_WEIGHTS[category]
                weighted_sum += score * weight
                total_weight += weight
        
        if total_weight == 0:
            return 1.0
            
        overall_grade = weighted_sum / total_weight
        
        # Round to nearest 0.5
        overall_grade = round(overall_grade * 2) / 2
        
        # Ensure grade is within valid range
        overall_grade = max(1.0, min(10.0, overall_grade))
        
        return overall_grade


class CardGrader:
    """Main class for grading sports cards"""
    
    def __init__(self):
        self.criteria = PSAGradingCriteria()
    
    def analyze_corners(self, corner_data):
        """
        Analyze corner condition
        
        Args:
            corner_data (dict): Data about corner condition
            
        Returns:
            float: Corner score (0-10)
        """
        # Scoring based on corner sharpness and wear
        sharpness = corner_data.get('sharpness', 5)  # 0-10 scale
        wear_count = corner_data.get('worn_corners', 0)  # 0-4
        
        score = sharpness
        
        # Deduct points for worn corners
        if wear_count == 0:
            score = max(score, 9.5)
        elif wear_count == 1:
            score = min(score, 8.5)
        elif wear_count == 2:
            score = min(score, 7.0)
        elif wear_count == 3:
            score = min(score, 5.0)
        else:  # All 4 corners worn
            score = min(score, 3.0)
        
        return max(1.0, min(10.0, score))
    
    def analyze_edges(self, edge_data):
        """
        Analyze edge condition
        
        Args:
            edge_data (dict): Data about edge condition
            
        Returns:
            float: Edge score (0-10)
        """
        whiteness = edge_data.get('edge_whiteness', 0)  # 0-100 (% of edge that's white/chipped)
        roughness = edge_data.get('roughness', 0)  # 0-10 scale
        
        score = 10.0
        
        # Deduct for edge whiteness (chipping)
        if whiteness < 5:
            score = 10.0
        elif whiteness < 10:
            score = 8.5
        elif whiteness < 20:
            score = 7.0
        elif whiteness < 30:
            score = 5.5
        else:
            score = 3.0
        
        # Deduct for roughness
        score -= roughness * 0.3
        
        return max(1.0, min(10.0, score))
    
    def analyze_surface(self, surface_data):
        """
        Analyze surface condition
        
        Args:
            surface_data (dict): Data about surface condition
            
        Returns:
            float: Surface score (0-10)
        """
        scratches = surface_data.get('scratch_count', 0)
        creases = surface_data.get('crease_count', 0)
        stains = surface_data.get('stain_count', 0)
        print_defects = surface_data.get('print_defects', 0)
        
        score = 10.0
        
        # Deduct for scratches
        if scratches == 0:
            pass
        elif scratches <= 2:
            score -= 1.0
        elif scratches <= 5:
            score -= 2.5
        else:
            score -= 4.0
        
        # Deduct heavily for creases
        score -= creases * 2.5
        
        # Deduct for stains
        score -= stains * 1.5
        
        # Deduct for print defects
        score -= print_defects * 1.0
        
        return max(1.0, min(10.0, score))
    
    def analyze_centering(self, centering_data):
        """
        Analyze centering
        
        Args:
            centering_data (dict): Data about centering
            
        Returns:
            float: Centering score (0-10)
        """
        left_right_ratio = centering_data.get('left_right_ratio', 50.0)  # % (50 is perfect)
        top_bottom_ratio = centering_data.get('top_bottom_ratio', 50.0)  # % (50 is perfect)
        
        # Calculate deviation from perfect centering (50/50)
        lr_deviation = abs(50.0 - left_right_ratio)
        tb_deviation = abs(50.0 - top_bottom_ratio)
        
        max_deviation = max(lr_deviation, tb_deviation)
        
        # PSA centering standards
        if max_deviation <= 5:  # 55/45 or better
            score = 10.0
        elif max_deviation <= 10:  # 60/40
            score = 8.5
        elif max_deviation <= 15:  # 65/35
            score = 7.0
        elif max_deviation <= 20:  # 70/30
            score = 5.5
        elif max_deviation <= 25:  # 75/25
            score = 4.0
        else:
            score = 2.0
        
        return score
    
    def analyze_print_quality(self, print_data):
        """
        Analyze print quality
        
        Args:
            print_data (dict): Data about print quality
            
        Returns:
            float: Print quality score (0-10)
        """
        focus = print_data.get('focus_score', 8.0)  # 0-10
        color_accuracy = print_data.get('color_accuracy', 8.0)  # 0-10
        registration = print_data.get('registration', 8.0)  # 0-10 (alignment of colors)
        
        # Average the print quality factors
        score = (focus + color_accuracy + registration) / 3.0
        
        return max(1.0, min(10.0, score))
    
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
            front_score = front_scores.get(category, 5.0)
            back_score = back_scores.get(category, 5.0)
            combined_scores[category] = min(front_score, back_score)
        
        # Calculate overall grade
        overall_grade = self.criteria.calculate_overall_grade(combined_scores)
        
        # Round to nearest integer for final PSA grade
        final_grade = round(overall_grade)
        
        return {
            'grade': final_grade,
            'grade_decimal': overall_grade,
            'description': self.criteria.get_grade_description(final_grade),
            'category_scores': combined_scores,
            'front_scores': front_scores,
            'back_scores': back_scores,
            'details': self._generate_grading_details(combined_scores, final_grade)
        }
    
    def _analyze_side(self, analysis_data, side_name):
        """Analyze one side of the card"""
        scores = {
            'corners': self.analyze_corners(analysis_data.get('corners', {})),
            'edges': self.analyze_edges(analysis_data.get('edges', {})),
            'surface': self.analyze_surface(analysis_data.get('surface', {})),
            'centering': self.analyze_centering(analysis_data.get('centering', {})),
            'print_quality': self.analyze_print_quality(analysis_data.get('print_quality', {}))
        }
        return scores
    
    def _generate_grading_details(self, scores, final_grade):
        """Generate detailed explanation of the grade"""
        details = []
        
        for category, score in scores.items():
            category_name = category.replace('_', ' ').title()
            if score >= 9.5:
                condition = "Excellent"
            elif score >= 8.0:
                condition = "Very Good"
            elif score >= 6.5:
                condition = "Good"
            elif score >= 5.0:
                condition = "Fair"
            else:
                condition = "Poor"
            
            details.append(f"{category_name}: {score:.1f}/10 ({condition})")
        
        # Add overall assessment
        if final_grade >= 9:
            assessment = "This card is in exceptional condition with minimal to no visible flaws."
        elif final_grade >= 7:
            assessment = "This card is in good condition with only minor wear."
        elif final_grade >= 5:
            assessment = "This card shows moderate wear but remains collectible."
        else:
            assessment = "This card shows significant wear and damage."
        
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
        'centering': {'left_right_ratio': 52, 'top_bottom_ratio': 48},
        'print_quality': {'focus_score': 9.0, 'color_accuracy': 9.0, 'registration': 9.0}
    }
    
    back_data = {
        'corners': {'sharpness': 8.5, 'worn_corners': 1},
        'edges': {'edge_whiteness': 10, 'roughness': 2},
        'surface': {'scratch_count': 1, 'crease_count': 0, 'stain_count': 0, 'print_defects': 0},
        'centering': {'left_right_ratio': 50, 'top_bottom_ratio': 50},
        'print_quality': {'focus_score': 9.0, 'color_accuracy': 8.5, 'registration': 9.0}
    }
    
    result = grader.grade_card(front_data, back_data)
    
    print(f"PSA Grade: {result['grade']}")
    print(f"Description: {result['description']}")
    print(f"\nDetailed Scores:")
    print(result['details'])
