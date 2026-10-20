// Small touches on top of the server-made pages. Every feature also works
// without this file: it only adds animation, gestures and drag-and-drop.
(function () {
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // A short buzz on phones that support it. Desktop browsers ignore it.
  function buzz(ms) {
    if (navigator.vibrate) navigator.vibrate(ms);
  }

  // ---------- Greeting by the time of day ----------

  // The server doesn't know your time zone, so your device's clock picks
  // the words. The server writes "Hello", which stays if this doesn't run.
  const hello = document.querySelector("[data-hello]");
  if (hello) {
    const hour = new Date().getHours();
    hello.textContent = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  }

  // ---------- Long press opens a task's menu ----------

  // Hold a card for half a second (or right-click it) to open the same
  // menu as its ⋯ button.
  //
  // The menu opens when the finger lifts, not while it's still down. A
  // popover closes itself when you press and release outside it ("light
  // dismiss"), and the press started on the card, outside the menu. So a
  // menu opened mid-press would close again the moment you let go.
  const HOLD_MS = 500;
  document.querySelectorAll(".task, .board-card").forEach((card) => {
    const menu = card.querySelector("[popover]");
    if (!menu || !menu.showPopover) return;
    let timer = null;
    let start = null;       // where the press began, while a press is going on
    let held = false;       // pressed long enough: open the menu on release
    let swallowClick = false;

    card.addEventListener("pointerdown", (event) => {
      // With a mouse, buttons and links keep their normal click.
      if (event.target.closest("button, a, input, select") && event.pointerType === "mouse") return;
      start = { x: event.clientX, y: event.clientY };
      timer = setTimeout(() => {
        timer = null;
        held = true;
        buzz(15); // you can feel when it's long enough
      }, HOLD_MS);
    });
    // Moving the finger means scrolling, not holding.
    card.addEventListener("pointermove", (event) => {
      if (timer && start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 10) {
        clearTimeout(timer);
        timer = null;
      }
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((name) =>
      card.addEventListener(name, () => {
        clearTimeout(timer);
        timer = null;
        start = null;
        if (!held) return;
        held = false;
        // Lifting the finger also "clicks" what's under it, like the title
        // link. Swallow that click, which comes right after pointerup, then
        // open the menu once it has passed.
        swallowClick = true;
        setTimeout(() => {
          swallowClick = false;
          menu.showPopover();
        }, 0);
      })
    );
    card.addEventListener("click", (event) => {
      if (swallowClick) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);
    // Right-click on a computer. Phones send this on a long press too: if
    // a finger is still down, wait for it to lift, like above.
    card.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      if (start) {
        held = true;
      } else {
        menu.showPopover();
      }
    });
  });

  // Put the cursor in the quick-add box when its sheet opens.
  const sheet = document.getElementById("quick-sheet");
  sheet?.addEventListener("toggle", (event) => {
    if (event.newState === "open") sheet.querySelector("input[name=text]").focus();
  });

  // ---------- A happy little moment when a task is done ----------

  function confetti(x, y) {
    const colors = ["#f43f5e", "#f59e0b", "#10b981", "#3b82f6", "#a855f7"];
    for (let i = 0; i < 16; i++) {
      const bit = document.createElement("span");
      bit.className = "confetti";
      // Each piece flies off at its own angle and distance. style.css
      // reads --dx and --dy in its animation.
      const angle = (Math.PI * 2 * i) / 16 + Math.random() * 0.4;
      const distance = 40 + Math.random() * 50;
      bit.style.left = `${x}px`;
      bit.style.top = `${y}px`;
      bit.style.background = colors[i % colors.length];
      bit.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
      bit.style.setProperty("--dy", `${Math.sin(angle) * distance}px`);
      document.body.append(bit);
      setTimeout(() => bit.remove(), 900);
    }
  }

  document.querySelectorAll(".task-check").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const card = form.closest(".task");
      // Only celebrate ticking a task off, not un-ticking it.
      if (calm || !card || card.classList.contains("done")) return;
      event.preventDefault();
      const box = form.querySelector(".check").getBoundingClientRect();
      card.classList.add("completing"); // the squish, then slide away, in style.css
      confetti(box.left + box.width / 2, box.top + box.height / 2);
      buzz([20, 40, 20]);
      // Send the form after the animation. form.submit() doesn't fire
      // "submit" again, so this doesn't loop.
      setTimeout(() => form.submit(), 600);
    });
  });

  // ---------- Dragging cards between board columns ----------

  let dragged = null;
  document.querySelectorAll(".board-card").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      dragged = card;
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      dragged = null;
    });
  });

  document.querySelectorAll(".board-col").forEach((column) => {
    // A drop is only allowed where dragover calls preventDefault().
    column.addEventListener("dragover", (event) => {
      if (!dragged) return;
      event.preventDefault();
      column.classList.add("drop-here");
    });
    column.addEventListener("dragleave", () => column.classList.remove("drop-here"));
    column.addEventListener("drop", (event) => {
      event.preventDefault();
      column.classList.remove("drop-here");
      if (!dragged || dragged.closest(".board-col") === column) return;
      // Send the same form the card's buttons send, then the page reloads.
      const form = document.createElement("form");
      form.method = "post";
      form.action = dragged.dataset.statusUrl;
      for (const [name, value] of [["csrf_token", csrfToken], ["status", column.dataset.status]]) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        form.append(input);
      }
      column.querySelector(".board-cards").append(dragged);
      document.body.append(form);
      form.submit();
    });
  });
})();
