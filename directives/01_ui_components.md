# UI Components Directive (SOP 01)

## Goal
Guide any updates or additions to the PyQt6 User Interface (`ui/`).

## Principles
1. **Separation of Concerns**: Never place API calls directly within Qt slots unless they are asynchronous. 
2. **QThread and Signals**: Use `pyqtSignal` to transmit data from background worker threads back to the main UI thread. Avoid updating UI elements directly from a background thread as this causes race conditions and crashes in Qt.

## Adding a New Feature
1. Design the UI widget class (e.g. `MyNewWidget(QWidget)`).
2. Wire up the buttons to local slots.
3. If clicking a button triggers a network request or heavy task, create a class subclassing `QThread` (or a generic worker class) in `core/` or `execution/`.
4. Connect the worker's signal to the widget's update slot before starting it.
5. In `ui/bar.py` (the root component), instantiate the widget and add it to the layout.

## Styling
- Keep stylesheets centralized or use the existing dark mode schema in the widget.
- Prefer explicit `#id` selectors for QSS if possible.
