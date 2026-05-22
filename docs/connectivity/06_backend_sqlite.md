# Step 6: Backend ↔ SQLite Connectivity

## Overview
This is the "Memory" of the application. It stores your job history, application status, and match scores so you can track your progress over days and weeks.

## Technical Details
- **Database**: SQLite (file-based)
- **Path**: `/app/db/job_agent.db`
- **Library**: SQLAlchemy (ORM)

## How it works
1. The `tracker_agent` receives updates about a job application (e.g., "Applied successfully").
2. It uses **SQLAlchemy** to connect to the `job_agent.db` file.
3. It inserts a new row (or updates an existing one) in the `application_logs` table.
4. Because the `/app/db` folder is a **Docker Volume**, the database file stays safe on the server even if you delete the container.

## Critical Files
- `db/database.py`: Defines the database schema and initialization logic.
- `agents/tracker_agent.py`: The agent responsible for writing to the database.
- `docker-compose.yml`: Defines the volume mapping `./db:/app/db`.
