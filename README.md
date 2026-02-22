# Sports Card Grading App 🏆

An AI-powered web application that analyzes sports card images and provides comprehensive grade estimates using a custom 100-1000 point scale. Upload front and back photos of your cards to receive detailed condition assessments with 19 distinct grade levels.

## 📍 Where to Run This?

**Can I run this in VS Code?** → **YES!** See [HOW_TO_RUN.md](HOW_TO_RUN.md) for detailed instructions.

You can run this app in:
- ✅ **VS Code** (recommended for beginners) - [See guide](HOW_TO_RUN.md#method-1-running-in-vs-code-recommended-for-beginners)
- ✅ **Command Line / Terminal** - [See guide](HOW_TO_RUN.md#method-2-running-from-command-line--terminal)
- ✅ **PyCharm or other IDEs** - [See guide](HOW_TO_RUN.md#method-3-running-in-pycharm)
- ✅ **Any Python environment** - [See guide](HOW_TO_RUN.md)

## 🚀 Quick Start - Test Your Cards Now!

**Want to start grading cards immediately?** See the [QUICKSTART.md](QUICKSTART.md) guide!

![Card Upload Interface](https://github.com/user-attachments/assets/29a09b70-7ce5-4273-a2a9-59a306df2ea2)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py

# Open in browser: http://localhost:5000
```

## Features

- **AI-Powered Analysis**: Advanced computer vision algorithms analyze card condition
- **Custom 100-1000 Point Scale**: Much more granular than traditional 1-10 scales
- **19 Grade Levels**: From POOR (100-149) to PRISTINE (990-1000)
- **Comprehensive Evaluation**: Analyzes corners, edges, surface, and centering
- **Detailed Breakdowns**: Provides category-by-category scores and explanations
- **Web Interface**: Easy-to-use interface for uploading and viewing results
- **Consistent Grading**: Uses standardized criteria for reproducible results

## How It Works

### Grading Criteria

The app evaluates four key categories, each weighted equally at 25%:

1. **Corners (25% weight)**: Sharpness, wear, rounding, and surface compromise
2. **Edges (25% weight)**: Chipping, whitening, roughness, notches, and tears
3. **Surface (25% weight)**: Scratches, creases, wrinkles, stains, and print defects
4. **Centering (25% weight)**: Image placement within borders (51/49 to 95/5 tolerance)

Each side of the card is analyzed separately, and the final grade uses the worse score for each category (a card is only as good as its worst side).

### Grading Scale

The system uses a 100-1000 point scale with 19 distinct grade levels:

| Grade | Name | Score Range | Description |
|-------|------|-------------|-------------|
| 10 | PRISTINE | 990-1000 | Virtually flawless |
| 10 | GEM MINT | 950-989 | Extremely high-grade |
| 9 | MINT | 900-949 | High-grade with minimal wear |
| 8.5 | NEAR MINT-MINT+ | 850-899 | Very nice with light wear |
| 8 | NEAR MINT-MINT | 800-849 | Nice with visible wear |
| 7.5 | NEAR MINT+ | 750-799 | Above average |
| 7 | NEAR MINT | 700-749 | Average collectible |
| 6.5 | EXCELLENT-MINT+ | 650-699 | Below average |
| 6 | EXCELLENT-MINT | 600-649 | Noticeable wear |
| 5.5 | EXCELLENT+ | 550-599 | Heavy wear beginning |
| 5 | EXCELLENT | 500-549 | Substantial wear |
| 4.5 | VERY GOOD-EXCELLENT+ | 450-499 | Significant damage |
| 4 | VERY GOOD-EXCELLENT | 400-449 | Heavy damage |
| 3.5 | VERY GOOD+ | 350-399 | Very heavy damage |
| 3 | VERY GOOD | 300-349 | Extreme wear |
| 2.5 | GOOD+ | 250-299 | Severe damage |
| 2 | GOOD | 200-249 | Major structural issues |
| 1.5 | FAIR | 150-199 | Card integrity compromised |
| 1 | POOR | 100-149 | Barely recognizable |

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
3. **View Results**: See your estimated grade (1-10 with name) and numerical score (100-1000) with detailed category scores

### Tips for Best Results

- Use high-resolution images (at least 800px on smallest side)
- Ensure good, even lighting without glare or shadows
- Capture the entire card with borders visible
- Use a contrasting background
- Avoid flash photography that creates glare
- Keep cards clean and free of dust/fingerprints

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
├── grading_system.py       # Custom grading logic and criteria (100-1000 scale)
├── image_analysis.py       # Computer vision analysis
├── requirements.txt        # Python dependencies
├── templates/
│   ├── index.html         # Main upload interface
│   └── about.html         # Information about grading system
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
- Grade ranges and descriptions (in `PSAGradingCriteria.GRADE_RANGES`)
- Analysis thresholds (in `CardGrader` methods)

### Improving Image Analysis

Edit `image_analysis.py` to enhance:
- Corner detection algorithms
- Edge analysis techniques
- Surface defect identification
- Centering calculations

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

This application provides AI-generated grade estimates for informational purposes only using a custom 100-1000 point grading scale. These estimates are not official professional grades and should not be used for buying, selling, or authenticating cards. Results are for comparative and educational purposes.

## Support

For questions, issues, or suggestions, please open an issue on GitHub.

---

Made with ❤️ for the sports card collecting community
