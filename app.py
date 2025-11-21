#!/usr/bin/env python3
"""
QA Image Review App - Tinder-style swipe interface for image quality assessment
"""

import os
import glob
import csv
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
from pathlib import Path

app = Flask(__name__)

# Configuration - Update this path pattern as needed
IMAGE_PATTERN = "/Users/jinghangli/qa_app/qa_images/ix1/tibrahim/jil202/studies/BIDS/WPC*/derivatives/ashs/sub-*/qa/qa_seg_multiatlas_corr_usegray_left_qa.png"
CSV_OUTPUT = "qa_results.csv"

# Store results in memory
results = {}
image_list = []

def load_images():
    """Load all images matching the pattern"""
    global image_list
    image_list = sorted(glob.glob(IMAGE_PATTERN))
    print(f"Found {len(image_list)} images")
    return image_list

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/images')
def get_images():
    """Get list of all images"""
    if not image_list:
        load_images()
    return jsonify({
        'images': image_list,
        'total': len(image_list),
        'reviewed': len(results)
    })

@app.route('/api/image/<path:image_path>')
def serve_image(image_path):
    """Serve an image file"""
    # Reconstruct absolute path
    full_path = '/' + image_path
    if os.path.exists(full_path):
        return send_file(full_path, mimetype='image/png')
    return "Image not found", 404

@app.route('/api/rate', methods=['POST'])
def rate_image():
    """Rate an image as good or bad"""
    data = request.json
    image_path = data.get('image')
    rating = data.get('rating')  # 'good' or 'bad'

    results[image_path] = {
        'rating': rating,
        'timestamp': datetime.now().isoformat()
    }

    # Auto-save to CSV after each rating
    save_to_csv()

    return jsonify({'success': True, 'reviewed': len(results)})

@app.route('/api/undo', methods=['POST'])
def undo_rating():
    """Undo the last rating"""
    data = request.json
    image_path = data.get('image')

    if image_path in results:
        del results[image_path]
        save_to_csv()

    return jsonify({'success': True, 'reviewed': len(results)})

def save_to_csv():
    """Save results to CSV file"""
    with open(CSV_OUTPUT, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['image_path', 'rating', 'timestamp'])
        for image_path, data in results.items():
            writer.writerow([image_path, data['rating'], data['timestamp']])

@app.route('/api/export')
def export_csv():
    """Download the CSV file"""
    if os.path.exists(CSV_OUTPUT):
        return send_file(CSV_OUTPUT, as_attachment=True)
    return "No results yet", 404

@app.route('/api/stats')
def get_stats():
    """Get current statistics"""
    good_count = sum(1 for r in results.values() if r['rating'] == 'good')
    bad_count = sum(1 for r in results.values() if r['rating'] == 'bad')
    return jsonify({
        'total': len(image_list),
        'reviewed': len(results),
        'good': good_count,
        'bad': bad_count,
        'remaining': len(image_list) - len(results)
    })

if __name__ == '__main__':
    load_images()
    print(f"Starting QA Review App...")
    print(f"Found {len(image_list)} images to review")
    app.run(debug=True, host='0.0.0.0', port=5001)
