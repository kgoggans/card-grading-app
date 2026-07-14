# Usage Guide - Card Grading App

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/kgoggans/card-grading-app.git
cd card-grading-app

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

### 2. Access the Application

Open your web browser and navigate to:
```
http://localhost:5000
```

### 3. Grade Your Cards

1. **Prepare Your Card Images**
   - Take clear, well-lit photos of the front and back of your card
   - Ensure the entire card is visible
   - Avoid glare, shadows, and reflections
   - Use a contrasting background
   - Recommended resolution: 800px minimum on smallest dimension

2. **Upload Images**
   - Click on "Front of Card" upload box
   - Select your front image
   - Click on "Back of Card" upload box
   - Select your back image

3. **Get Your Grade**
   - Click the "Grade My Card" button
   - Wait for analysis (typically 5-15 seconds)
   - Review your PSA grade estimate and detailed breakdown

## Understanding Your Results

### Overall Grade
- **PSA Grade (1-10)**: The estimated PSA grade for your card
- **Description**: Explanation of what the grade means
- **Decimal Grade**: More precise grade (with half-point precision)

### Category Scores
Each card is evaluated across five categories:

1. **Corners (25% weight)**
   - Evaluates corner sharpness and wear
   - 10 = Perfect sharp corners
   - 1 = Severely rounded/damaged corners

2. **Edges (20% weight)**
   - Checks for chipping, whitening, and roughness
   - 10 = Clean, crisp edges
   - 1 = Heavy edge wear and chipping

3. **Surface (25% weight)**
   - Detects scratches, creases, stains, print defects
   - 10 = Pristine surface
   - 1 = Heavy surface damage

4. **Centering (15% weight)**
   - Analyzes image placement within card borders
   - 10 = Perfect 50/50 centering
   - 1 = Severely off-center

5. **Print Quality (15% weight)**
   - Evaluates focus, color accuracy, registration
   - 10 = Perfect print quality
   - 1 = Poor print quality or defects

### Detailed Analysis
The app provides explanations for each category score and an overall assessment of your card's condition.

## Photography Tips

### Best Practices for Accurate Grading

#### Lighting
- Use natural, indirect light or soft artificial lighting
- Avoid direct sunlight (creates harsh shadows/glare)
- Avoid using camera flash (creates hot spots)
- Ensure even lighting across entire card

#### Background
- Use a solid, contrasting background
- Dark cards → light background (white/gray)
- Light cards → slightly darker background
- Avoid busy patterns or textures

#### Camera Setup
- Hold camera parallel to card (avoid angles)
- Fill frame with card (include all borders)
- Use highest resolution your camera/phone offers
- Keep camera steady (use tripod if possible)
- Ensure card is in focus

#### Card Preparation
- Clean card gently (remove dust/fingerprints)
- Place card on flat surface
- Ensure card is not in sleeve (if possible) to show true condition
- If in sleeve, ensure sleeve is clean and clear

### Common Mistakes to Avoid
- ❌ Blurry images
- ❌ Partial card in frame
- ❌ Glare or reflections
- ❌ Shadows across card
- ❌ Angled shots (card not parallel to camera)
- ❌ Low resolution images
- ❌ Dirty card or sleeve

## Achieving Consistent Results

### For Multiple Cards
If grading multiple cards, consistency is key:

1. **Same Setup**: Use identical lighting, background, and camera position
2. **Same Resolution**: Use same camera/device for all photos
3. **Same Time/Place**: Photograph in same location under same conditions
4. **Same Distance**: Keep camera at consistent distance from cards

### Factors Affecting Accuracy

#### Image Quality (Most Important)
- Higher resolution = more accurate
- Better lighting = more accurate
- Sharper focus = more accurate

#### Card Type
- Modern cards (smooth surface) → Generally more accurate
- Vintage cards (textured surface) → May affect surface analysis
- Glossy vs. matte finish → Different reflection properties

#### Actual Defects vs. Photo Artifacts
The AI cannot distinguish between:
- Real crease vs. shadow that looks like crease
- Actual stain vs. lighting variation
- True surface scratch vs. sleeve scratch

**Always photograph cards without sleeves when possible for most accurate results.**

## Understanding Limitations

### What the AI CAN Detect
✅ Corner wear and rounding
✅ Edge whitening and chipping
✅ Surface scratches (if visible)
✅ Major creases and bends
✅ Centering issues
✅ Print focus and registration
✅ Major stains or discoloration

### What the AI CANNOT Detect
❌ Card thickness variations
❌ Very minor defects invisible to camera
❌ Authenticity (real vs. counterfeit)
❌ Subtle color differences
❌ Minor surface imperfections
❌ Card warping (unless severe)
❌ Defects hidden by lighting/angle

### Important Disclaimers
- This is an **AI estimate**, not an official PSA grade
- Results are for **informational purposes only**
- Do not rely on this for buying/selling decisions
- For official grading, submit to PSA directly
- Actual PSA graders consider factors beyond what photos show

## Advanced Usage

### Testing the System
The repository includes a test script:

```bash
python test_grading.py
```

This creates synthetic test cards at different quality levels and grades them, demonstrating how the system works.

### Modifying Grading Criteria
To adjust grading parameters, edit `grading_system.py`:

- **Category Weights**: Adjust importance of each factor
- **Scoring Thresholds**: Change what constitutes "good" vs "poor"
- **Grade Descriptions**: Customize explanations

### Improving Image Analysis
To enhance detection algorithms, edit `image_analysis.py`:

- **Corner Detection**: Modify edge detection parameters
- **Surface Analysis**: Adjust scratch/crease detection sensitivity
- **Centering Calculation**: Change how borders are measured

## Troubleshooting

### "Error processing images"
- **Cause**: Invalid image file or processing error
- **Solution**: Ensure images are valid PNG/JPG files, try different images

### Grade seems inaccurate
- **Cause**: Poor image quality, lighting issues, or limitations
- **Solution**: 
  - Retake photos with better lighting
  - Use higher resolution
  - Ensure card is flat and in focus
  - Remove card from sleeve

### App won't start
- **Cause**: Missing dependencies or port conflict
- **Solution**:
  ```bash
  pip install -r requirements.txt
  # If port 5000 is in use, edit app.py to change port
  ```

### Images too large
- **Cause**: File size over 16MB limit
- **Solution**: Resize images or compress before uploading

## API Usage

### Programmatic Access
You can call the grading endpoint directly:

```bash
curl -X POST \
  -F "front_image=@path/to/front.jpg" \
  -F "back_image=@path/to/back.jpg" \
  http://localhost:5000/grade
```

Response format:
```json
{
  "success": true,
  "grade": 8,
  "grade_decimal": 8.0,
  "description": "Near Mint-Mint - Very slight wear...",
  "category_scores": {
    "corners": 8.5,
    "edges": 9.2,
    "surface": 8.0,
    "centering": 7.5,
    "print_quality": 8.3
  },
  "details": "Detailed analysis text...",
  "front_image": "/static/../uploads/...",
  "back_image": "/static/../uploads/..."
}
```

## Support and Contributing

### Getting Help
- Check the [README.md](README.md) for general information
- Review the [About page](http://localhost:5000/about) for grading details
- Open an issue on GitHub for bugs or questions

### Contributing
Contributions are welcome! Areas for improvement:
- Machine learning integration
- Support for specific card types
- Batch processing
- Mobile app
- Database for history

## Best Practices Summary

✅ **DO:**
- Use high-resolution images (800px+ minimum)
- Ensure good, even lighting
- Keep card parallel to camera
- Use contrasting background
- Clean cards before photographing
- Take multiple photos if unsure

❌ **DON'T:**
- Use flash photography
- Photograph at angles
- Include glare or shadows
- Use low-resolution images
- Rely solely on these results for purchasing decisions
- Expect 100% accuracy

Remember: This tool is designed to give you a **general estimate** of your card's condition. For official grading and maximum accuracy, always submit to PSA directly!
