import { setDemoState, showToast } from "./prototype.js";
const chat = document.querySelector("#reviewChatState"),
  form = document.querySelector("#reviewChatForm"),
  input = document.querySelector("#reviewChatInput"),
  error = document.querySelector("#reviewChatError");

form?.addEventListener("submit", (e) => {
  e.preventDefault();
  if (!input.value.trim()) {
    input.setAttribute("aria-invalid", "true");
    error.hidden = false;
    input.focus();
    return;
  }
  input.setAttribute("aria-invalid", "false");
  error.hidden = true;
  setDemoState(chat, "pending");
});

input?.addEventListener("input", () => {
  input.setAttribute("aria-invalid", "false");
  error.hidden = true;
});

document.addEventListener("click", (e) => {
  if (e.target.closest("[data-review-complete]")) {
    setDemoState(chat, "complete");
  }
  if (e.target.closest("[data-review-no-evidence]")) {
    setDemoState(chat, "no-evidence");
  }
  if (e.target.closest("[data-review-fail]")) {
    setDemoState(chat, "failed");
  }
  if (e.target.closest("[data-review-retry]")) {
    chat.querySelectorAll("[data-review-attempt]").forEach((attempt) => {
      attempt.textContent = "attempt 2";
    });
    setDemoState(chat, "pending");
    showToast("같은 CHAT_RESPONSE Job을 attempt 2로 재시도합니다.", "success");
  }
});
