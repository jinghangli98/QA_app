#!/usr/bin/env python3
"""
QA Image Review App - Tinder-style swipe interface for image quality assessment
Supports multiple raters; each user's results are stored separately.
"""

import os
import glob
import csv
import re
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file, session
from pathlib import Path
import io

app = Flask(__name__)
app.secret_key = 'qa_review_secret_key_2024'  # needed for session support

# Configuration - Update this path pattern as needed
IMAGE_PATTERN = "/ix1/tibrahim/jil202/studies/ADNI_nii/derivatives/TSE/*/qa/masv*.png"
CSV_OUTPUT_DIR = "/ix1/tibrahim/jil202/studies/ADNI_nii/derivatives/QA_app"  # directory for per-user CSVs

# Store results in memory: { username: { image_path: { rating, timestamp } } }
all_results = {}
image_list = []


def load_images():
    """Load all images matching the pattern"""
    global image_list
    all_found = glob.glob(IMAGE_PATTERN)
    image_list = sorted(all_found, key=lambda p: (0 if '_left' in p else 1, p))
    print(f"Found {len(image_list)} images")
    return image_list


def get_username():
    """Return the current session's username, or None if not set."""
    return session.get('username')


def sanitize_filename(name):
    """Remove characters unsafe for filenames."""
    return re.sub(r'[^\w\-]', '_', name)


def csv_path_for(username):
    """Return the CSV file path for a given username."""
    safe = sanitize_filename(username)
    return os.path.join(CSV_OUTPUT_DIR, f"qa_results_{safe}.csv")


def get_user_results(username):
    """Get (or initialise) the results dict for a user."""
    if username not in all_results:
        # Try to load existing CSV so progress survives restarts
        all_results[username] = {}
        path = csv_path_for(username)
        if os.path.exists(path):
            with open(path, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    all_results[username][row['image_path']] = {
                        'rating': row['rating'],
                        'timestamp': row['timestamp'],
                    }
    return all_results[username]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/set_user', methods=['POST'])
def set_user():
    """Set the current rater's name for this browser session."""
    data = request.json
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400
    session['username'] = username
    # Initialise results so saved progress is loaded
    get_user_results(username)
    return jsonify({'success': True, 'username': username})


@app.route('/api/current_user')
def current_user():
    """Return the current session user (or null)."""
    return jsonify({'username': get_username()})


@app.route('/api/images')
def get_images():
    """Get list of all images"""
    if not image_list:
        load_images()
    username = get_username()
    results = get_user_results(username) if username else {}
    return jsonify({
        'images': image_list,
        'total': len(image_list),
        'reviewed': len(results),
    })


@app.route('/api/image/<path:image_path>')
def serve_image(image_path):
    """Serve an image file"""
    full_path = '/' + image_path
    if os.path.exists(full_path):
        return send_file(full_path, mimetype='image/png')
    return "Image not found", 404


@app.route('/api/rate', methods=['POST'])
def rate_image():
    """Rate an image as good or bad"""
    username = get_username()
    if not username:
        return jsonify({'success': False, 'error': 'No user set'}), 403

    data = request.json
    image_path = data.get('image')
    rating = data.get('rating')  # 'good' or 'bad'

    results = get_user_results(username)
    results[image_path] = {
        'rating': rating,
        'timestamp': datetime.now().isoformat(),
    }

    save_to_csv(username)
    return jsonify({'success': True, 'reviewed': len(results)})


@app.route('/api/undo', methods=['POST'])
def undo_rating():
    """Undo the last rating"""
    username = get_username()
    if not username:
        return jsonify({'success': False, 'error': 'No user set'}), 403

    data = request.json
    image_path = data.get('image')
    results = get_user_results(username)

    if image_path in results:
        del results[image_path]
        save_to_csv(username)

    return jsonify({'success': True, 'reviewed': len(results)})


def save_to_csv(username):
    """Save a user's results to their personal CSV file."""
    results = get_user_results(username)
    path = csv_path_for(username)
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['image_path', 'rating', 'timestamp', 'rater'])
        for image_path, data in results.items():
            writer.writerow([image_path, data['rating'], data['timestamp'], username])


@app.route('/api/export')
def export_csv():
    """Download the CSV file for the current user."""
    username = get_username()
    if not username:
        return "No user set – please enter your name first", 403

    path = csv_path_for(username)
    if os.path.exists(path):
        safe = sanitize_filename(username)
        return send_file(
            path,
            as_attachment=True,
            download_name=f"qa_results_{safe}.csv",
        )
    return "No results yet", 404


@app.route('/api/stats')
def get_stats():
    """Get current statistics for the logged-in user."""
    username = get_username()
    results = get_user_results(username) if username else {}
    good_count = sum(1 for r in results.values() if r['rating'] == 'good')
    bad_count = sum(1 for r in results.values() if r['rating'] == 'bad')
    return jsonify({
        'total': len(image_list),
        'reviewed': len(results),
        'good': good_count,
        'bad': bad_count,
        'remaining': len(image_list) - len(results),
    })


@app.route('/api/reviewed')
def get_reviewed():
    """Return the set of reviewed image paths and the resume index.

    The resume index is the first image in image_list that has not yet
    been rated, so the frontend can jump straight there on load.
    """
    username = get_username()
    results = get_user_results(username) if username else {}
    reviewed_set = set(results.keys())

    # Find first unreviewed image index
    resume_index = len(image_list)  # default: all done
    for i, path in enumerate(image_list):
        if path not in reviewed_set:
            resume_index = i
            break

    # Build per-image rating map (path -> rating) for the progress bar
    ratings = {path: results[path]['rating'] for path in reviewed_set if path in set(image_list)}

    return jsonify({
        'reviewed': list(reviewed_set),
        'ratings': ratings,
        'resume_index': resume_index,
    })


@app.route('/api/clear', methods=['POST'])
def clear_ratings():
    """Clear all ratings for the current user."""
    username = get_username()
    if not username:
        return jsonify({'success': False, 'error': 'No user set'}), 403

    all_results[username] = {}
    path = csv_path_for(username)
    if os.path.exists(path):
        os.remove(path)

    return jsonify({'success': True})


if __name__ == '__main__':
    load_images()
    print(f"Starting QA Review App...")
    print(f"Found {len(image_list)} images to review")
    app.run(debug=True, host='0.0.0.0', port=5001)
