import { setDemoState, showToast } from "./prototype.js";

const connection = document.querySelector("#studentConnection");
const transcript = document.querySelector("#studentTranscript");
const partial = document.querySelector("#studentPartial");
const questionForm = document.querySelector("#questionForm");
const questionInput = document.querySelector("#questionInput");
const questionError = document.querySelector("#questionError");
const draftState = document.querySelector("#draftState");
const draftInput = document.querySelector("#draftInput");
const draftError = document.querySelector("#draftError");
const draftEdit = document.querySelector("#draftEdit");
const summaryState = document.querySelector("#summaryState");
const chatState = document.querySelector("#chatState");
const chatForm = document.querySelector("#chatForm");
const chatInput = document.querySelector("#chatInput");
const chatError = document.querySelector("#chatError");
const announcer = document.querySelector("#studentAnnouncement");
let partialRevision = 2;
let reactionFailOnce = false;

function announce(message) {
  announcer.textContent = message;
}

function submitQuestion({ fail = false, value = questionInput.value } = {}) {
  const trimmed = value.trim();
  if (!trimmed) {
    questionInput.setAttribute("aria-invalid", "true");
    questionError.hidden = false;
    questionInput.focus();
    return;
  }
  questionInput.setAttribute("aria-invalid", "false");
  questionError.hidden = true;
  questionForm.setAttribute("aria-busy", "true");
  questionForm
    .querySelectorAll("button")
    .forEach((button) => (button.disabled = true));
  if (fail) {
    showToast("질문을 전송하지 못했습니다. 입력은 유지됩니다.", "error");
  } else {
    questionInput.value = "";
    showToast(
      "익명 질문을 저장했습니다. 클러스터링은 별도로 진행됩니다.",
      "success",
    );
  }
  questionForm.setAttribute("aria-busy", "false");
  questionForm
    .querySelectorAll("button")
    .forEach((button) => (button.disabled = false));
}

questionForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuestion();
});

document.addEventListener("click", (event) => {
  const failQuestion = event.target.closest("[data-question-fail]");
  const draftRequest = event.target.closest("[data-draft-request]");
  const draftSuccess = event.target.closest("[data-draft-success]");
  const draftFail = event.target.closest("[data-draft-fail]");
  const draftRegister = event.target.closest("[data-draft-register]");
  const revision = event.target.closest("[data-student-revision]");
  const finalize = event.target.closest("[data-student-finalize]");
  const reaction = event.target.closest("[data-reaction]");
  const failReaction = event.target.closest("[data-reaction-fail-once]");
  const summaryRequest = event.target.closest("[data-summary-request]");
  const summaryRunning = event.target.closest("[data-summary-running]");
  const summaryComplete = event.target.closest("[data-summary-complete]");
  const summaryError = event.target.closest("[data-summary-error]");
  const summaryRetry = event.target.closest("[data-summary-retry]");
  const chatEvidence = event.target.closest("[data-chat-evidence]");
  const chatNoEvidence = event.target.closest("[data-chat-no-evidence]");
  const chatErrorResult = event.target.closest("[data-chat-error]");
  const chatRetry = event.target.closest("[data-chat-retry]");

  if (failQuestion) submitQuestion({ fail: true });
  if (draftRequest) {
    if (!draftInput.value.trim()) {
      draftInput.setAttribute("aria-invalid", "true");
      draftError.hidden = false;
      draftInput.focus();
    } else {
      draftInput.setAttribute("aria-invalid", "false");
      draftError.hidden = true;
      setDemoState(draftState, "requesting");
    }
  }
  if (draftSuccess) setDemoState(draftState, "suggestions");
  if (draftFail) setDemoState(draftState, "error");
  if (draftRegister) {
    submitQuestion({ value: draftEdit.value });
    if (draftEdit.value.trim()) setDemoState(draftState, "idle");
  }
  if (revision && partial?.isConnected) {
    partialRevision += 1;
    partial.dataset.revision = String(partialRevision);
    partial.querySelector("[data-student-partial-text]").textContent =
      "다익스트라는 가장 가까운 정점을 반복해서 확정합니다.";
    partial.querySelector("[data-student-revision-label]").textContent =
      `revision ${partialRevision}`;
  }
  if (finalize && partial?.isConnected) {
    partial.dataset.transcriptKind = "final";
    partial.dataset.sequence = "88";
    partial.removeAttribute("id");
    partial.querySelector("[data-student-partial-text]").textContent =
      "다익스트라는 가장 가까운 정점을 반복해서 확정합니다.";
    partial.querySelector("[data-student-partial-meta]").textContent =
      "final · DB commit 완료 · sequence 88";
    announce("sequence 88 final Transcript가 저장되었습니다.");
  }
  if (failReaction) {
    reactionFailOnce = true;
    showToast("다음 반응 요청을 실패로 모의합니다.", "warning");
  }
  if (reaction) {
    const previousPressed = reaction.getAttribute("aria-pressed") === "true";
    const count = Number(
      reaction.querySelector("[data-reaction-count]").textContent,
    );
    reaction.setAttribute("aria-pressed", String(!previousPressed));
    reaction.querySelector("[data-reaction-count]").textContent = String(
      count + (previousPressed ? -1 : 1),
    );
    if (reactionFailOnce) {
      reaction.setAttribute("aria-pressed", String(previousPressed));
      reaction.querySelector("[data-reaction-count]").textContent =
        String(count);
      reactionFailOnce = false;
      showToast("서버 거부를 모의해 이전 반응 상태로 되돌렸습니다.", "error");
    }
  }
  if (summaryRequest) setDemoState(summaryState, "pending");
  if (summaryRunning) setDemoState(summaryState, "running");
  if (summaryComplete) setDemoState(summaryState, "complete");
  if (summaryError) setDemoState(summaryState, "error");
  if (summaryRetry) {
    summaryState.querySelector("[data-summary-attempt]").textContent =
      "attempt 2";
    setDemoState(summaryState, "pending");
  }
  if (chatEvidence) setDemoState(chatState, "evidence");
  if (chatNoEvidence) setDemoState(chatState, "no-evidence");
  if (chatErrorResult) setDemoState(chatState, "error");
  if (chatRetry) {
    chatState.querySelector("[data-chat-attempt]").textContent = "attempt 2";
    setDemoState(chatState, "pending");
  }
});

document.querySelectorAll('input[name="draftSuggestion"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    draftEdit.value = radio.value;
    setDemoState(draftState, "editing");
  });
});

chatForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!chatInput.value.trim()) {
    chatInput.setAttribute("aria-invalid", "true");
    chatError.hidden = false;
    chatInput.focus();
    return;
  }
  chatInput.setAttribute("aria-invalid", "false");
  chatError.hidden = true;
  setDemoState(chatState, "pending");
});

document
  .querySelector("[data-student-connection-switcher]")
  ?.addEventListener("click", (event) => {
    const state = event.target.closest("[data-state]")?.dataset.state;
    if (["reconnecting", "resync"].includes(state) && partial?.isConnected) {
      partial.remove();
      announce("재연결 시 저장되지 않은 partial을 제거했습니다.");
    }
  });

if (["reconnecting", "resync"].includes(connection?.dataset.demoState)) {
  partial?.remove();
}
