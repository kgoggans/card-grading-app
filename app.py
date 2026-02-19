"""
Flask Web Application for Card Grading

This app allows users to upload front and back images of sports cards
and receive AI-powered PSA grade estimates.
"""

from flask import Flask, render_template, request, jsonify, url_for
from werkzeug.utils import secure_filename
import os
import secrets
from grading_system import CardGrader
from image_analysis import analyze_card_images

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/grade', methods=['POST'])
def grade_card():
    """
    Grade a card based on uploaded front and back images
    """
    # Check if both files are present
    if 'front_image' not in request.files or 'back_image' not in request.files:
        return jsonify({'error': 'Both front and back images are required'}), 400
    
    front_file = request.files['front_image']
    back_file = request.files['back_image']
    
    # Check if files are selected
    if front_file.filename == '' or back_file.filename == '':
        return jsonify({'error': 'Both images must be selected'}), 400
    
    # Validate file types
    if not (allowed_file(front_file.filename) and allowed_file(back_file.filename)):
        return jsonify({'error': 'Invalid file type. Please upload PNG, JPG, or JPEG files'}), 400
    
    try:
        # Save uploaded files
        front_filename = secure_filename(front_file.filename)
        back_filename = secure_filename(back_file.filename)
        
        # Add timestamp to avoid overwrites
        import time
        timestamp = str(int(time.time()))
        front_filename = f"{timestamp}_front_{front_filename}"
        back_filename = f"{timestamp}_back_{back_filename}"
        
        front_path = os.path.join(app.config['UPLOAD_FOLDER'], front_filename)
        back_path = os.path.join(app.config['UPLOAD_FOLDER'], back_filename)
        
        front_file.save(front_path)
        back_file.save(back_path)
        
        # Analyze images
        print(f"Analyzing images: {front_path}, {back_path}")
        front_analysis, back_analysis = analyze_card_images(front_path, back_path)
        
        # Grade the card
        grader = CardGrader()
        grading_result = grader.grade_card(front_analysis, back_analysis)
        
        # Prepare response
        response = {
            'success': True,
            'grade': grading_result['grade'],
            'grade_decimal': grading_result['grade_decimal'],
            'description': grading_result['description'],
            'details': grading_result['details'],
            'category_scores': grading_result['category_scores'],
            'front_image': url_for('static', filename=f'../uploads/{front_filename}'),
            'back_image': url_for('static', filename=f'../uploads/{back_filename}')
        }
        
        return jsonify(response)
    
    except Exception as e:
        print(f"Error processing card: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error processing images: {str(e)}'}), 500


@app.route('/about')
def about():
    """About page explaining the grading system"""
    return render_template('about.html')


if __name__ == '__main__':
    # Debug mode should only be enabled in development
    # Set FLASK_ENV=production in production environments
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
