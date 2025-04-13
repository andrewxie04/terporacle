# TerpOracle - UMD Schedule Analyzer

TerpOracle analyzes a University of Maryland (UMD) student's class schedule to provide comprehensive, AI-powered feedback and scores across several key categories, helping students make more informed decisions about their semester.

## Features

*   **Dual Input:** Analyze schedules by uploading an image or entering course/section details manually.
*   **AI Analysis:** Leverages Google Gemini (2.0 Flash) to generate insights on:
    *   Overall Workload
    *   Professor Quality (using PlanetTerp data)
    *   Schedule Balance
    *   Subject Synergy
    *   Difficulty Management
    *   Overall Schedule Quality & Grade
*   **Data Integration:** Combines information scraped from UMD Testudo and fetched from the PlanetTerp API.
*   **Concurrent Processing:** Uses `asyncio` to generate individual course analyses in parallel for faster results.
*   **Web Interface:** Simple, clean UI built with Flask and vanilla HTML/CSS/JS.

## How it Works

1.  **Input:** User provides a schedule image or enters courses manually, selects the term, and enters their Google Gemini API Key via the web UI.
2.  **Backend (Flask):** Receives the request, handles input (image processing or JSON parsing).
3.  **Core Script (`enhanced_schedule_analyzer.py`):**
    *   Extracts courses (if image provided) using Gemini Vision.
    *   Scrapes Testudo for official course details (professor, time).
    *   Fetches professor reviews/ratings from PlanetTerp API.
    *   Sends data to Gemini 2.0 Flash for concurrent individual course analysis.
    *   Sends individual summaries to Gemini 2.0 Flash for overall schedule analysis and grade.
    *   Outputs results to a JSON file.
4.  **Backend (Flask):** Reads the resulting JSON.
5.  **Frontend:** Receives the JSON data and displays the formatted analysis, overall grade, and individual course breakdowns.

## Setup and Running Locally

1.  **Clone the Repository (or ensure you have the files):**
    ```bash
    # If you haven't already:
    # git clone https://github.com/andrewxie04/terporacle.git
    # cd terporacle
    ```

2.  **Install Dependencies:**
    *   **Python:** Ensure you have Python 3 installed.
    *   **Flask & Requests:**
        ```bash
        pip install Flask Werkzeug requests beautifulsoup4 Pillow google-generativeai
        # Or potentially: pip3 install ...
        ```

3.  **Get Gemini API Key:**
    *   Obtain an API key from [Google AI Studio](https://aistudio.google.com/app/apikey) (click "Create API key").

4.  **Run the Flask Server:**
    *   Navigate to the `schedule-frontend` directory:
        ```bash
        cd schedule-frontend
        ```
    *   Run the server:
        ```bash
        python3 app.py
        # Or: python app.py
        ```

5.  **Access the App:**
    *   Open your web browser and go to `http://localhost:5001` (or the address shown in the terminal).

6.  **Use the App:**
    *   Enter your Gemini API key.
    *   Select the desired term.
    *   Choose either "Upload Image" or "Enter Manually".
    *   Provide the schedule input.
    *   Click "Analyze Schedule".

## Technologies Used

*   **Python:** Core logic, backend server.
*   **Flask:** Web framework for the backend API.
*   **Google Gemini API:** For vision (image extraction) and text generation (analysis).
*   **Requests:** For making HTTP requests to Testudo and PlanetTerp.
*   **BeautifulSoup4:** For parsing HTML scraped from Testudo.
*   **Pillow:** For image handling (if using image upload).
*   **Asyncio:** For concurrent Gemini API calls.
*   **HTML, CSS, JavaScript:** For the frontend web interface.
*   **Git & GitHub:** For version control and hosting.