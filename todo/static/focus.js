// Focus mode: a stack of task cards, one on top. Swipe the top card:
//   right = done, left = later (to the back of the stack), up = tomorrow.
// The buttons and the arrow keys do the same.
//
// Done and Tomorrow are sent to the server with fetch(), so the page
// doesn't reload between cards.
(function () {
  const stack = document.querySelector("[data-stack]");
  if (!stack) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const counter = document.querySelector("[data-count]");
  const empty = document.querySelector("[data-empty]");
  const actions = document.querySelector(".focus-actions");
  const hint = document.querySelector(".focus-hint");
  const THRESHOLD = 100; // pixels to drag before letting go counts

  function cards() {
    return [...stack.querySelectorAll(".focus-card")];
  }

  // Number the cards so style.css can tuck the 2nd and 3rd behind the first.
  function layout() {
    const all = cards();
    all.forEach((card, i) => {
      card.style.setProperty("--depth", Math.min(i, 3));
      card.setAttribute("aria-hidden", i === 0 ? "false" : "true");
    });
    if (counter) counter.textContent = `${all.length} to go`;
    if (!all.length) {
      stack.remove();
      actions?.remove();
      hint?.remove();
      counter?.remove();
      empty.hidden = false;
    }
  }

  function send(url) {
    const body = new URLSearchParams({ csrf_token: csrfToken });
    // The header tells the server to answer with nothing (see is_fetch() in tasks.py).
    return fetch(url, { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
  }

  // Fly the top card off the screen in a direction, then do the action.
  function act(action) {
    const card = cards()[0];
    if (!card || card.classList.contains("leaving")) return;
    const away = { done: [1, 0], later: [-1, 0], tomorrow: [0, -1] }[action];
    card.classList.add("leaving");
    card.style.transform = `translate(${away[0] * 140}%, ${away[1] * 140}%) rotate(${away[0] * 18}deg)`;
    if (navigator.vibrate) navigator.vibrate(action === "done" ? [20, 40, 20] : 10);

    if (action === "done") send(card.dataset.doneUrl);
    if (action === "tomorrow") send(card.dataset.tomorrowUrl);

    setTimeout(() => {
      card.classList.remove("leaving");
      card.style.transform = "";
      if (action === "later") {
        stack.append(card); // to the back
      } else {
        card.remove();
      }
      layout();
    }, 300);
  }

  // ---------- Dragging the top card ----------

  let start = null;
  stack.addEventListener("pointerdown", (event) => {
    const card = cards()[0];
    if (!card || !card.contains(event.target)) return;
    start = { x: event.clientX, y: event.clientY, card };
    card.setPointerCapture(event.pointerId); // keep getting moves even off the card
    card.classList.add("dragging");
  });

  stack.addEventListener("pointermove", (event) => {
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    start.card.style.transform = `translate(${dx}px, ${dy}px) rotate(${dx / 20}deg)`;
    // Show the label for the direction you're heading.
    const heading = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "done" : "later") : dy < 0 ? "tomorrow" : null;
    const strength = Math.min(Math.max(Math.abs(dx), -dy, 0) / THRESHOLD, 1);
    start.card.dataset.heading = heading || "";
    start.card.style.setProperty("--strength", strength);
  });

  function release(event) {
    if (!start) return;
    const { card } = start;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    start = null;
    card.classList.remove("dragging");
    card.dataset.heading = "";
    card.style.setProperty("--strength", 0);
    if (dx > THRESHOLD) act("done");
    else if (dx < -THRESHOLD) act("later");
    else if (dy < -THRESHOLD) act("tomorrow");
    else card.style.transform = ""; // not far enough: spring back
  }
  stack.addEventListener("pointerup", release);
  stack.addEventListener("pointercancel", release);

  // ---------- Buttons and keys ----------

  // The buttons are real links and forms, for when JavaScript is off.
  // Here they act on whichever card is on top instead.
  document.querySelectorAll("[data-action]").forEach((element) => {
    const action = element.dataset.action;
    const trigger = element.tagName === "FORM" ? "submit" : "click";
    element.addEventListener(trigger, (event) => {
      event.preventDefault();
      act(action);
    });
  });

  document.addEventListener("keydown", (event) => {
    const action = { ArrowRight: "done", ArrowLeft: "later", ArrowUp: "tomorrow" }[event.key];
    if (action) {
      event.preventDefault();
      act(action);
    }
  });

  layout();
})();
