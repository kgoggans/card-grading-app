# Sports Card Grading App 🏆

An AI-powered web application that analyzes sports card images and provides PSA (Professional Sports Authenticator) grade estimates. Upload front and back photos of your cards to receive detailed condition assessments and grade predictions.

## Features

- **AI-Powered Analysis**: Advanced computer vision algorithms analyze card condition
- **PSA Grading Scale**: Estimates grades on the official 1-10 PSA scale
- **Comprehensive Evaluation**: Analyzes corners, edges, surface, centering, and print quality
- **Detailed Breakdowns**: Provides category-by-category scores and explanations
- **Web Interface**: Easy-to-use interface for uploading and viewing results
- **Consistent Grading**: Uses standardized criteria for reproducible results

## How It Works

### Grading Criteria

The app evaluates five key categories based on PSA standards:

1. **Corners (25% weight)**: Sharpness, wear, and rounding
2. **Edges (20% weight)**: Chipping, whitening, and roughness
3. **Surface (25% weight)**: Scratches, creases, stains, and print defects
4. **Centering (15% weight)**: Image placement and border balance
5. **Print Quality (15% weight)**: Focus, color accuracy, and registration

Each side of the card is analyzed separately, and the final grade uses the worse score for each category (a card is only as good as its worst side).

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/kgoggans/card-grading-app.git
cd card-grading-app
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to:
```
http://localhost:5000
```

## Usage

1. **Upload Images**: Click on the upload boxes to select front and back images of your card
2. **Grade Card**: Click the "Grade My Card" button to start the analysis
3. **View Results**: See your estimated PSA grade with detailed category scores and explanations

### Tips for Best Results

- Use high-resolution images (at least 800px on smallest side)
- Ensure good, even lighting without glare or shadows
- Capture the entire card with borders visible
- Use a contrasting background
- Avoid flash photography that creates glare
- Keep cards clean and free of dust/fingerprints

## PSA Grading Scale

| Grade | Designation | Description |
|-------|-------------|-------------|
| 10 | Gem Mint | Perfect card with no visible flaws |
| 9 | Mint | Near-perfect with minimal wear |
| 8 | Near Mint-Mint | Very slight wear on corners/edges |
| 7 | Near Mint | Minor defects visible |
| 6 | Excellent-Mint | Noticeable wear but attractive |
| 5 | Excellent | Moderate wear on corners/edges |
| 4 | Very Good-Excellent | Significant wear, no major creases |
| 3 | Very Good | Heavy wear with possible light creases |
| 2 | Good | Very heavy wear with creases |
| 1 | Poor | Extremely poor condition |

## Accuracy and Consistency

### Achieving Accurate Grades

The accuracy of the AI grading depends on several factors:

1. **Image Quality**: Higher resolution images provide more detail for analysis
2. **Lighting Conditions**: Consistent, even lighting is crucial
3. **Camera Angle**: Straight-on shots work best
4. **Card Positioning**: Card should fill most of the frame

### Consistency

For consistent results across multiple cards:

- Use the same photography setup (lighting, camera, angle)
- Maintain consistent image resolution
- Use the same background for all photos
- Photograph in the same environment

### Limitations

**Important**: This is an AI estimate and NOT an official PSA grade. Consider these limitations:

- Cannot detect all physical defects (thickness variations, actual creases vs shadows)
- Image quality directly impacts accuracy
- Some card-specific issues may not be detectable in photos
- No authentication or verification of card legitimacy
- For official grading, submit directly to PSA

## Project Structure

```
card-grading-app/
├── app.py                  # Flask web application
├── grading_system.py       # PSA grading logic and criteria
├── image_analysis.py       # Computer vision analysis
├── requirements.txt        # Python dependencies
├── templates/
│   ├── index.html         # Main upload interface
│   └── about.html         # Information about grading
├── uploads/               # Uploaded card images (gitignored)
└── README.md              # This file
```

## Technology Stack

- **Backend**: Python 3, Flask
- **Image Processing**: OpenCV, Pillow, NumPy
- **Frontend**: HTML5, CSS3, JavaScript
- **Computer Vision**: Custom algorithms for condition analysis

## Development

### Running Tests

```bash
python grading_system.py
```

This runs the example grading scenario included in the grading system module.

### Modifying Grading Criteria

Edit `grading_system.py` to adjust:
- Category weights (in `PSAGradingCriteria.CATEGORY_WEIGHTS`)
- Grade descriptions (in `PSAGradingCriteria.GRADE_DESCRIPTIONS`)
- Analysis thresholds (in `CardGrader` methods)

### Improving Image Analysis

Edit `image_analysis.py` to enhance:
- Corner detection algorithms
- Edge analysis techniques
- Surface defect identification
- Centering calculations
- Print quality assessment

## Contributing

Contributions are welcome! Areas for improvement:

1. Machine learning model integration for more accurate predictions
2. Support for specific card types (vintage, modern, etc.)
3. Batch processing for multiple cards
4. Export functionality for grading reports
5. Mobile app development
6. Database storage for grading history

## License

This project is available for educational and personal use.

## Disclaimer

This application provides AI-generated grade estimates for informational purposes only. These estimates are not official PSA grades and should not be used for buying, selling, or authenticating cards. For official grading, submit your cards to PSA (www.psacard.com).

## Support

For questions, issues, or suggestions, please open an issue on GitHub.

---

Made with ❤️ for the sports card collecting community
