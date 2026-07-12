import {
  closeDialog,
  openDialog,
  setDemoState,
  showToast,
} from "./prototype.js";

const eventState = document.querySelector("#eventState");
const audioState = document.querySelector("#audioState");
const sttState = document.querySelector("#sttState");
const answerState = document.querySelector("#answerState");
const endFlow = document.querySelector("#endFlow");
const endDialog = document.querySelector("#endDialog");
const announcement = document.querySelector("#liveAnnouncement");
const partial = document.querySelector("#activePartial");
const transcriptStream = document.querySelector("#transcriptStream");
const answerTarget = document.querySelector("#answerTargetCopy");
const answerBoundary = document.querySelector("#answerBoundaryCopy");

let activeAnswer = null;
let partialRevision = 2;

function announce(message) {
  if (announcement) announcement.textContent = message;
}

function isCapturing() {
  return ["waiting", "candidate", "not-ready"].includes(
    answerState?.dataset.demoState,
  );
}

function setAnswerButtonsDisabled(disabled) {
  document.querySelectorAll("[data-answer-select]").forEach((button) => {
    if (disabled) {
      button.disabled = true;
      return;
    }
    if (button.dataset.answerSelect === "cluster") {
      const cards = [
        ...document.querySelectorAll("#clusterQuestions [data-question-id]"),
      ];
      button.disabled = cards.every(
        (card) => card.dataset.questionStatus === "answered",
      );
      return;
    }
    button.disabled =
      button.closest("[data-question-id]")?.dataset.questionStatus ===
      "answered";
  });
}

function setQuestionStatus(ids, status) {
  ids.forEach((id) => {
    const card = document.querySelector(`[data-question-id="${id}"]`);
    if (!card) return;
    card.dataset.questionStatus = status.toLowerCase();
    const label = card.querySelector("[data-question-status-label]");
    if (label) label.textContent = status;
  });
}

function disableCompletedTargets(ids) {
  ids.forEach((id) => {
    document
      .querySelector(`[data-question-id="${id}"] [data-answer-select]`)
      ?.setAttribute("disabled", "");
  });
  const clusterIds = [
    ...document.querySelectorAll("#clusterQuestions [data-question-id]"),
  ].map((card) => card.dataset.questionId);
  if (clusterIds.length > 0 && clusterIds.every((id) => ids.includes(id))) {
    document
      .querySelector('[data-answer-select="cluster"]')
      ?.setAttribute("disabled", "");
  }
}

function startAnswer(button) {
  if (isCapturing()) return;
  const type = button.dataset.answerSelect;
  const cards =
    type === "cluster"
      ? [...document.querySelectorAll("#clusterQuestions [data-question-id]")]
      : [button.closest("[data-question-id]")];
  const ids = cards.filter(Boolean).map((card) => card.dataset.questionId);
  const latestSequence = Math.max(
    0,
    ...[...document.querySelectorAll("[data-sequence]")].map((item) =>
      Number(item.dataset.sequence),
    ),
  );
  activeAnswer = { ids, captureStartedAfterSequence: latestSequence };
  answerTarget.textContent =
    type === "cluster" ? `선택 질문 ${ids.length}개` : "선택 질문 1개";
  answerBoundary.textContent = `sequence ${latestSequence} 이후 final부터 후보`;
  setQuestionStatus(ids, "SELECTED");
  setAnswerButtonsDisabled(true);
  setDemoState(answerState, "waiting");
  answerState.focus();
  announce("답변 캡처를 시작했습니다. 첫 final Transcript를 기다립니다.");
}

function removePartial(reason) {
  if (!partial?.isConnected) return;
  partial.remove();
  announce(reason);
}

document.addEventListener("click", (event) => {
  const micRequest = event.target.closest("[data-mic-request]");
  const micAllow = event.target.closest("[data-mic-allow]");
  const micDeny = event.target.closest("[data-mic-deny]");
  const revision = event.target.closest("[data-partial-revision]");
  const finalize = event.target.closest("[data-partial-finalize]");
  const answerSelect = event.target.closest("[data-answer-select]");
  const answerComplete = event.target.closest("[data-answer-complete]");
  const answerCancel = event.target.closest("[data-answer-cancel]");
  const endOpen = event.target.closest("[data-end-open]");
  const endConfirm = event.target.closest("[data-end-confirm]");
  const endDrain = event.target.closest("[data-end-drain]");
  const endDone = event.target.closest("[data-end-done]");

  if (micRequest) {
    setDemoState(audioState, "connecting");
    announce(
      "마이크 권한 요청 목 상태입니다. 실제 장치에는 접근하지 않습니다.",
    );
  }
  if (micAllow) {
    setDemoState(audioState, "listening");
    setDemoState(sttState, "listening");
    announce("오디오 전송과 STT 수신 목 상태를 시작했습니다.");
  }
  if (micDeny) {
    setDemoState(audioState, "denied");
    announce(
      "마이크 권한이 거부되었습니다. 질문 기능은 계속 사용할 수 있습니다.",
    );
  }
  if (revision && partial?.isConnected) {
    partialRevision += 1;
    partial.dataset.revision = String(partialRevision);
    partial.querySelector("[data-partial-text]").textContent =
      "다익스트라 알고리즘은 음수 가중치가 없을 때 최단 경로를 구합니다.";
    partial.querySelector("[data-partial-revision-label]").textContent =
      `revision ${partialRevision}`;
  }
  if (finalize && partial?.isConnected) {
    partial.dataset.transcriptKind = "final";
    partial.dataset.sequence = "128";
    partial.removeAttribute("id");
    partial.querySelector("[data-transcript-time]").textContent = "10:34";
    partial.querySelector("[data-partial-text]").textContent =
      "다익스트라 알고리즘은 음수 가중치가 없을 때 최단 경로를 구합니다.";
    partial.querySelector("[data-partial-meta]").textContent =
      "final · DB commit 완료 · sequence 128";
    if (activeAnswer) {
      partial.dataset.transcriptKind = "candidate";
      setDemoState(answerState, "candidate");
      announce("새 final Transcript가 답변 후보에 포함되었습니다.");
    } else {
      announce("sequence 128 final Transcript가 저장되었습니다.");
    }
  }
  if (answerSelect) startAnswer(answerSelect);
  if (answerComplete) {
    if (!activeAnswer || answerState.dataset.demoState !== "candidate") {
      setDemoState(answerState, "not-ready");
      announce("확정할 final Transcript가 없어 CAPTURING 상태를 유지합니다.");
    } else {
      setQuestionStatus(activeAnswer.ids, "ANSWERED");
      document
        .querySelectorAll('[data-transcript-kind="candidate"]')
        .forEach((item) => (item.dataset.transcriptKind = "final"));
      setAnswerButtonsDisabled(false);
      disableCompletedTargets(activeAnswer.ids);
      setDemoState(answerState, "completed");
      announce("답변을 완료하고 선택 질문을 ANSWERED로 변경했습니다.");
      activeAnswer = null;
    }
  }
  if (answerCancel) {
    const ids = activeAnswer?.ids || [];
    setQuestionStatus(ids, "OPEN");
    document
      .querySelectorAll('[data-transcript-kind="candidate"]')
      .forEach((item) => (item.dataset.transcriptKind = "final"));
    setAnswerButtonsDisabled(false);
    setDemoState(answerState, "cancelled");
    announce("답변 캡처를 취소하고 선택 질문을 OPEN으로 되돌렸습니다.");
    activeAnswer = null;
  }
  if (endOpen) {
    if (isCapturing()) {
      showToast("진행 중인 답변을 완료하거나 취소한 뒤 종료해주세요.", "error");
      answerState.focus();
    } else {
      setDemoState(endFlow, "confirm");
      openDialog(endDialog, endOpen);
    }
  }
  if (endConfirm) {
    setDemoState(audioState, "finalizing");
    setDemoState(sttState, "finalizing");
    setDemoState(endFlow, "stopping");
    announce("audio.stop 전송 후 남은 final Transcript를 확정 중입니다.");
  }
  if (endDrain) {
    setDemoState(audioState, "stopped");
    setDemoState(sttState, "finalized");
    setDemoState(eventState, "stopped");
    setDemoState(endFlow, "processing");
    announce("audio.stopped와 FINALIZED 확인 후 종료 요청이 수락되었습니다.");
  }
  if (endDone) {
    closeDialog(endDialog);
    showToast("PROCESSING 화면 연결은 PR 6에서 추가됩니다.", "success");
  }
});

document
  .querySelector("[data-event-state-switcher]")
  ?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-state]");
    if (["reconnecting", "resync"].includes(button?.dataset.state)) {
      removePartial("재연결 시 저장되지 않은 partial 표시를 제거했습니다.");
    }
  });

document
  .querySelector("[data-question-sort]")
  ?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-sort]");
    if (!button) return;
    const list = document.querySelector("#sortableQuestions");
    const items = [...list.children];
    items.sort((a, b) =>
      button.dataset.sort === "popular"
        ? Number(b.dataset.reactions) - Number(a.dataset.reactions)
        : Number(b.dataset.recent) - Number(a.dataset.recent),
    );
    items.forEach((item) => list.append(item));
    announce(`${button.textContent.trim()}으로 질문을 정렬했습니다.`);
  });

document
  .querySelector("[data-new-transcript]")
  ?.addEventListener("click", () => {
    transcriptStream?.lastElementChild?.scrollIntoView({ block: "end" });
    showToast("가장 최근 Transcript로 이동했습니다.", "info");
  });

if (["reconnecting", "resync"].includes(eventState?.dataset.demoState)) {
  removePartial("재연결 초기 상태에서 저장되지 않은 partial을 제거했습니다.");
}

if (isCapturing()) setAnswerButtonsDisabled(true);
