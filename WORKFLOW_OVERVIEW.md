# Job Agent System: Detailed Request Flow Architecture

This document provides a comprehensive, step-by-step breakdown of exactly what happens in the Job Agent system, starting from the moment a user initiates a request, down to the final database record.

---

## Phase 1: Request Initiation (Frontend & API)

1. **User Interaction**
   - The user opens the React frontend (running on port `8082`, served via Nginx or Vite dev server).
   - They navigate to the "Workflow" tab and click **"Start Workflow"**, or they upload a new resume.
   - *Alternative CLI flow:* The user runs `python main.py --resume path/to/cv.pdf` directly from the terminal.

2. **Frontend API Call**
   - The React frontend (`src/api.js`) sends a `POST` request to the FastAPI backend at `/api/start-workflow`.
   - The payload includes the `resume_path` and `user_profile`.

3. **Backend API Handling (`server/app.py`)**
   - The `/api/start-workflow` endpoint receives the request.
   - It validates that a workflow isn't already running.
   - If no resume path is provided, it auto-detects the first `.pdf` in the project root or `uploads/` directory.
   - It spawns a background thread running the `_run_workflow_thread` function to prevent blocking the API.
   - The endpoint immediately returns a 200 OK with a `workflow_id`, while the heavy lifting starts in the background.

---

## Phase 2: Workflow Orchestration (LangGraph Setup)

4. **Background Thread Initialization**
   - Inside `_run_workflow_thread`, the `WorkflowManager` instance updates its state: `is_running = True`, `current_step = "initializing"`, `progress = 0`.
   - It broadcasts a WebSocket message to the frontend: `🚀 Workflow starting...`

5. **State & Graph Construction**
   - The system calls `build_initial_state` (`graph/state.py`) to create the root `JobAgentState`. This state dictionary acts as the shared memory for all agents (holding resume data, job lists, current index, scores, and logs).
   - The system calls `build_graph()` (`graph/workflow.py`), which initializes the LLM (`gpt-4o-mini` via OpenAI) and wires together the LangGraph nodes and edges.
   - The graph is compiled into a runnable application.

6. **Workflow Execution & Real-Time Streaming**
   - The background thread starts iterating through the LangGraph using `compiled.stream(initial_state)`.
   - After *every* node executes, the `WorkflowManager` captures the state updates (new logs, progress, extracted data) and pushes them over the WebSocket (`/ws`) to the React frontend in real-time.

---

## Phase 3: The Autonomous Pipeline (Node by Node)

### Step 1: Resume Parsing Node (`resume_parser_agent.py`)
- **Action**: Reads the PDF and structures the data.
- **Detailed Flow**:
  1. Validates the PDF file path.
  2. Uses `pdfplumber` (in `tools/resume_parser_tool.py`) to extract raw text deterministically.
  3. Sends the raw text to the LLM with a strict system prompt to output JSON.
  4. The LLM extracts: `skills`, `experience`, `education`, `name`, `email`, `years_of_experience`, etc.
  5. The extracted JSON is merged into the graph's `resume_data` and `user_profile` state.

### Step 2: Job Discovery Node (`job_discovery_agent.py`)
- **Action**: Finds jobs matching the candidate's profile.
- **Detailed Flow**:
  1. Extracts top skills and preferred roles from the parsed resume to use as search keywords.
  2. Calls the Playwright-based `scrape_jobs_real` tool (`tools/job_scraper_tool.py`).
  3. **Playwright Scraper**:
     - Launches an authenticated browser session.
     - **LinkedIn**: Navigates to `/jobs/search/`, types keywords, scrolls to load job cards, extracts titles, URLs, and companies.
     - **Naukri**: Navigates to search results, extracts job cards similarly.
     - Generates a deterministic SHA-256 `job_id` for each listing.
     - **Deduplication**: Queries the SQLite database (`application_logs` table) to skip jobs the agent has already applied to in previous runs.
  4. Returns a curated `job_list` and sets `current_job_index` to 0.

### Step 3: Select Job Node (`select_job_node`)
- **Action**: Picks the next job to evaluate.
- **Detailed Flow**:
  1. Looks at `state["current_job_index"]`.
  2. Plucks `job_list[current_job_index]` and assigns it to `state["selected_job"]`.
  3. Resets application-specific state fields (score, decision, reasoning).

### Step 4: Matcher Node (`matcher_agent.py`)
- **Action**: Scores the fit between the candidate and the selected job.
- **Detailed Flow**:
  1. Passes the parsed resume JSON and the `selected_job` description to the LLM (`matcher_tool.py`).
  2. The LLM evaluates skill overlap, experience relevance, and requirements.
  3. Outputs a JSON object with a `match_score` (0-100) and a `reasoning` string (e.g., "Candidate has 2 years Node.js, job requires 1 year").

### Step 5: Decision Node (`decision_agent.py`)
- **Action**: Hardcoded business logic routing.
- **Detailed Flow**:
  1. Reads the `match_score`.
  2. **Rule 1**: If score ≥ 75 → Decision is `apply`.
  3. **Rule 2**: If 50 ≤ score < 75 → Decision is `ask` (ask user).
  4. **Rule 3**: If score < 50 → Decision is `skip`.
  5. The LangGraph conditional edge `route_after_decision` reads this decision and branches the execution flow accordingly.

*(If Decision = Skip or Ask, it routes straight to the Tracker node. If Apply, it proceeds to Cover Letter Node).*

### Step 6: Cover Letter Node (`cover_letter_agent.py`)
- **Action**: Generates a custom cover letter tailored to the specific job.
- **Detailed Flow**:
  1. Sends the candidate's resume data and the specific job description to the LLM.
  2. The LLM acts as a career consultant to generate a concise, compelling cover letter (3 paragraphs max) that highlights relevant transferable skills.
  3. Updates `cover_letter` in the state.

### Step 7: Deep Apply Agent Node (`deep_apply_agent.py`)
- **Action**: The core autonomous browser agent that fills out the form using a hybrid deterministic and VLM-based approach.
- **Detailed Flow**:
  1. Initializes a `DeepBrowserSession` using Playwright, leveraging an existing user data directory to maintain authenticated sessions.
  2. Navigates to the `job_url` (LinkedIn or Naukri).
  3. **Apply Gate**:
     - Before form filling starts, the agent must prove that the listing has entered an application flow.
     - It repeatedly searches for legitimate Apply controls: `Easy Apply`, `Apply Now`, `Simple Apply`, `Apply on company site`, `Apply on company website`, or `Apply`.
     - It only proceeds after an application surface is detected, such as an application modal, side panel, resume field, email/phone application fields, review screen, or submit-application text.
     - Generic listing-page fields, such as job search boxes, do not count as an opened application.
     - If no valid Apply flow opens, `deep_apply_agent` returns `application_status = "failed"` with an `application_error` instead of silently returning `pending`.
  4. **The Observe-Reason-Act Loop** (Maximum 45 steps):
     - **Observe**: Reads the page DOM. Uses `deep_browser_utils.simplify_html` to strip styles/scripts and inject `data-agent-idx` attributes for precise targeting. Takes a screenshot of the current viewport for the Vision-Language Model (VLM).
     - **Fast Path Check**: Checks if it's a simple Google Form. If so, uses a deterministic script to fill it instantly.
     - **Form Parsing (`form_parser.py`)**: Uses a JavaScript evaluator to extract all interactive elements (inputs, buttons, dropdowns) across the main page and iframes into a clean JSON structure, capturing labels, roles, and placeholders.
     - **Layer 1: Deterministic Automation (`deterministic_filler.py`)**: The deterministic filler parses the structured JSON to automatically identify and fill standard fields (First Name, Last Name, Email, Phone, Resume upload). It executes these actions immediately without invoking the LLM. If all fields are handled deterministically and a submit/next button is found, it clicks it automatically.
     - **Reason (LLM/VLM Call)**: If there are unhandled, complex fields (like custom questions), the agent sends *only* the remaining unfilled fields (filtered JSON) and the page screenshot to the LLM. This drastically reduces context size and enhances reliability via visual grounding.
     - **Act**: The LLM outputs a JSON plan containing actions like `click`, `fill`, `type`, `select_dropdown`, or `upload_resume` for the remaining fields. 
     - **Execution**: The browser executes these actions using exact `data-agent-idx` locators. It handles tricky elements (e.g., `contenteditable` divs, React comboboxes) using custom JavaScript events.
     - **Learning**: If the agent encounters a custom question, it saves the answer to `learned_placeholders.json` for future memory.
     - **Termination**: The loop ends when the DOM contains specific submission-confirmation text, the job is detected as closed, a CAPTCHA blocks the page, or the maximum step budget is reached.
  5. Updates `application_status` (`success` or `failed`). It should not use `pending` for an apply attempt that did not submit.

### Step 8: Tracker Node (`tracker_agent.py`)
- **Action**: Logs the outcome to the database.
- **Detailed Flow**:
  1. Takes the job details, match score, decision, and final application status.
  2. Connects to SQLite (`db.database.insert_application`).
  3. Inserts a new row into the `application_logs` table. This serves as the system's persistent memory to prevent duplicate applications in the future.
  4. Appends an `ApplicationRecord` to the in-memory `application_history` state.

### Step 9: Advance Job Node (`advance_job_node`)
- **Action**: Iterator logic.
- **Detailed Flow**:
  1. For skip/ask paths, checks if `current_job_index + 1 < len(job_list)` and continues normally.
  2. For apply paths, the workflow advances only when `application_status == "success"`.
  3. If an apply attempt fails, the graph stops on that job so the failure reason remains visible instead of moving quietly to the next queued job.
  4. If the apply succeeded and more jobs remain, increments the index by 1 and loops back to **Step 3 (Select Job Node)**.
  5. If no jobs remain, proceeds to the `END` of the LangGraph.

---

## Phase 4: Completion & Teardown

1. **Workflow Termination**
   - The LangGraph execution finishes.
   - The background thread in `server/app.py` catches the completion.
   - It sets `wf_manager.progress = 100`, `wf_manager.completed = True`, and `wf_manager.is_running = False`.

2. **Final Broadcast**
   - A final WebSocket message is sent to the frontend: `🎉 Workflow complete! Evaluated X jobs...`
   - The thread shuts down gracefully.

3. **Frontend Dashboard Update**
   - The React UI receives the completion event.
   - The "Running" badge disappears.
   - The user can navigate to the "Applications" or "Dashboard" tab, which fetches `/api/applications` and `/api/dashboard` to display updated metrics, success rates, score distributions, and application history pulled directly from the SQLite database.
