"""Checking what the user typed into the task form.

validate_task() is a plain function: form data goes in, and clean data plus
error messages come out. It doesn't use Flask or the database, which makes
it easy to test (see tests/test_validation.py).
"""
import re
from datetime import date

TITLE_MAX = 100
DESCRIPTION_MAX = 500
DATE_FORMAT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def validate_task(form, today, existing_due_date=None):
    """Return (data, errors).

    form              -- the submitted fields (request.form or a plain dict)
    today             -- today's date, passed in so tests can choose the day
    existing_due_date -- when editing, the task's saved due date ('YYYY-MM-DD' or None)

    `data` holds the cleaned values, ready to save.
    `errors` maps a field name to a message. The form is valid when it's empty.
    """
    errors = {}

    # Trim spaces first, so a title of "   " counts as empty.
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    due_text = form.get("due_date", "").strip()

    if not title:
        errors["title"] = "Title is required."
    elif len(title) > TITLE_MAX:
        errors["title"] = f"Title must be {TITLE_MAX} characters or fewer (it has {len(title)})."

    if len(description) > DESCRIPTION_MAX:
        errors["description"] = f"Description must be {DESCRIPTION_MAX} characters or fewer (it has {len(description)})."

    due_date = None
    if due_text:  # The due date is optional: an empty field means "no due date".
        if not DATE_FORMAT.fullmatch(due_text):
            errors["due_date"] = "Enter the date as YYYY-MM-DD."
        else:
            try:
                # fromisoformat rejects dates that don't exist, like 2026-02-30.
                due_date = date.fromisoformat(due_text)
            except ValueError:
                errors["due_date"] = "That date doesn't exist."
            else:
                # A past date is only allowed if the task already had it, so
                # you can still edit the title of a task that is now overdue.
                if due_date < today and due_text != existing_due_date:
                    errors["due_date"] = "Due date can't be in the past."

    data = {
        "title": title,
        "description": description,
        "due_date": due_date.isoformat() if due_date else None,
    }
    return data, errors
