# Seq Widget - Project Architecture (SOP 00)

## Overview
Seq Widget is a Python desktop widget built using PyQt6. 
Its core purpose is to act as a desktop assistant that polls for emails, checks schedules, and integrates with multiple LLM providers (Groq, OpenAI, Gemini, OpenRouter, Ollama) to summarize and highlight important information.

## System Components

1. **UI Layer (`ui/`)**
   - Built with PyQt6.
   - The main entry point is `ui/bar.py`.
   - Modifying this requires understanding PyQt signals/slots.
   - Run in the main thread to ensure the GUI is responsive.

2. **Core Logic (`core/`)**
   - Contains integrations and engine-level logic.
   - **`api_client.py`**: A facade for multi-provider LLM calling. Uses `StreamWorker` (a `QThread`) to allow streaming inference without blocking the UI thread.
   - **Polling Engines (`polling_engine.py`)**: Runs background workers checking for new items (Outlook via Microsoft Graph and Gmail). Sends signals when important items are identified by the AI.
   - **Scheduling (`scheduler.py`)**: A `ScheduleCheckerWorker` continuously checks if any scheduled items are overdue.

3. **Execution Layer (`execution/`)**
   - The deterministic python tools.
   - If any API tests, cleanups, or pure logic (independent of Qt) need to be run, they live here.

4. **Directives (`directives/`)**
   - Where the Standard Operating Procedures for maintaining the system live.

## Important Considerations
- Always decouple heavy operations from the main PyQt thread to prevent "Not Responding" states.
- The `.env` file holds sensitive keys. Ensure all providers gracefully fail if the required key is missing, as currently handled in `api_client.py`.
