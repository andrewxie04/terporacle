document.addEventListener('DOMContentLoaded', () => {
    const analyzeForm = document.getElementById('analyze-form');
    const apiKeyInput = document.getElementById('api-key');
    const termSelect = document.getElementById('term-select');
    const courseListDiv = document.getElementById('course-list');
    const addCourseButton = document.getElementById('add-course-button');
    const loadingIndicator = document.getElementById('loading-indicator');
    const resultsArea = document.getElementById('results-area');
    const overallAnalysisContent = document.getElementById('overall-analysis-content');
    const individualCoursesContent = document.getElementById('individual-courses-content');
    const errorArea = document.getElementById('error-area');
    const errorOutput = document.getElementById('error-output');
    const analyzeButton = document.getElementById('analyze-button');

    // Input method elements
    const inputMethodRadios = document.querySelectorAll('input[name="inputMethod"]');
    const imageUploadSection = document.getElementById('image-upload-section');
    const manualInputSection = document.getElementById('manual-input-section');
    const scheduleImageInput = document.getElementById('schedule-image'); // Image input
    const fileNameSpan = document.getElementById('file-name'); // Image file name display

    // --- Input Method Switching ---

    function updateInputMethodView() {
        const selectedMethod = document.querySelector('input[name="inputMethod"]:checked').value;
        if (selectedMethod === 'image') {
            imageUploadSection.style.display = 'block';
            manualInputSection.style.display = 'none';
            scheduleImageInput.required = true; // Make image required
            manualInputSection.querySelectorAll('input').forEach(input => input.required = false);
        } else { // manual
            imageUploadSection.style.display = 'none';
            manualInputSection.style.display = 'block';
            scheduleImageInput.required = false; // Make image not required
            manualInputSection.querySelectorAll('input').forEach(input => input.required = true);
            if (courseListDiv.children.length === 0) {
                createCourseInputRow();
            }
        }
        errorArea.style.display = 'none';
    }

    inputMethodRadios.forEach(radio => {
        radio.addEventListener('change', updateInputMethodView);
    });
    updateInputMethodView();

    // --- Course Input Management (for manual section) ---

    function createCourseInputRow() {
        const row = document.createElement('div');
        row.className = 'course-input-row';

        const courseIdInput = document.createElement('input');
        courseIdInput.type = 'text';
        courseIdInput.placeholder = 'Course ID (e.g., CMSC132)';
        courseIdInput.className = 'course-id';
        courseIdInput.required = (document.querySelector('input[name="inputMethod"]:checked').value === 'manual');

        const sectionInput = document.createElement('input');
        sectionInput.type = 'text';
        sectionInput.placeholder = 'Section (e.g., 0101)';
        sectionInput.className = 'course-section';
        sectionInput.required = (document.querySelector('input[name="inputMethod"]:checked').value === 'manual');

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.textContent = 'Remove';
        removeButton.className = 'remove-course-button';
        removeButton.onclick = () => {
            row.remove();
            updateRemoveButtons();
        };

        row.appendChild(courseIdInput);
        row.appendChild(sectionInput);
        row.appendChild(removeButton);
        courseListDiv.appendChild(row);
        updateRemoveButtons();
    }

    function updateRemoveButtons() {
        const rows = courseListDiv.querySelectorAll('.course-input-row');
        rows.forEach((row, index) => {
            const button = row.querySelector('.remove-course-button');
            button.disabled = rows.length <= 1;
        });
    }

    addCourseButton.addEventListener('click', createCourseInputRow);

    scheduleImageInput.addEventListener('change', () => {
        if (scheduleImageInput.files.length > 0) {
            fileNameSpan.textContent = scheduleImageInput.files[0].name;
        } else {
            fileNameSpan.textContent = 'Click or drag to upload schedule image';
        }
    });

    // --- Form Submission ---

    analyzeForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const apiKey = apiKeyInput.value;
        const termId = termSelect.value;
        const selectedMethod = document.querySelector('input[name="inputMethod"]:checked').value;

        errorArea.style.display = 'none';
        resultsArea.style.display = 'none';
        loadingIndicator.style.display = 'block';
        analyzeButton.disabled = true;
        analyzeButton.textContent = 'Analyzing...';

        let requestBody;
        let fetchOptions = { method: 'POST' };

        try {
            if (selectedMethod === 'image') {
                const file = scheduleImageInput.files[0];
                if (!file) throw new Error('Please select an image file.');
                if (!apiKey) throw new Error('Please enter your Gemini API Key.');

                const formData = new FormData();
                formData.append('scheduleImage', file);
                formData.append('apiKey', apiKey);
                formData.append('termId', termId);
                requestBody = formData;
            } else { // manual
                const courseRows = courseListDiv.querySelectorAll('.course-input-row');
                const courses = [];
                let formIsValid = true;
                courseRows.forEach(row => {
                    const courseId = row.querySelector('.course-id').value.trim().toUpperCase();
                    const section = row.querySelector('.course-section').value.trim();
                    if (courseId && section) {
                        courses.push({ course_id: courseId, section: section });
                    } else {
                        formIsValid = false;
                    }
                });

                if (!apiKey) throw new Error('Please enter your Gemini API Key.');
                if (!formIsValid || courses.length === 0) throw new Error('Please fill in all Course ID and Section fields.');

                const payload = { apiKey, termId, courses };
                requestBody = JSON.stringify(payload);
                fetchOptions.headers = { 'Content-Type': 'application/json' };
            }

            fetchOptions.body = requestBody;
            const response = await fetch('/analyze', fetchOptions);
            const result = await response.json();

            if (!response.ok) {
                // Include stderr in the error message if available
                const errorDetails = result.stderr ? `\n\nServer Error Details:\n${result.stderr}` : '';
                throw new Error((result.error || `Server error: ${response.status}`) + errorDetails);
            }

            displayResults(result);

        } catch (error) {
            console.error('Error during analysis:', error);
            showError(`Analysis failed: ${error.message}. Check console for details.`);
        } finally {
            loadingIndicator.style.display = 'none';
            analyzeButton.disabled = false;
            analyzeButton.textContent = 'Analyze Schedule';
        }
    });

    // --- Display Results ---

    // Simple Markdown Renderer (handles **bold** and newlines)
    function renderMarkdown(text) {
        if (!text) return '';
        // Escape HTML characters first to prevent XSS
        let escapedText = text.replace(/&/g, '&amp;')
                              .replace(/</g, '<')
                              .replace(/>/g, '>')
                              .replace(/"/g, '"')
                              .replace(/'/g, '&#039;');

        // Convert **bold** to <strong>
        let boldedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Convert newlines to <br>
        return boldedText.replace(/\n/g, '<br>');
    }


    function displayResults(data) {
        // Clear previous results
        overallAnalysisContent.innerHTML = '';
        individualCoursesContent.innerHTML = '';
        const gradeDisplay = document.getElementById('overall-grade-display');
        const gradeValueSpan = gradeDisplay.querySelector('.grade-value');
        gradeDisplay.style.display = 'none'; // Hide initially
        gradeValueSpan.textContent = '--'; // Reset grade value

        if (data.error) {
            showError(data.error + (data.stderr ? `\n\nServer Error Details:\n${data.stderr}` : ''));
            return;
        }

        // Display Overall Grade if available
        if (data.overall_grade !== null && data.overall_grade !== undefined) {
            gradeValueSpan.textContent = data.overall_grade;
            gradeDisplay.style.display = 'block'; // Show the grade display
        }

        // Display Overall Analysis using Markdown renderer
        // Remove the grade line from the text before rendering if it exists
        let analysisText = data.overall_analysis || 'Overall analysis not available.';
        analysisText = analysisText.replace(/^Overall Schedule Grade:\s*\d+\s*\/\s*100\s*\n?/, ''); // Remove grade line
        overallAnalysisContent.innerHTML = renderMarkdown(analysisText);

        // Display Individual Course Analyses
        if (data.courses && data.courses.length > 0) {
            data.courses.forEach(course => {
                const card = document.createElement('div');
                card.className = 'course-card';

                const title = document.createElement('h4');
                title.textContent = `${course.course_id} - ${course.course_title || 'N/A'}`;
                card.appendChild(title);

                const meta = document.createElement('div');
                meta.className = 'course-meta';
                meta.innerHTML = `
                    <span>Section: <strong>${course.section_id || 'N/A'}</strong></span>
                    <span>Professor: <strong>${course.professor || 'N/A'}</strong></span><br>
                    <span>Schedule: <strong>${course.schedule || 'N/A'}</strong></span>
                    <span>Avg Rating: <strong>${course.avg_rating !== undefined ? course.avg_rating.toFixed(2) + '/5' : 'N/A'} (${course.review_count || 0} reviews)</strong></span>
                `;
                if (course.research_stats) {
                    const stats = course.research_stats;
                    const researchP = document.createElement('p');
                    researchP.style.fontSize = '0.85em';
                    // Calculate lengths safely, defaulting to 0 if key missing or not an array
                    const direct_reviews_count = Array.isArray(stats.direct_reviews) ? stats.direct_reviews.length : 0;
                    const prof_other_reviews_count = Array.isArray(stats.professor_other_reviews) ? stats.professor_other_reviews.length : 0;
                    const course_other_reviews_count = Array.isArray(stats.course_other_reviews) ? stats.course_other_reviews.length : 0;
                    researchP.innerHTML = `<i>Research Depth: ${direct_reviews_count} direct, ${prof_other_reviews_count} prof-other, ${course_other_reviews_count} course-other</i>`;
                    meta.appendChild(researchP);
                }
                card.appendChild(meta);

                const summaryDiv = document.createElement('div');
                summaryDiv.className = 'analysis-summary';
                // Render individual summary using Markdown renderer
                summaryDiv.innerHTML = renderMarkdown(course.summary);
                card.appendChild(summaryDiv);

                individualCoursesContent.appendChild(card);
            });
        } else {
            const noCourses = document.createElement('p');
            noCourses.textContent = 'No individual course analyses available.';
            individualCoursesContent.appendChild(noCourses);
        }

        resultsArea.style.display = 'block';
    }

    function showError(message) {
        // Display errors in the designated area, preserving line breaks
        errorOutput.innerHTML = message.replace(/\n/g, '<br>');
        errorArea.style.display = 'block';
        resultsArea.style.display = 'none';
    }
});