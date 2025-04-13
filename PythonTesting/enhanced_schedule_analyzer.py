#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
import asyncio # Import asyncio
from PIL import Image
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
import re
from collections import defaultdict


def setup_gemini_api(api_key):
    """Set up the Gemini API with the provided API key."""
    genai.configure(api_key=api_key)
    # Use gemini-2.0-flash for both vision and analysis for speed
    flash_model = genai.GenerativeModel(
        'gemini-2.0-flash')  # Changed model name
    return {
        'vision_model': flash_model,
        'analysis_model': flash_model
    }


def print_progress(message):
    """Print a progress message with a consistent format."""
    print(f"[*] {message}")


def print_progress_bar(iteration, total, prefix='', suffix='', length=50, fill='█'):
    """Print a progress bar in the console."""
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        print()

# ===== STEP 1: Extract courses from schedule image (Optional) =====


def extract_courses_from_image(image_path, vision_model):
    """Extract course IDs and sections from an image using Gemini API."""
    if "manual_input_" in os.path.basename(image_path) and ".dummy" in image_path:
        print_progress("Skipping image analysis for manual input.")
        return None

    try:
        print_progress(f"Analyzing schedule image: {image_path}")
        img = Image.open(image_path)
        prompt = """
        Extract all course IDs and section numbers from this UMD class schedule image.
        Format the output as a JSON array of objects with exactly these fields:
        - course_id: The course ID (e.g., "CMSC132")
        - section: The section number (e.g., "0201")
        Example output: [{"course_id": "CMSC132", "section": "0201"}, {"course_id": "MATH141", "section": "0301"}]
        Only include courses with both a valid course ID and section number.
        """
        print_progress("Sending image to Gemini vision model...")
        # Vision model call remains synchronous for now
        response = vision_model.generate_content([prompt, img], request_options={'timeout': 60})
        print_progress("Image processed.")
        json_text = response.text
        json_match = re.search(r'\[(.*?)\]', json_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                courses = json.loads(json_str)
                print_progress(
                    f"Successfully extracted {len(courses)} courses from image")
                return courses
            except json.JSONDecodeError as e:
                print_progress(
                    f"Error parsing JSON from Gemini response: {e}\nRaw JSON string: {json_str}")
                return []
        else:
            print_progress(
                f"No valid JSON found in Gemini response.\nRaw response: {json_text}")
            return []
    except FileNotFoundError:
        print_progress(f"Error: Image file not found at {image_path}.")
        return []
    except Exception as e:
        print_progress(f"Error processing image: {e}")
        return []

# ===== STEP 2: Get course and section information =====


def build_testudo_url(course_id, section_id=None, term_id="202508"):
    base_url = "https://app.testudo.umd.edu/soc/search"
    params = {"courseId": course_id.upper(), "termId": term_id}
    if section_id:
        params["sectionId"] = section_id
    query_parts = [f"{key}={value}" for key, value in params.items()]
    additional_params = [
        "creditCompare=", "credits=", "courseLevelFilter=ALL", "instructor=",
        "_facetoface=on", "_blended=on", "_online=on", "courseStartCompare=",
        "courseStartHour=", "courseStartMin=", "courseStartAM=", "courseEndHour=",
        "courseEndMin=", "courseEndAM=", "teachingCenter=ALL", "_classDay1=on",
        "_classDay2=on", "_classDay3=on", "_classDay4=on", "_classDay5=on"
    ]
    query_parts.extend(additional_params)
    query_string = "&".join(query_parts)
    return f"{base_url}?{query_string}"


def get_section_directly(course_id, section_id, term_id="202508"):
    # This remains synchronous
    course_id = course_id.upper()
    section_id = section_id.strip().zfill(4)
    print_progress(
        f"Searching Testudo for {course_id} section {section_id} for term {term_id}")
    url = build_testudo_url(course_id, section_id, term_id)
    try:
        response = requests.get(url, timeout=10)  # Added timeout
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        course_divs = soup.find_all('div', class_='course')
        if not course_divs:
            print_progress("No matching course found on Testudo.")
            return None
        course_title = ""
        for course_div in course_divs:
            title_elem = course_div.find('span', class_='course-title')
            if title_elem:
                course_title = title_elem.text.strip()
                break
        all_section_divs = []
        for course_div in course_divs:
            section_divs = course_div.find_all(['div', 'tr'], class_=[
                                               'section', 'section-info-container'])  # Look for divs or table rows
            all_section_divs.extend(section_divs)
        if not all_section_divs:
            print_progress(
                "Course found, but no section divs/rows detected in HTML structure.")
            return None

        for section_container in all_section_divs:
            section_id_elem = section_container.find(
                ['span', 'td'], class_=['section-id', 'section-id-container'])
            if not section_id_elem:
                continue
            current_section_id = section_id_elem.text.strip()
            if current_section_id == section_id:
                instructors = []
                instructor_elems = section_container.find_all(
                    ['div', 'span', 'td'], class_=['section-instructor', 'section-instructors'])
                for instructor_elem in instructor_elems:
                    instructor_name = instructor_elem.text.strip()
                    if instructor_name and "TBA" not in instructor_name:
                        match = re.search(
                            r'Instructor(?:s)?:\s*(.*)', instructor_name, re.IGNORECASE)
                        instructors.append(match.group(
                            1).strip() if match else instructor_name)
                class_days_elem = section_container.find(
                    ['span', 'td'], class_=['section-days', 'section-days-container'])
                class_start_time_elem = section_container.find(
                    ['span', 'td'], class_=['class-start-time', 'section-start-time-container'])
                class_end_time_elem = section_container.find(
                    ['span', 'td'], class_=['class-end-time', 'section-end-time-container'])
                days = class_days_elem.text.strip() if class_days_elem else ""
                time_str = f"{class_start_time_elem.text.strip()} - {class_end_time_elem.text.strip()}" if class_start_time_elem and class_end_time_elem else ""
                return {'course_id': course_id, 'course_title': course_title, 'section_id': section_id, 'instructors': instructors, 'days': days, 'time': time_str}
        print_progress(
            f"Section {section_id} details not found within the course page.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Testudo data: {e}")
        return None
    except Exception as e:
        print(f"Error processing Testudo data: {e}")
        return None

# ===== STEP 3: Enhanced PlanetTerp API Interaction =====


def search_planetterp_professors(course_id=None):
    # This remains synchronous
    if not course_id:
        return []
    print_progress(
        f"Searching PlanetTerp for professors who've taught {course_id}...")
    api_url = f"https://api.planetterp.com/v1/course?name={course_id}"
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code != 200:
            print_progress(f"PlanetTerp Error: Status {response.status_code}")
            return []
        data = response.json()
        if "error" in data:
            print_progress(f"PlanetTerp Error: {data['error']}")
            return []
        return data.get("professors", [])
    except Exception as e:
        print_progress(f"Error searching PlanetTerp professors: {e}")
        return []


def get_professor_reviews(professor_name, course_id=None):
    # This remains synchronous
    if not professor_name:
        return []
    print_progress(f"Fetching PlanetTerp reviews for {professor_name}" + (
        f" teaching {course_id}" if course_id else ""))
    api_url = f"https://api.planetterp.com/v1/professor?name={professor_name}&reviews=true"
    try:
        # Longer timeout for potentially large review data
        response = requests.get(api_url, timeout=15)
        if response.status_code != 200:
            print_progress(f"PlanetTerp Error: Status {response.status_code}")
            return []
        data = response.json()
        if "error" in data:
            print_progress(f"PlanetTerp Error: {data['error']}")
            return []
        all_reviews = data.get("reviews", [])
        if course_id:
            filtered_reviews = [
                r for r in all_reviews if r.get("course") == course_id]
            print_progress(
                f"Found {len(filtered_reviews)} reviews for {professor_name} teaching {course_id}")
            return filtered_reviews
        else:
            print_progress(
                f"Found {len(all_reviews)} total reviews for {professor_name}")
            return all_reviews
    except Exception as e:
        print_progress(f"Error processing PlanetTerp reviews: {e}")
        return []


def research_professor_and_course(professor_name, course_id, course_info=None):
    # This remains synchronous
    research_data = {
        'course_id': course_id, 'professor': professor_name,
        'course_title': course_info.get('course_title', '') if course_info else '',
        'section_id': course_info.get('section_id', '') if course_info else '',
        'schedule': f"{course_info.get('days', '')} {course_info.get('time', '')}".strip() if course_info else '',
        'direct_reviews': [], 'professor_other_reviews': [], 'course_other_reviews': [],
        'professor_other_courses': [], 'course_other_professors': []
    }
    print_progress(
        f"RESEARCH STEP 1: Direct reviews for {professor_name} teaching {course_id}")
    research_data['direct_reviews'] = get_professor_reviews(
        professor_name, course_id)
    direct_review_count = len(research_data['direct_reviews'])
    ratings = [r.get("rating") for r in research_data['direct_reviews'] if r.get(
        "rating") is not None]
    research_data['avg_rating'] = sum(ratings) / len(ratings) if ratings else 0
    research_data['review_count'] = len(ratings)
    print_progress(
        f"Found {direct_review_count} direct reviews for {professor_name} teaching {course_id}")
    if direct_review_count >= 5:
        print_progress(
            f"Found sufficient direct reviews ({direct_review_count}). Skipping additional research.")
        return research_data

    print_progress(
        f"RESEARCH STEP 2: Other courses taught by {professor_name}")
    all_professor_reviews = get_professor_reviews(
        professor_name)  # Get all reviews for the prof
    research_data['professor_other_reviews'] = [r for r in all_professor_reviews if r.get(
        "course") != course_id and r.get("course") is not None]
    research_data['professor_other_courses'] = sorted(list(set(r.get(
        # Sort courses
        "course") for r in research_data['professor_other_reviews'] if r.get("course") is not None)))
    print_progress(
        f"Found {len(research_data['professor_other_reviews'])} reviews for {professor_name} teaching other courses")
    if research_data['professor_other_courses']:
        print_progress(
            f"Other courses taught by {professor_name}: {', '.join(research_data['professor_other_courses'])}")

    print_progress(
        f"RESEARCH STEP 3: Other professors who've taught {course_id}")
    all_professors = search_planetterp_professors(course_id)
    research_data['course_other_professors'] = sorted(
        [p for p in all_professors if p != professor_name])  # Sort professors
    print_progress(
        f"Found {len(research_data['course_other_professors'])} other professors who've taught {course_id}")
    other_prof_reviews = []
    # Get reviews from a sample of other professors
    # Limit to 3 other professors for brevity
    for prof in research_data['course_other_professors'][:3]:
        print_progress(
            f"Getting sample reviews for {course_id} taught by {prof}")
        prof_reviews = get_professor_reviews(prof, course_id)
        # Take at most 5 reviews per professor
        other_prof_reviews.extend(prof_reviews[:5])
    research_data['course_other_reviews'] = other_prof_reviews
    print_progress(
        f"Collected {len(research_data['course_other_reviews'])} sample reviews for {course_id} from other professors")
    return research_data


def process_review_data(reviews):
    # This remains synchronous
    if not reviews:
        return []
    review_data = []
    total = len(reviews)
    for i, review in enumerate(reviews):
        # Removed progress bar from here for cleaner async logs
        # if i % 10 == 0 or i == total - 1: print_progress_bar(...)
        course = review.get("course", "Unknown") or "Unknown"
        rating = review.get("rating")
        grade = review.get("grade", "")
        review_text = review.get("review", "")
        date = review.get("created", "")[:10] if review.get("created") else ""
        review_data.append({"Course": course, "Rating": rating,
                           "Expected Grade": grade, "Review": review_text, "Date": date})
    return review_data

# ===== STEP 4: Generate AI summaries (NOW ASYNC) =====


async def generate_enhanced_course_summary(research_data, analysis_model): # Make async
    print_progress(
        f"Generating AI analysis for {research_data['course_id']} with {research_data['professor']}...")
    course_id = research_data['course_id']
    professor = research_data['professor']
    course_title = research_data['course_title']
    schedule = research_data['schedule']
    direct_reviews_processed = process_review_data(
        research_data['direct_reviews'])
    direct_reviews_text = "\n\n".join(
        # Simplified format
        [f"DIRECT REVIEW (Rating: {r['Rating']}/5): {r['Review']}" for r in direct_reviews_processed[:10] if r["Review"]])
    prof_other_reviews_processed = process_review_data(
        research_data['professor_other_reviews'])
    prof_other_courses = research_data['professor_other_courses']
    prof_other_reviews_text = "\n\n".join(
        [f"PROF OTHER COURSE REVIEW ({r['Course']} - Rating: {r['Rating']}/5): {r['Review']}" for r in prof_other_reviews_processed[:10] if r["Review"]])
    course_other_reviews_processed = process_review_data(
        research_data['course_other_reviews'])
    course_other_professors = research_data['course_other_professors']
    # Extract professor names from course_other_reviews if available
    other_prof_names_in_reviews = list(
        set(r.get('Professor', 'Unknown') for r in course_other_reviews_processed))
    course_other_reviews_text = "\n\n".join(
        [f"COURSE OTHER PROF REVIEW (Prof: {r.get('Professor', 'Unknown')} - Rating: {r['Rating']}/5): {r['Review']}" for r in course_other_reviews_processed[:10] if r["Review"]])
    avg_rating = research_data['avg_rating']
    review_count = research_data['review_count']

    # Simplified prompt focusing on key info
    prompt = f"""
    Analyze UMD course {course_id} ({course_title}) taught by Professor {professor}. Schedule: {schedule}

    Key Information:
    - Direct Reviews ({review_count} total, avg rating {avg_rating:.2f}/5): {direct_reviews_text or 'None available.'}
    - Professor Context (also teaches {', '.join(prof_other_courses) or 'N/A'}): {prof_other_reviews_text or 'None available.'}
    - Course Context (other profs include {', '.join(course_other_professors[:3]) or 'N/A'}): {course_other_reviews_text or 'None available.'}

    Instructions:
    Provide a balanced analysis based *only* on the information above. For each category below, give a score (out of 100) and a concise explanation, citing evidence (e.g., "direct reviews mention...", "reviews for other courses suggest..."). If information is insufficient, state that clearly and assign a neutral score (e.g., 50/100) or indicate N/A.
    1.  **Teaching Quality:** (Clarity, engagement, effectiveness)
    2.  **Course Difficulty:** (Challenging concepts, exams, assignments)
    3.  **Workload:** (Time commitment, amount of homework/reading)
    4.  **Grading Fairness:** (Lenient/strict, clear criteria, curves)
    5.  **Organization/Structure:** (Pacing, syllabus clarity, flow)
    6.  **Professor Approachability:** (Helpfulness, responsiveness, demeanor)
    7.  **Overall Value:** (Learning experience, relevance, recommendation)

    Finally, write a 1-2 paragraph **General Summary** synthesizing the key points for a student considering this specific course/professor combination. Focus on being helpful and objective. Use Markdown for formatting (like **bold** scores).
    """
    print_progress(f"Sending prompt for {course_id} to Gemini...") # Log before await
    try:
        # Use the async method with timeout
        response = await analysis_model.generate_content_async(prompt, request_options={'timeout': 120}) # Use await and async method
        print_progress(f"Received analysis for {course_id}") # Log after await
        # Basic check for empty or error response from model
        if not response.text or "error" in response.text.lower():
            raise ValueError("Model returned empty or error response.")
        return {
            'course_id': course_id, 'course_title': course_title, 'section_id': research_data.get('section_id', ''),
            'professor': professor, 'schedule': schedule, 'avg_rating': avg_rating, 'review_count': review_count,
            'summary': response.text,
            # Pass full research data back for potential use in JSON export
            'research_stats': research_data
        }
    except Exception as e:
        print_progress(f"Error generating AI summary for {course_id}: {e}")
        # Return error structure
        return {
            'course_id': course_id, 'course_title': course_title, 'section_id': research_data.get('section_id', ''),
            'professor': professor, 'schedule': schedule, 'avg_rating': avg_rating, 'review_count': review_count,
            'summary': f"Error generating AI summary: {e}",
            'research_stats': research_data # Still return research data
        }


async def generate_overall_schedule_summary(course_summaries, analysis_model): # Make async
    print_progress("Generating overall schedule analysis...")
    courses_text = ""
    for idx, summary in enumerate(course_summaries, 1):
        # Include key details used by the prompt
        courses_text += f"\n{idx}. {summary['course_id']} ({summary.get('course_title', 'N/A')}) - Prof: {summary.get('professor', 'N/A')} ({summary.get('avg_rating', 0):.1f}/5, {summary.get('review_count', 0)} rev) - Sched: {summary.get('schedule', 'N/A')}"

    prompt = f"""
    Analyze the following UMD schedule consisting of {len(course_summaries)} course(s):
    {courses_text}

    Instructions:
    1.  **VERY IMPORTANT:** Start the entire response *immediately* with a single line formatted exactly like this: `Overall Schedule Grade: XX/100` where XX is your calculated overall score. Do not add any text before this line.
    2.  After the grade line, provide a comprehensive analysis with scores (out of 100) and detailed paragraph explanations for the following categories:
        *   **Overall Workload:** (Consider course levels, number of courses, known demands)
        *   **Professor Quality:** (Based on average ratings and review counts provided)
        *   **Schedule Balance:** (Timing, back-to-back classes, day distribution)
        *   **Subject Synergy:** (How well course topics might complement or conflict)
        *   **Difficulty Management:** (Combined challenge, potential bottlenecks)
        *   **Overall Schedule Quality:** (Synthesize pros/cons, offer advice/strategies - this is separate from the grade line at the start)

    Base your analysis *only* on the information provided about the courses in the list. Use Markdown for formatting (like **bold** scores within the category explanations).
    """
    print_progress("Sending overall prompt to Gemini...") # Log before await
    try:
        # Use the async method with timeout
        response = await analysis_model.generate_content_async(prompt, request_options={'timeout': 120}) # Use await and async method
        print_progress("Received overall analysis.") # Log after await
        if not response.text or "error" in response.text.lower():
            raise ValueError(
                "Model returned empty or error response for overall summary.")
        return response.text
    except Exception as e:
        print_progress(f"Error generating overall summary: {e}")
        return f"Error generating overall schedule analysis: {e}"

# ===== STEP 5: Output results =====


def export_to_file(course_summaries, overall_summary, filename):
    # This remains synchronous
    print_progress(f"Exporting analysis to {filename}...")
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(
                f"UMD SCHEDULE ANALYSIS\nGenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("OVERALL SCHEDULE ANALYSIS\n" + "=" * 50 + "\n\n")
            f.write(overall_summary or "Overall summary generation failed.")
            f.write("\n\n" + "=" * 50 +
                    "\n\nINDIVIDUAL COURSE ANALYSES\n" + "=" * 50 + "\n\n")
            if not course_summaries:
                f.write("No individual course analyses were generated.\n")
            for idx, summary in enumerate(course_summaries, 1):
                f.write(
                    f"COURSE {idx}: {summary.get('course_id', 'N/A')} - {summary.get('course_title', 'N/A')}\n")
                f.write(
                    f"Section: {summary.get('section_id', 'N/A')}\nProfessor: {summary.get('professor', 'N/A')}\nSchedule: {summary.get('schedule', 'N/A')}\n")
                f.write(
                    f"Average Rating: {summary.get('avg_rating', 0):.2f}/5 ({summary.get('review_count', 0)} reviews)\n")
                stats = summary.get('research_stats', {}) # Use .get for safety
                if stats and isinstance(stats, dict): # Check if it's a dict
                    # Get lengths of the review lists for counts
                    direct_reviews_count = len(stats.get('direct_reviews', []))
                    prof_other_reviews_count = len(stats.get('professor_other_reviews', []))
                    course_other_reviews_count = len(stats.get('course_other_reviews', []))
                    f.write(
                        f"Research Depth: {direct_reviews_count} direct, {prof_other_reviews_count} prof-other, {course_other_reviews_count} course-other\n")
                    # Use len() for lists within stats
                    prof_courses = stats.get('professor_other_courses', [])
                    other_profs = stats.get('course_other_professors', [])
                    if prof_courses: f.write(f"                Professor teaches {len(prof_courses)} other courses\n")
                    if other_profs: f.write(f"                Course is taught by {len(other_profs)} other professors\n")
                f.write("\nANALYSIS:\n")
                f.write(summary.get('summary', 'Summary generation failed.'))
                f.write("\n\n" + "-" * 50 + "\n\n")
        print_progress(f"Analysis exported to {filename}")
    except Exception as e:
        print_progress(f"Error exporting text file: {e}")


def parse_overall_grade(summary_text):
    """Extracts the overall grade from the summary text."""
    if not summary_text:
        return None
    match = re.search(r"Overall Schedule Grade:\s*(\d{1,3})\s*/\s*100", summary_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None

def export_to_json(course_summaries, overall_summary_text, filename):
     # This remains synchronous
    print_progress(f"Exporting JSON data to {filename}...")

    # Parse the overall grade
    overall_grade = parse_overall_grade(overall_summary_text)
    print_progress(f"Parsed Overall Grade: {overall_grade}") # Log parsed grade

    # Ensure research_stats is serializable
    serializable_summaries = []
    for summary in course_summaries:
        s_copy = summary.copy()
        if 'research_stats' in s_copy and isinstance(s_copy['research_stats'], dict):
             s_copy['research_stats']['professor_other_courses'] = list(s_copy['research_stats'].get('professor_other_courses', []))
             s_copy['research_stats']['course_other_professors'] = list(s_copy['research_stats'].get('course_other_professors', []))
             s_copy['research_stats']['direct_reviews'] = list(s_copy['research_stats'].get('direct_reviews', []))
             s_copy['research_stats']['professor_other_reviews'] = list(s_copy['research_stats'].get('professor_other_reviews', []))
             s_copy['research_stats']['course_other_reviews'] = list(s_copy['research_stats'].get('course_other_reviews', []))
        else:
             s_copy['research_stats'] = {}
        serializable_summaries.append(s_copy)

    json_data = {
        "metadata": {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "course_count": len(serializable_summaries)},
        "overall_grade": overall_grade, # Add the parsed grade
        "overall_analysis": overall_summary_text or "Overall summary generation failed.",
        "courses": serializable_summaries
    }
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
        print_progress(f"JSON data exported to {filename}")
    except TypeError as e:
        print_progress(f"Error exporting JSON file (likely non-serializable data): {e}")
        # Attempt to dump without problematic keys for debugging
        try:
            for course in json_data['courses']: course.pop('research_stats', None)
            fallback_filename = filename.replace(".json", ".err_fallback.json")
            with open(fallback_filename, 'w', encoding='utf-8') as f:
                 json.dump(json_data, f, indent=2)
            print_progress(f"Fallback JSON (without research_stats) saved to {fallback_filename}")
        except Exception as e2:
             print_progress(f"Fallback JSON export also failed: {e2}")
    except Exception as e:
        print_progress(f"Error exporting JSON file: {e}")


async def main():  # Make main async
    parser = argparse.ArgumentParser(
        description='Enhanced UMD schedule analyzer')
    parser.add_argument('image_path', nargs='?', default=None,
                        help='Path to the image file (optional if --courses-json is used)')
    parser.add_argument(
        '--courses-json', help='JSON string of courses [{"course_id": "ID", "section": "SEC"}, ...]')
    parser.add_argument('--term', default='202508',
                        help='Term ID (default: 202508)')
    parser.add_argument(
        '--output', default='enhanced_schedule_analysis.txt', help='Output text file name')
    parser.add_argument('--json', default='schedule_data.json',
                        help='JSON output file name')
    parser.add_argument('--api-key', help='Gemini API key')
    args = parser.parse_args()

    print("=" * 50 + "\nENHANCED UMD SCHEDULE ANALYZER (Async)\n" + "=" * 50)

    if not args.image_path and not args.courses_json:
        parser.error("Either image_path or --courses-json must be provided.")
    if args.image_path and not os.path.exists(args.image_path) and not args.courses_json:
        print(f"Error: Image file '{args.image_path}' not found.")
        sys.exit(1)

    api_key = args.api_key or os.environ.get('GEMINI_API_KEY') or input(
        "Enter your Gemini API key: ").strip()
    if not api_key:
        print("Error: Gemini API key is required.")
        sys.exit(1)

    print_progress("Setting up Gemini API...")
    models = setup_gemini_api(api_key)

    courses = []
    processed_combinations = set()  # Keep track of processed course-section pairs

    if args.courses_json:
        print_progress("Using courses provided via --courses-json argument.")
        try:
            input_courses = json.loads(args.courses_json)
            if not isinstance(input_courses, list):
                raise ValueError("JSON input must be a list.")
            for course in input_courses:
                if not isinstance(course, dict) or 'course_id' not in course or 'section' not in course:
                    raise ValueError(
                        "Each course object must have 'course_id' and 'section'.")
                # Add check for duplicates before adding to the list to process
                course_key = (course['course_id'].upper(),
                              course['section'].strip().zfill(4))
                if course_key not in processed_combinations:
                    courses.append(course)
                    processed_combinations.add(course_key)
                else:
                    print_progress(
                        f"Skipping duplicate input: {course_key[0]}-{course_key[1]}")
            print_progress(
                f"Processing {len(courses)} unique courses from JSON.")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing --courses-json: {e}")
            sys.exit(1)
    elif args.image_path:
        extracted_courses = extract_courses_from_image(
            args.image_path, models['vision_model'])
        if extracted_courses:
            for course in extracted_courses:
                course_key = (course['course_id'].upper(),
                              course['section'].strip().zfill(4))
                if course_key not in processed_combinations:
                    courses.append(course)
                    processed_combinations.add(course_key)
                else:
                    print_progress(
                        f"Skipping duplicate extracted from image: {course_key[0]}-{course_key[1]}")
            print_progress(
                f"Processing {len(courses)} unique courses from image.")

    if not courses:
        print_progress("No unique courses found or provided.")
        # Ensure output files are created even if empty
        open(args.output, 'w').close()
        with open(args.json, 'w') as f:
            json.dump(
                {"metadata": {}, "overall_analysis": "No courses found.", "courses": []}, f)
        sys.exit(0)  # Exit gracefully

    print_progress(
        f"Processing {len(courses)} unique courses for term {args.term}:")
    for i, course in enumerate(courses, 1):
        print(f"{i}. {course['course_id']} Section {course['section']}")

    # --- Gather Research Data Sequentially ---
    research_tasks_data = []
    print_progress("Gathering course and review data sequentially...")
    for i, course in enumerate(courses, 1):
        print("\n" + "=" * 30 + f" Researching Course {i}/{len(courses)}: {course['course_id']}-{course['section']} " + "=" * 30)
        course_info = get_section_directly(course['course_id'], course['section'], args.term)
        if not course_info:
            print_progress(f"Could not find Testudo info. Trying PlanetTerp...")
            course_info = {'course_id': course['course_id'], 'section_id': course['section'], 'instructors': ['Unknown']} # Minimal info

        professors = course_info.get('instructors', [])
        professor_to_analyze = 'Unknown' # Default
        if professors and professors != ['Unknown']:
             professor_to_analyze = professors[0] # Use first listed professor
        else:
             # Try PlanetTerp if Testudo failed or gave TBA
             print_progress(f"Searching PlanetTerp for professors of {course['course_id']}...")
             pt_profs = search_planetterp_professors(course['course_id'])
             if pt_profs:
                  professor_to_analyze = pt_profs[0] # Use first found from PlanetTerp
                  print_progress(f"Found potential professor via PlanetTerp: {professor_to_analyze}")
             else:
                  print_progress(f"No professor found for {course['course_id']}. Cannot generate detailed analysis.")

        if professor_to_analyze != 'Unknown':
             # Store data needed for summary generation
             research_data = research_professor_and_course(professor_to_analyze, course['course_id'], course_info)
             research_tasks_data.append(research_data)
        else:
             # Append placeholder for courses without a professor
             research_tasks_data.append({
                 'course_id': course['course_id'], 'course_title': course_info.get('course_title', 'N/A'),
                 'section_id': course['section'], 'professor': 'Unknown', 'schedule': 'N/A',
                 'avg_rating': 0, 'review_count': 0, 'summary': 'Professor information unavailable. Cannot perform detailed analysis.',
                 'research_stats': {}
             })

    # --- Generate Individual Summaries Concurrently ---
    print("\n" + "=" * 50 + "\nGENERATING INDIVIDUAL COURSE SUMMARIES (CONCURRENTLY)\n" + "=" * 50)
    summary_tasks = []
    for data in research_tasks_data:
        if data.get('professor') != 'Unknown': # Only generate summary if we have a professor
             summary_tasks.append(
                 # Create an awaitable task for each summary generation
                 asyncio.create_task(generate_enhanced_course_summary(data, models['analysis_model']))
             )
        else:
             # If professor was unknown, create a task that immediately returns the placeholder data
             summary_tasks.append(asyncio.sleep(0, result=data)) # Use asyncio.sleep(0, result=...)

    # Run tasks concurrently and gather results
    # Results will be in the order the tasks were created
    course_summaries = await asyncio.gather(*summary_tasks)

    # Filter out potential None results if any task failed unexpectedly, though errors should be handled within generate_enhanced_course_summary
    course_summaries = [s for s in course_summaries if s is not None]

    if not course_summaries: print_progress("No course summaries generated."); sys.exit(1)

    # --- Generate Overall Summary Sequentially (after individuals are done) ---
    print("\n" + "=" * 50 + "\nGENERATING OVERALL SCHEDULE ANALYSIS\n" + "=" * 50)
    overall_summary = await generate_overall_schedule_summary(course_summaries, models['analysis_model']) # Await the async function

    # --- Export Results ---
    export_to_file(course_summaries, overall_summary, args.output)
    export_to_json(course_summaries, overall_summary, args.json)

    print("\nEnhanced analysis complete! ✅")
    print(f"Results saved to {args.output}")
    print(f"JSON data saved to {args.json}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
