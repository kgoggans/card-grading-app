# Quick Start Guide - Test Your Cards Now! 🏆

## 🤔 Where Do I Run This?

**New to this?** Check out [HOW_TO_RUN.md](HOW_TO_RUN.md) for detailed setup instructions including:
- ✅ Running in VS Code (step-by-step with screenshots)
- ✅ Running from Command Line/Terminal
- ✅ Running in PyCharm or other IDEs
- ✅ Troubleshooting common issues

## Where to Upload Cards

![Card Upload Interface](https://github.com/user-attachments/assets/29a09b70-7ce5-4273-a2a9-59a306df2ea2)

## Step 1: Start the Application

```bash
# Install dependencies (first time only)
pip install flask pillow numpy opencv-python werkzeug

# Run the app
python app.py
```

**Need help?** See [HOW_TO_RUN.md](HOW_TO_RUN.md) for detailed instructions on running in VS Code or other environments.

## Step 2: Open the Web Interface

Open your web browser and go to:
```
http://localhost:5000
```

## Step 3: Upload Your Card Images

**You'll see two upload boxes:**

1. **📸 Front of Card** (left box)
   - Click on this box
   - Select a photo of the front of your sports card
   - The image will preview in the box

2. **📸 Back of Card** (right box)
   - Click on this box
   - Select a photo of the back of your sports card
   - The image will preview in the box

## Step 4: Grade Your Card

Click the **"Grade My Card"** button (it becomes active after both images are uploaded)

## Step 5: View Your Results

The app will analyze your card and show:
- **Overall Grade**: Number (1-10) and Name (e.g., "9 - MINT")
- **Score**: Points out of 1000 (e.g., "924/1000")
- **Category Breakdown**:
  - Corners score
  - Edges score
  - Surface score
  - Centering score
- **Detailed Analysis**: Explanation of the grade

## Tips for Best Results

### Photo Requirements
- ✅ Use clear, well-lit photos
- ✅ Show the entire card including borders
- ✅ Avoid glare, shadows, or reflections
- ✅ Use a contrasting, solid-color background
- ✅ Minimum 800px resolution on smallest dimension
- ✅ Keep camera parallel to card (straight-on shot)

### What NOT to Do
- ❌ Don't use blurry or out-of-focus images
- ❌ Don't crop out parts of the card
- ❌ Don't use images with heavy shadows
- ❌ Don't use flash photography that creates glare
- ❌ Don't use backgrounds that match the card color

## Testing the System

### Want to Test Without Your Own Cards?

Run the test script to see example grading:

```bash
python test_grading.py
```

This will:
1. Generate sample card images with different quality levels
2. Grade them automatically
3. Show you the grading results

Sample output:
```
============================================================
Card Grading System Test
============================================================

Testing: Perfect condition card
✓ PSA Grade: 9.0
  Score: 924/1000
  Corners: 925/1000 (MINT)
  Edges: 875/1000 (NEAR MINT - MINT+)
  Surface: 925/1000 (MINT)
  Centering: 970/1000 (GEM MINT)
```

## Troubleshooting

### "The app isn't starting"
- Make sure you installed all dependencies: `pip install -r requirements.txt`
- Check that port 5000 isn't already in use
- Look for error messages in the terminal

### "My images won't upload"
- Check file format (JPG, PNG supported)
- Verify file size isn't too large (< 10MB recommended)
- Make sure you have permission to read the files

### "The grade seems wrong"
- Check your image quality - blurry images produce inaccurate results
- Ensure proper lighting without glare
- Make sure the entire card is visible
- Try retaking photos with better conditions

## Understanding Your Grade

### Grade Scale (100-1000 points)
- **990-1000**: PRISTINE - Virtually flawless
- **950-989**: GEM MINT - Extremely high-grade
- **900-949**: MINT - High-grade with minimal wear
- **850-899**: NEAR MINT-MINT+ - Very nice with light wear
- **800-849**: NEAR MINT-MINT - Nice with visible wear
- **750-799**: NEAR MINT+ - Above average
- **700-749**: NEAR MINT - Average collectible
- ... and 12 more levels down to POOR (100-149)

### Category Scores

Each category is weighted equally at 25%:

1. **Corners** - Sharpness, rounding, fraying, wear
2. **Edges** - Chipping, whitening, roughness, notches
3. **Surface** - Scratches, creases, stains, print defects
4. **Centering** - Image placement within borders

**Important**: Your card receives the WORST score from front and back for each category. A card is only as good as its worst side!

## Need More Help?

- **Detailed Documentation**: See [USAGE_GUIDE.md](USAGE_GUIDE.md)
- **About Grading**: Click "About Grading System" in the app
- **Full Manual**: See [README.md](README.md)
- **Deployment Guide**: See [DEPLOYMENT.md](DEPLOYMENT.md) for production use

---

**Note**: This is an AI-powered estimate using a custom grading system. Results are for informational and educational purposes. They are NOT official professional grades.
