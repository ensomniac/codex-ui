const wheel =
  "https://github.com/ensomniac/codex-ui/releases/download/v2.0.0/ensomniac_codex_ui-2.0.0-py3-none-any.whl";
const archive =
  "https://github.com/ensomniac/codex-ui/releases/download/v2.0.0/ensomniac-codex-ui-2.0.0.tgz";
const installers = {
  installer: [
    "curl -fsSL https://raw.githubusercontent.com/ensomniac/codex-ui/main/install.sh | sh",
    "The installer supplies uv and an isolated Python runtime. macOS may request its normal desktop permissions once.",
  ],
  uv: [
    `uv tool install '${wheel}'`,
    "Requires uv. The release installs in its own environment. No registry login or checkout.",
  ],
  brew: [
    "brew tap ensomniac/codex-ui https://github.com/ensomniac/codex-ui\nbrew install ensomniac/codex-ui/codex-ui",
    "The repository is its own Homebrew tap. Dependencies are pinned, and brew upgrade keeps the release current.",
  ],
  npm: [
    `npm install -g '${archive}'`,
    "Requires Node 18+ and uv or Python 3.11+. The small bridge prepares an isolated Python runtime on first use.",
  ],
};
const tabs = [...document.querySelectorAll("[data-install]")];
function selectTab(tab, focus = false) {
  for (const other of tabs) {
    other.setAttribute("aria-selected", String(other === tab));
    other.tabIndex = other === tab ? 0 : -1;
  }
  const [command, note] = installers[tab.dataset.install];
  document.querySelector("#install-code").textContent = command;
  document.querySelector("#install-note").textContent = note;
  document
    .querySelector("#install-code-panel")
    .setAttribute("aria-labelledby", tab.id);
  document.querySelector("#copy-status").textContent = "";
  if (focus) tab.focus();
}
for (const tab of tabs) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    const index = tabs.indexOf(tab);
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % tabs.length
        : event.key === "ArrowLeft"
          ? (index + tabs.length - 1) % tabs.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? tabs.length - 1
              : -1;
    if (next !== -1) {
      event.preventDefault();
      selectTab(tabs[next], true);
    }
  });
}
document.querySelector("#copy-install").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(
      document.querySelector("#install-code").textContent,
    );
    document.querySelector("#copy-status").textContent = "Copied.";
  } catch {
    document.querySelector("#copy-status").textContent =
      "Select the command above to copy.";
  }
});
let activations = 0;
document.querySelector("#demo-button").addEventListener("click", () => {
  activations += 1;
  document.querySelector(".control-scene").classList.add("activated");
  document.querySelector("#scene-state").textContent = "● COMPLETED";
  document.querySelector("#demo-status").textContent =
    `Demo activated ${activations} time${activations === 1 ? "" : "s"}. State verified.`;
  document.querySelector("#terminal-result").textContent =
    `{ "ok": true, "activations": ${activations}, "pointer_restored": true }`;
});
