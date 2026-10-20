"""Checking what the user typed into the task and sign-up forms.

validate_task() is a plain function: form data goes in, and clean data plus
error messages come out. It doesn't use Flask or the database, which makes
it easy to test (see tests/test_validation.py).
"""
import re
from datetime import date

from .recurrence import first_due, parse_repeat

TITLE_MAX = 100
DESCRIPTION_MAX = 500
DATE_FORMAT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TIME_FORMAT = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")  # 24-hour clock, like 17:30
TAG_LENGTH_MAX = 30
TAG_FORMAT = re.compile(rf"[\w-]{{1,{TAG_LENGTH_MAX}}}")
TAGS_MAX = 10
LIST_NAME_MAX = 40
# The colors a list can have. style.css has a .color-<name> class for each.
LIST_COLORS = ["blue", "violet", "pink", "red", "orange", "amber", "green", "teal"]

# The reminder menu: minutes before the due time -> label.
REMINDERS = {
    0: "At the due time",
    10: "10 minutes before",
    30: "30 minutes before",
    60: "1 hour before",
    1440: "1 day before",
}

# The emoji offered on the task form. Quick add accepts any emoji.
EMOJI_CHOICES = ["🛒", "💪", "📚", "💼", "🏠", "💡", "🎉", "❤️",
                 "🧹", "💊", "🍳", "✈️", "💰", "📞", "🎮", "🌱"]
# An emoji is a few characters that aren't letters, digits, spaces or HTML symbols.
EMOJI_FORMAT = re.compile(r"[^\w\s<>&\"']{1,8}")

SUBTASK_MAX = 100
SUBTASKS_MAX = 20

# Color themes, and the best streak (days in a row with a task done) that
# unlocks each one. A small reward for keeping at it.
THEMES = {
    "default": {"label": "Grape", "unlock": 0},
    "ocean": {"label": "Ocean", "unlock": 0},
    "matcha": {"label": "Matcha", "unlock": 3},
    "sunset": {"label": "Sunset", "unlock": 7},
}
APPEARANCES = {"system": "Match my device", "light": "Light", "dark": "Dark"}

# The profile picture choices. Nobody uploads a photo: an emoji is enough.
AVATAR_CHOICES = ["😀", "😎", "🦊", "🐱", "🐼", "🐸", "🌸", "🌈",
                  "⚡", "🍀", "🎧", "🚀", "🧋", "🎨", "⚽", "🦄"]
DISPLAY_NAME_MAX = 40

USERNAME_MIN = 3
USERNAME_MAX = 30
USERNAME_FORMAT = re.compile(rf"[A-Za-z0-9_]{{{USERNAME_MIN},{USERNAME_MAX}}}")
PASSWORD_MIN = 8


def capitalize_first(text):
    """Start the text with a capital letter: "buy eggs" -> "Buy eggs".

    Only the first letter changes. A first word that mixes cases on purpose,
    like "iPhone" or "eBay", is left alone, and so is everything after it.
    The templates also use this as the |capfirst filter, so tasks saved
    before this rule existed look the same.
    """
    if not text or not text[0].islower():
        return text
    rest_of_word = text.split()[0][1:]
    if rest_of_word != rest_of_word.lower():  # "iPhone": "Phone" has a capital
        return text
    return text[0].upper() + text[1:]


def validate_task(form, today, existing_due_date=None):
    """Return (data, errors).

    form              -- the submitted fields (request.form or a plain dict)
    today             -- today's date, passed in so tests can choose the day
    existing_due_date -- when editing, the task's saved due date ('YYYY-MM-DD' or None)

    The fields are title, description, due_date, due_time, repeat (words
    like "every week"), remind_before (minutes, from REMINDERS), tags,
    list_id, priority (a checkbox), emoji and subtasks (one per line, only
    on the "new task" form). Only the title is required.

    `data` holds the cleaned values, ready to save.
    `errors` maps a field name to a message. The form is valid when it's empty.
    """
    errors = {}

    # Trim spaces first, so a title of "   " counts as empty.
    title = capitalize_first(form.get("title", "").strip())
    description = form.get("description", "").strip()
    due_text = form.get("due_date", "").strip()
    time_text = form.get("due_time", "").strip()
    repeat_text = form.get("repeat", "").strip()
    remind_text = form.get("remind_before", "").strip()
    tags_text = form.get("tags", "").strip()
    list_text = form.get("list_id", "").strip()
    emoji = form.get("emoji", "").strip() or None
    subtasks_text = form.get("subtasks", "")

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

    repeat = None
    if repeat_text:
        repeat = parse_repeat(repeat_text)
        if repeat is None:
            errors["repeat"] = "Try something like “every day”, “every 2 weeks” or “every 2nd Monday”."
        elif due_date is None and "due_date" not in errors:
            # A repeat needs a date to count from. Without one, start at the
            # first day that fits: "every Friday" starts this Friday.
            due_date = first_due(repeat, today)

    due_time = None
    if time_text:
        if not TIME_FORMAT.fullmatch(time_text):
            errors["due_time"] = "Enter the time as HH:MM, like 17:30."
        elif due_date is None and "due_date" not in errors:
            errors["due_time"] = "Add a due date for this time."
        else:
            due_time = time_text

    remind_before = None
    if remind_text:
        if not remind_text.isdigit() or int(remind_text) not in REMINDERS:
            errors["remind_before"] = "Choose a reminder from the list."
        elif due_time is None and "due_time" not in errors:
            errors["remind_before"] = "Set a due time to get a reminder."
        else:
            remind_before = int(remind_text)

    # Tags can be typed as "home, errands" or "#home #errands".
    tags = []
    for word in re.split(r"[\s,]+", tags_text):
        tag = word.lstrip("#").lower()
        if tag and tag not in tags:
            tags.append(tag)
    if any(not TAG_FORMAT.fullmatch(tag) for tag in tags):
        errors["tags"] = f"Tags can use letters, numbers, - and _, up to {TAG_LENGTH_MAX} characters each."
    elif len(tags) > TAGS_MAX:
        errors["tags"] = f"Use {TAGS_MAX} tags or fewer."

    # The list's id comes from a menu. Whether that list belongs to the
    # user needs the database, so tasks.py checks that part.
    list_id = None
    if list_text:
        if list_text.isdigit():
            list_id = int(list_text)
        else:
            errors["list_id"] = "Choose a list from the menu."

    if emoji is not None and not EMOJI_FORMAT.fullmatch(emoji):
        errors["emoji"] = "Pick an emoji from the list."

    # One subtask per line. Blank lines are skipped.
    subtasks = [capitalize_first(line.strip()) for line in subtasks_text.splitlines() if line.strip()]
    if any(len(line) > SUBTASK_MAX for line in subtasks):
        errors["subtasks"] = f"Each subtask must be {SUBTASK_MAX} characters or fewer."
    elif len(subtasks) > SUBTASKS_MAX:
        errors["subtasks"] = f"Use {SUBTASKS_MAX} subtasks or fewer."

    data = {
        "title": title,
        "description": description,
        "due_date": due_date.isoformat() if due_date else None,
        "due_time": due_time,
        "repeat": repeat,
        "remind_before": remind_before,
        "tags": tags,
        "list_id": list_id,
        # A ticked checkbox sends its value. An unticked one sends nothing.
        "priority": 1 if form.get("priority") else 0,
        "emoji": emoji,
        "subtasks": subtasks,
    }
    return data, errors


def validate_subtask(form):
    """Return (title, error) for the "add a subtask" box."""
    title = capitalize_first(form.get("title", "").strip())
    if not title:
        return title, "Type the subtask first."
    if len(title) > SUBTASK_MAX:
        return title, f"Subtasks must be {SUBTASK_MAX} characters or fewer."
    return title, None


def validate_settings(form, best_streak):
    """Return (data, errors) for the theme and appearance settings.

    best_streak decides which themes are unlocked.
    """
    errors = {}
    theme = form.get("theme", "")
    appearance = form.get("appearance", "")
    if theme not in THEMES:
        errors["theme"] = "Pick one of the themes."
    elif THEMES[theme]["unlock"] > best_streak:
        days = THEMES[theme]["unlock"]
        errors["theme"] = f"{THEMES[theme]['label']} unlocks after a {days}-day streak."
    if appearance not in APPEARANCES:
        errors["appearance"] = "Pick light, dark or match my device."
    return {"theme": theme, "appearance": appearance}, errors


def validate_registration(form):
    """Return (data, errors) for the sign-up form, like validate_task().

    Whether the username is already taken needs the database, so auth.py
    checks that part.
    """
    errors = {}

    username = form.get("username", "").strip()
    # Passwords are not trimmed: a space can be part of a password.
    password = form.get("password", "")
    confirm = form.get("confirm", "")

    # The walrus operator := saves the result and checks it in one step.
    if error := username_error(username):
        errors["username"] = error
    if error := password_error(password):
        errors["password"] = error
    elif password != confirm:
        errors["confirm"] = "The passwords don't match."

    return {"username": username, "password": password}, errors


def username_error(username):
    """The problem with a username, or None. Shared by sign-up and the profile."""
    if not username:
        return "Username is required."
    if not USERNAME_FORMAT.fullmatch(username):
        return f"Use {USERNAME_MIN} to {USERNAME_MAX} letters, numbers or underscores (_)."
    return None


def password_error(password):
    if len(password) < PASSWORD_MIN:
        return f"Password must be at least {PASSWORD_MIN} characters."
    return None


def validate_profile(form):
    """Return (data, errors) for the "Your info" form on the profile page.

    Whether the new username is taken needs the database, so profile.py
    checks that part.
    """
    errors = {}
    username = form.get("username", "").strip()
    display_name = " ".join(form.get("display_name", "").split()) or None  # squash extra spaces
    avatar = form.get("avatar", "").strip() or None

    if error := username_error(username):
        errors["username"] = error
    if display_name and len(display_name) > DISPLAY_NAME_MAX:
        errors["display_name"] = f"Your name must be {DISPLAY_NAME_MAX} characters or fewer."
    if avatar and not EMOJI_FORMAT.fullmatch(avatar):
        errors["avatar"] = "Pick one of the pictures."
    return {"username": username, "display_name": display_name, "avatar": avatar}, errors


def validate_password_change(form):
    """Return (new_password, errors) for the "Change password" form.

    Whether the current password is right needs the saved hash, so
    profile.py checks that part.
    """
    errors = {}
    new = form.get("new_password", "")
    if not form.get("current_password"):
        errors["current_password"] = "Type your current password."
    if error := password_error(new):
        errors["new_password"] = error
    elif new != form.get("confirm_password", ""):
        errors["confirm_password"] = "The new passwords don't match."
    return new, errors


def validate_list_name(form):
    """Return (name, error) for the "New list" form. error is None when it's fine.

    Whether the user already has a list with that name needs the database,
    so tasks.py checks that part.
    """
    name = capitalize_first(" ".join(form.get("name", "").split()))  # trim, squash repeated spaces
    if not name:
        return name, "Give the list a name."
    if len(name) > LIST_NAME_MAX:
        return name, f"List names must be {LIST_NAME_MAX} characters or fewer."
    return name, None


def validate_list_color(form, default=None):
    """Return (color, error) for a list's color, picked from LIST_COLORS.

    If no color was sent, `default` is used when there is one.
    """
    color = form.get("color", "") or default
    if color not in LIST_COLORS:
        return None, "Pick one of the colors."
    return color, None


def next_list_color(list_count):
    """The color a new list gets unless another is picked: each in turn."""
    return LIST_COLORS[list_count % len(LIST_COLORS)]
