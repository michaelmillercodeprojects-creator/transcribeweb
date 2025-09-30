#!/usr/bin/env python3
"""
Transcription Web Application
Flask web application for transcribing audio/video content
"""

import os
import uuid
import threading
import shutil
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

from transcription_service import TranscriptionService

# App configuration
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5GB

# Directories
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
CHUNK_FOLDER = Path(__file__).parent / 'chunks'
for folder in [UPLOAD_FOLDER, CHUNK_FOLDER]:
    folder.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configuration
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'mp4', 'avi', 'mov', 'mkv', 'flv', 'webm', 'm4a', 'aac', 'ogg'}
active_jobs = {}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/settings')
def settings():
    """Settings page"""
    return render_template('settings.html')

@app.route('/api/save-settings', methods=['POST'])
def save_settings():
    """Save user settings"""
    try:
        settings = request.get_json()
        
        # Store in session for now (in production, use secure database)
        session['settings'] = settings
        
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get-settings')
def get_settings():
    """Get user settings"""
    return jsonify(session.get('settings', {}))

@app.route('/api/upload-chunk', methods=['POST'])
def upload_chunk():
    """Handle chunked file upload"""
    try:
        chunk = request.files.get('chunk')
        chunk_index = int(request.form.get('chunkIndex'))
        total_chunks = int(request.form.get('totalChunks'))
        upload_id = request.form.get('uploadId')
        filename = request.form.get('filename')

        if not all([chunk, upload_id, filename]):
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

        # Create upload directory
        upload_dir = CHUNK_FOLDER / upload_id
        upload_dir.mkdir(exist_ok=True)

        # Save chunk
        chunk_path = upload_dir / f'chunk_{chunk_index:04d}'
        chunk.save(chunk_path)

        return jsonify({
            'success': True,
            'chunkIndex': chunk_index,
            'totalChunks': total_chunks,
            'message': f'Chunk {chunk_index + 1}/{total_chunks} uploaded'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/finalize-upload', methods=['POST'])
def finalize_upload():
    """Combine chunks and start processing"""
    try:
        data = request.get_json()
        upload_id = data.get('uploadId')
        filename = data.get('filename')
        total_size = data.get('totalSize')

        if not all([upload_id, filename]):
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

        # Validate settings
        settings = session.get('settings', {})
        if not settings.get('openai_api_key'):
            return jsonify({
                'success': False, 
                'error': 'OpenAI API key not configured. Please go to Settings to configure your API key.'
            }), 400

        upload_dir = CHUNK_FOLDER / upload_id
        if not upload_dir.exists():
            return jsonify({'success': False, 'error': 'Upload not found'}), 404

        # Combine chunks
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        job_id = str(uuid.uuid4())
        secure_name = secure_filename(filename)
        final_filename = f"{timestamp}_{job_id}_{secure_name}"
        final_path = UPLOAD_FOLDER / final_filename

        # Combine all chunks in order
        with open(final_path, 'wb') as outfile:
            chunk_files = sorted(upload_dir.glob('chunk_*'))
            for chunk_file in chunk_files:
                with open(chunk_file, 'rb') as infile:
                    shutil.copyfileobj(infile, outfile)

        # Clean up chunks
        shutil.rmtree(upload_dir)

        # Start processing
        try:
            service = TranscriptionService(settings)
        except Exception as service_error:
            return jsonify({
                'success': False, 
                'error': f'Failed to initialize transcription service: {str(service_error)}'
            }), 500

        def process_file():
            try:
                # Check if job is already processing to prevent duplicates
                if job_id in active_jobs and active_jobs[job_id]['status'] == 'processing':
                    return
                    
                active_jobs[job_id] = {
                    'status': 'processing',
                    'progress': 'Starting transcription...',
                    'result': None,
                    'error': None
                }

                result = service.process_file(str(final_path), job_id, active_jobs)

                active_jobs[job_id].update({
                    'status': 'completed',
                    'progress': 'Transcription completed',
                    'result': result
                })

                # Clean up uploaded file
                try:
                    os.remove(final_path)
                except:
                    pass

            except Exception as e:
                print(f"Error processing file: {e}")
                active_jobs[job_id].update({
                    'status': 'error',
                    'error': str(e)
                })

        # Start processing in background
        thread = threading.Thread(target=process_file)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': f'Large file uploaded successfully ({total_size / 1024 / 1024:.1f}MB). Processing started.'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cleanup-upload', methods=['POST'])
def cleanup_upload():
    """Clean up failed chunked upload"""
    try:
        data = request.get_json()
        upload_id = data.get('uploadId')

        if upload_id:
            upload_dir = CHUNK_FOLDER / upload_id
            if upload_dir.exists():
                shutil.rmtree(upload_dir)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    try:
        print(f"Upload request received: {request.files}")  # Debug logging
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        file = request.files['file']
        print(f"File: {file.filename}, size: {file.content_length if hasattr(file, 'content_length') else 'unknown'}")  # Debug
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False, 
                'error': f'File type not allowed. Supported types: {", ".join(ALLOWED_EXTENSIONS)}'
            }), 400
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{job_id}_{filename}"
        file_path = app.config['UPLOAD_FOLDER'] / unique_filename
        file.save(file_path)
        
        # Start processing
        settings = session.get('settings', {})
        
        # Validate that we have required settings before creating service
        if not settings.get('openai_api_key'):
            return jsonify({
                'success': False, 
                'error': 'OpenAI API key not configured. Please go to Settings to configure your API key.'
            }), 400
        
        try:
            service = TranscriptionService(settings)
        except Exception as service_error:
            return jsonify({
                'success': False, 
                'error': f'Failed to initialize transcription service: {str(service_error)}'
            }), 500
        
        def process_file():
            try:
                # Check if job is already processing to prevent duplicates
                if job_id in active_jobs and active_jobs[job_id]['status'] == 'processing':
                    return
                    
                active_jobs[job_id] = {
                    'status': 'processing',
                    'progress': 'Starting transcription...',
                    'result': None,
                    'error': None
                }
                
                # Check if OpenAI API key is configured
                if not settings.get('openai_api_key'):
                    raise Exception("OpenAI API key not configured. Please go to Settings to configure your API key.")
                
                result = service.process_file(str(file_path), job_id, active_jobs)
                
                active_jobs[job_id].update({
                    'status': 'completed',
                    'progress': 'Transcription completed',
                    'result': result
                })
                
                # Clean up uploaded file
                try:
                    os.remove(file_path)
                except:
                    pass
                    
            except Exception as e:
                print(f"Error processing file: {e}")  # Debug logging
                active_jobs[job_id].update({
                    'status': 'error',
                    'error': str(e)
                })
        
        # Start processing in background
        thread = threading.Thread(target=process_file)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True, 
            'job_id': job_id,
            'message': 'File uploaded successfully. Processing started.'
        })
        
    except RequestEntityTooLarge:
        return jsonify({'success': False, 'error': 'File too large (max 500MB)'}), 413
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/process-url', methods=['POST'])
def process_url():
    """Handle URL processing"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Start processing
        settings = session.get('settings', {})
        
        # Validate that we have required settings before creating service
        if not settings.get('openai_api_key'):
            return jsonify({
                'success': False, 
                'error': 'OpenAI API key not configured. Please go to Settings to configure your API key.'
            }), 400
        
        try:
            service = TranscriptionService(settings)
        except Exception as service_error:
            return jsonify({
                'success': False, 
                'error': f'Failed to initialize transcription service: {str(service_error)}'
            }), 500
        
        def process_url_task():
            try:
                active_jobs[job_id] = {
                    'status': 'processing',
                    'progress': 'Downloading from URL...',
                    'result': None,
                    'error': None
                }
                
                # Check if OpenAI API key is configured
                if not settings.get('openai_api_key'):
                    raise Exception("OpenAI API key not configured. Please go to Settings to configure your API key.")
                
                result = service.process_url(url, job_id, active_jobs)
                
                active_jobs[job_id].update({
                    'status': 'completed',
                    'progress': 'Transcription completed',
                    'result': result
                })
                
            except Exception as e:
                print(f"Error processing URL: {e}")  # Debug logging
                active_jobs[job_id].update({
                    'status': 'error',
                    'error': str(e)
                })
        
        # Start processing in background
        thread = threading.Thread(target=process_url_task)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True, 
            'job_id': job_id,
            'message': 'URL processing started.'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/job-status/<job_id>')
def job_status(job_id):
    """Get job status"""
    if job_id not in active_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(active_jobs[job_id])

@app.route('/api/test-email', methods=['POST'])
def test_email():
    """Test email configuration"""
    try:
        settings = session.get('settings', {})
        service = TranscriptionService(settings)
        
        result = service.test_email_credentials()
        
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({'success': False, 'error': 'File too large (max 5GB)'}), 413

@app.errorhandler(500)
def internal_error(e):
    print(f"Internal server error: {str(e)}")
    return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'}), 500

@app.errorhandler(404)
def not_found(e):
    # Only return JSON for API routes, HTML for regular routes
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'API endpoint not found'}), 404
    else:
        # Return minimal HTML for non-API 404s (like favicon)
        return '<html><body><h1>404 Not Found</h1></body></html>', 404

if __name__ == '__main__':
    # Create uploads directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)