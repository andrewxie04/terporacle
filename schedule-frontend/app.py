import os
import subprocess
import uuid
import json
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import sys

# Add the PythonTesting directory to the Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
python_testing_dir = os.path.abspath(os.path.join(script_dir, '..', 'PythonTesting'))

app = Flask(__name__, static_folder='static')

# Configuration
UPLOAD_FOLDER = 'uploads' # Bring back upload folder
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
PYTHON_EXECUTABLE = sys.executable
SCRIPT_PATH = os.path.abspath(os.path.join(python_testing_dir, 'enhanced_schedule_analyzer.py'))
OUTPUT_DIR = python_testing_dir
OUTPUT_TXT_FILENAME = 'enhanced_schedule_analysis.txt'
OUTPUT_JSON_FILENAME = 'schedule_data.json'

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

@app.route('/analyze', methods=['POST'])
def analyze_schedule():
    api_key = None
    term_id = None
    image_path_to_process = None
    is_manual_input = False
    courses_input = None # For manual input

    # Determine input type based on Content-Type
    content_type = request.headers.get('Content-Type', '').lower()

    if 'application/json' in content_type:
        # --- Handle JSON Input (Manual) ---
        is_manual_input = True
        print("[*] Handling JSON request (manual input)")
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 415

        data = request.get_json()
        courses_input = data.get('courses')
        api_key = data.get('apiKey')
        term_id = data.get('termId', '202508')

        if not courses_input or not isinstance(courses_input, list) or len(courses_input) == 0:
            return jsonify({"error": "Missing or invalid 'courses' list in JSON payload"}), 400

        # --- IMPORTANT: Manual input requires script modification ---
        # We will pass a dummy image path, but the script needs to be adapted
        # to potentially ignore the image and use provided course data.
        # Create a dummy file path (it won't contain real data)
        dummy_filename = f"manual_input_{uuid.uuid4()}.dummy"
        image_path_to_process = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], dummy_filename))
        try:
            with open(image_path_to_process, 'w') as f: f.write("manual input placeholder")
            print(f"[*] Created dummy file for manual input: {image_path_to_process}")
        except Exception as e:
             print(f"[!] Error creating dummy file: {e}")
             return jsonify({"error": "Server error creating temporary file."}), 500

    elif 'multipart/form-data' in content_type:
        # --- Handle Form Data (Image Upload) ---
        print("[*] Handling multipart/form-data request (image upload)")
        if 'scheduleImage' not in request.files:
            return jsonify({"error": "No image file part"}), 400
        file = request.files['scheduleImage']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        api_key = request.form.get('apiKey')
        term_id = request.form.get('termId', '202508')

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = str(uuid.uuid4()) + "_" + filename
            temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(temp_image_path)
            image_path_to_process = os.path.abspath(temp_image_path) # Use absolute path
            print(f"[*] Image saved temporarily to: {image_path_to_process}")
        else:
            return jsonify({"error": "File type not allowed"}), 400
    else:
        return jsonify({"error": f"Unsupported Content-Type: {content_type}"}), 415

    # --- Common Logic: API Key Check ---
    if not api_key:
         api_key = os.environ.get('GEMINI_API_KEY') # Fallback to env var
         if not api_key:
              # Clean up dummy file if created
              if is_manual_input and image_path_to_process and os.path.exists(image_path_to_process):
                  os.remove(image_path_to_process)
              return jsonify({"error": "API Key is required."}), 400

    # --- Common Logic: Execute Script ---
    output_txt_path = os.path.join(OUTPUT_DIR, OUTPUT_TXT_FILENAME)
    output_json_path = os.path.join(OUTPUT_DIR, OUTPUT_JSON_FILENAME)

    # Ensure old output files are removed
    try:
        if os.path.exists(output_txt_path): os.remove(output_txt_path)
        if os.path.exists(output_json_path): os.remove(output_json_path)
    except OSError as e:
        print(f"[*] Warning: Could not remove old output file(s): {e}")

    # Prepare command for the script
    command = [ PYTHON_EXECUTABLE, SCRIPT_PATH ]

    # Add arguments based on input type
    if is_manual_input and courses_input:
        # For manual input, pass --courses-json and skip image_path argument in script logic
        command.extend(['--courses-json', json.dumps(courses_input)])
        # We still pass a dummy image path because argparse in the script might expect it,
        # but the script logic should ignore it when --courses-json is present.
        command.extend([image_path_to_process]) # Add dummy image path as positional arg if needed
    else:
        # For image input, pass the image path as the positional argument
        command.extend([image_path_to_process])

    # Add common arguments
    command.extend([
        '--term', term_id,
        '--output', OUTPUT_TXT_FILENAME,
        '--json', OUTPUT_JSON_FILENAME,
        '--api-key', api_key
    ])

    try:
        print(f"[*] Running script: {' '.join(command)}")
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True, # Raise error on non-zero exit code
            cwd=python_testing_dir # Run from script's directory
        )
        print(f"[*] Script stdout:\n{process.stdout}")
        print(f"[*] Script stderr:\n{process.stderr}")
        print(f"[*] Script finished successfully.")

        # Read the generated JSON output file
        if os.path.exists(output_json_path):
            with open(output_json_path, 'r', encoding='utf-8') as f:
                analysis_data = json.load(f)
            return jsonify(analysis_data) # Return the structured JSON
        else:
            print(f"[*] Error: Output JSON file not found at {output_json_path}")
            # Include script output in error if possible
            stderr_output = process.stderr if process else "N/A"
            return jsonify({"error": "Analysis script ran but did not produce the expected JSON output file.", "stderr": stderr_output}), 500

    except subprocess.CalledProcessError as e:
        print(f"[*] Error executing script: {e}")
        print(f"[*] Script stdout:\n{e.stdout}")
        print(f"[*] Script stderr:\n{e.stderr}")
        return jsonify({"error": "Failed to execute analysis script.", "details": str(e), "stdout": e.stdout, "stderr": e.stderr}), 500
    except Exception as e:
        print(f"[*] An unexpected error occurred: {e}")
        return jsonify({"error": "An unexpected server error occurred.", "details": str(e)}), 500
    finally:
        # Clean up uploaded image or dummy file
        if image_path_to_process and os.path.exists(image_path_to_process):
            try:
                os.remove(image_path_to_process)
                print(f"[*] Cleaned up temp file: {image_path_to_process}")
            except OSError as e:
                print(f"[*] Warning: Could not remove temp file {image_path_to_process}: {e}")
        # Optionally clean up output files (or leave for debugging)
        # if os.path.exists(output_txt_path): os.remove(output_txt_path)
        # if os.path.exists(output_json_path): os.remove(output_json_path)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)