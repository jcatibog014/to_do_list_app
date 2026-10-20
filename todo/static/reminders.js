// Reminders: every half minute, ask the server for this user's reminders
// (GET /reminders) and announce any whose time has come.
//
// This only runs while the app is open in a tab (it can be in the
// background). Once every tab is closed, nothing runs, so nothing reminds.
(function () {
  const box = document.getElementById("reminders");
  if (!box) return; // logged out

  const CHECK_EVERY_MS = 30 * 1000;
  // A reminder missed by more than this (the app was closed) is skipped,
  // so opening the app after a week doesn't pop up a week of reminders.
  const TOO_OLD_MS = 12 * 60 * 60 * 1000;

  // The browser asks the user before a site may show notifications, and
  // only after a click. So show a button while the answer is still unknown.
  const button = document.getElementById("enable-reminders");
  const canAsk = "Notification" in window && Notification.permission === "default";
  if (button && canAsk) {
    button.hidden = false;
    button.addEventListener("click", async () => {
      await Notification.requestPermission();
      button.hidden = true;
    });
  }

  // Remember which reminders were already shown, so each shows once, even
  // across page loads. localStorage can be blocked, so failures are ignored.
  function alreadyShown(key) {
    try { return localStorage.getItem(key) !== null; } catch { return false; }
  }
  function markShown(key) {
    try { localStorage.setItem(key, "1"); } catch { /* ignore */ }
  }

  function announce(reminder) {
    const text = `🔔 ${reminder.title} · ${reminder.when}`;

    // On the page: always, in case notifications are off.
    const message = document.createElement("p");
    message.className = "flash flash-reminder";
    message.textContent = text; // textContent, not innerHTML, so a title can't add HTML
    box.append(message);

    // As a system notification, when allowed. Some phones only allow them
    // from installed apps and throw an error here, which is fine.
    if ("Notification" in window && Notification.permission === "granted") {
      try {
        new Notification("Later Gator reminder", {
          body: `${reminder.title} · ${reminder.when}`,
          icon: "/static/logo.png",
          tag: `task-${reminder.id}`,
        });
      } catch { /* the message on the page is enough */ }
    }
  }

  async function check() {
    let data;
    try {
      const response = await fetch(box.dataset.url, { headers: { Accept: "application/json" } });
      data = await response.json();
    } catch {
      return; // offline, or logged out in another tab: try again next time
    }
    const now = Date.now();
    for (const reminder of data.reminders) {
      // "2026-10-23T16:50" has no time zone, so it's read as local time.
      const at = new Date(reminder.at).getTime();
      const key = `reminded:${reminder.id}:${reminder.at}`;
      if (at <= now && now - at < TOO_OLD_MS && !alreadyShown(key)) {
        markShown(key);
        announce(reminder);
      }
    }
  }

  check();
  setInterval(check, CHECK_EVERY_MS);
})();
