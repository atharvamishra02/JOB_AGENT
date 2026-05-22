# Step 4: Backend ↔ Browser Connectivity

## Overview
This is the internal "hands" of the agent. It connects the Python code to the actual Google Chrome browser running on the server.

## Technical Details
- **Protocol**: CDP (Chrome DevTools Protocol)
- **Library**: Playwright
- **Browser**: Google Chrome Stable

## How it works
1. The `deep_apply_agent` calls `sync_playwright()`.
2. Playwright launches a "Persistent Context" using your stored profile in `/app/browser_data`.
3. The Python code sends high-level commands (e.g., `page.click("#apply")`) to Playwright.
4. Playwright translates these into CDP messages that the Chrome browser process understands.
5. Chrome performs the action (clicks, types, navigates) on the virtual display `:99`.

## Critical Files
- `tools/deep_browser_tools.py`: Where the browser is launched and managed.
- `agents/deep_apply_agent.py`: The "Brain" that decides what commands to send to the browser.
