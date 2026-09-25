/* Progressive enhancement. The page, recipes and guide work without this file. */
(() => {
  const copyStatus = document.querySelector("#copy-message");
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.hidden = false;
    const label = button.querySelector(".copy-label") || button;
    const original = label.textContent;
    let reset;
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copy);
      const kind = button.dataset.copyKind || "Command";
      try {
        await navigator.clipboard.writeText(target.textContent);
        label.textContent = "Copied";
        if (copyStatus) copyStatus.textContent = `${kind} copied.`;
      } catch {
        const range = document.createRange();
        range.selectNodeContents(target);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        label.textContent = "Selected";
        if (copyStatus)
          copyStatus.textContent = `${kind} selected. Use your copy shortcut.`;
      }
      clearTimeout(reset);
      reset = setTimeout(() => {
        label.textContent = original;
      }, 2200);
    });
  });

  const tabs = [...document.querySelectorAll("[data-tab]")];
  function select(tab, focus = false) {
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(item.getAttribute("aria-controls"));
      panel.hidden = !selected;
      panel.setAttribute("role", "tabpanel");
      panel.tabIndex = 0;
    });
    if (copyStatus) copyStatus.textContent = "";
    if (focus) tab.focus();
  }
  if (tabs.length) {
    document.querySelector(".install-tabs").hidden = false;
    document.querySelector(".install-card").classList.add("enhanced");
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(tab));
      tab.addEventListener("keydown", (event) => {
        const destination = {
          ArrowRight: (index + 1) % tabs.length,
          ArrowLeft: (index + tabs.length - 1) % tabs.length,
          Home: 0,
          End: tabs.length - 1,
        }[event.key];
        if (destination !== undefined) {
          event.preventDefault();
          select(tabs[destination], true);
        }
      });
    });
    select(tabs[0]);
  }

  const review = document.querySelector("#review-button");
  if (review) {
    let count = 0;
    const reset = document.querySelector("#reset-demo");
    function render() {
      const reviewed = count > 0;
      document
        .querySelector("#review-sheet")
        .classList.toggle("reviewed", reviewed);
      document.querySelector("#review-status").textContent = reviewed
        ? "Reviewed"
        : "Not reviewed";
      document.querySelector("#state-value").textContent = reviewed
        ? "reviewed"
        : "not_reviewed";
      document.querySelector("#activation-count").textContent = String(count);
      document.querySelector("#demo-feedback").textContent = reviewed
        ? "The page changed. Ready to inspect."
        : "Waiting for a click.";
      document
        .querySelector(".console-state")
        .classList.toggle("completed", reviewed);
      reset.hidden = !reviewed;
    }
    review.addEventListener("click", () => {
      count += 1;
      render();
    });
    reset.addEventListener("click", () => {
      count = 0;
      render();
      review.focus();
    });
  }
})();
