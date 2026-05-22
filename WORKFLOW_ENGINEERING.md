# 🏗️ Job Agent: Core Workflow Engineering

Welcome, Junior Developer! This guide explains the "Internal Plumbing" of the Job Agent. We will follow a single execution from the moment a user clicks **"Launch"** until a job application is **Submitted**.

---

## 🗺️ Execution Overview

The system uses **LangGraph** to orchestrate different AI agents. Each agent is a "node" in a graph, and data flows between them in a shared "State" object.

---

## 🏁 Phase 1: The Trigger (FastAPI)

### 1. `server/app.py` ➔ `start_workflow()`
- **What it does**: Receives the HTTP POST request from the frontend.
- **Next Step**: Spawns a background thread called `_run_workflow_thread` so the web server doesn't freeze while the AI is working.

### 2. `server/app.py` ➔ `_run_workflow_thread()`
- **What it does**: Initializes the **LangGraph** engine.
- **Key Call**: `compiled = build_graph()` from `graph/workflow.py`.
- **Action**: Starts iterating through the graph nodes and streams logs to the WebSocket.

---

## 🧠 Phase 2: The LangGraph Pipeline

### 3. `agents/resume_parser_agent.py` ➔ `resume_parser_agent()`
- **Goal**: Turn a PDF into structured JSON (Skills, Experience).
- **Tool Called**: `tools/resume_parser_tool.py` ➔ `parse_resume_with_llm()`.
- **Result**: The "State" now contains your `resume_data`.

### 4. `agents/job_discovery_agent.py` ➔ `job_discovery_agent()`
- **Goal**: Find job listings on the internet.
- **Tool Called**: `tools/job_scraper_tool.py` ➔ `scrape_jobs_real()`.
- **Action**: Opens a browser, searches LinkedIn/Naukri, and returns a list of ~10-20 job URLs.

### 5. `graph/workflow.py` ➔ `select_job()`
- **Goal**: The "Loop Controller".
- **Action**: Picks the next job from the list to process. If the list is empty, it finishes the workflow.

---

## 🎯 Phase 3: Evaluation & Optimization

### 6. `agents/matcher_agent.py` ➔ `matcher_agent()`
- **Goal**: Compare your resume to the job description.
- **Tool Called**: `tools/matcher_tool.py` ➔ `calculate_match_score()`.
- **Result**: A score from 0-100 and a list of "missing keywords".

### 7. `agents/decision_agent.py` ➔ `decision_agent()`
- **Goal**: Should we apply?
- **Action**: If the score is > 70, it sets the state to `APPLY`. Otherwise, it `SKIPS` and goes back to Step 5.

### 8. `agents/ats_optimizer_agent.py` ➔ `ats_optimizer_agent()`
- **Goal**: Tailor the application.
- **Tool Called**: `tools/cover_letter_tool.py` ➔ `generate_cover_letter()`.
- **Action**: Creates a custom cover letter based on the specific job requirements.

---

## 🚀 Phase 4: The Deep Apply (The "Heavy Lifting")

### 9. `agents/deep_apply_agent.py` ➔ `deep_apply_agent()`
- **Goal**: The autonomous browser loop. This is the most complex part.
- **Workflow inside this function**:
    - **Step A**: Call `tools/deep_browser_tools.py` ➔ `get_session_manager()` to open Chrome.
    - **Step B**: `_login_platform()` ensures you are logged in.
    - **Step C (The Loop)**: 
        1. Capture the page DOM (HTML).
        2. `tools/form_parser.py` ➔ `extract_form_json()` finds all inputs.
        3. `tools/deterministic_filler.py` fills common fields (Name, Email).
        4. If stuck, the **LLM** (GPT-4o) looks at the screenshot and decides the next click.
        5. `session.execute_actions()` clicks/types in the real browser.
    - **Step D**: Detect success (e.g., "Application Submitted").

---

## 📝 Phase 5: Persistence

### 10. `agents/tracker_agent.py` ➔ `tracker_agent()`
- **Goal**: Save the result to the database.
- **Call**: `db/database.py` ➔ `ApplicationLog` (SQLAlchemy).
- **Action**: Records the Job Title, Company, Status (Applied/Failed), and Time.

---

## 💡 Summary for Developers
If you want to change how the **AI thinks**, edit the **Agents**.
If you want to change how the **Browser clicks**, edit the **Tools**.
If you want to change the **Order of steps**, edit the **Graph**.

Happy Coding! 💻
