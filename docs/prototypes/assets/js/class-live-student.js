import { setDemoState, showToast } from "./prototype.js";
import {
  initLiveCommon,
  normalizeLiveInput,
  validateLiveField,
} from "./live-common.js";

const liveView = document.querySelector("#studentLiveView");
const connection = document.querySelector("#studentConnection");
const transcript = document.querySelector("#studentTranscript");
const transcriptStream = document.querySelector("#studentTranscriptStream");
const questionForm = document.querySelector("#questionForm");
const questionInput = document.querySelector("#questionInput");
const draftState = document.querySelector("#draftState");
const draftInput = document.querySelector("#draftInput");
const draftEdit = document.querySelector("#draftEdit");
const questions = document.querySelector("#studentQuestions");
const questionBranches = document.querySelector("[data-question-branches]");
const unclusteredQuestions = document.querySelector(
  "[data-unclustered-questions]",
);
const announcer = document.querySelector("#studentAnnouncement");

const { announce } = initLiveCommon({ announcer });

let partialRevision = 2;
let reactionFailOnce = false;

function getActivePartial() {
  return document.querySelector('[data-transcript-kind="partial"]');
}

function removePartial(reason) {
  const partial = getActivePartial();
  if (!partial) return;
  partial.remove();
  announce(reason);
}

function updateQuestionWatermark() {
  const requested = document.querySelector("[data-requested-sequence]");
  const pending = document.querySelector("[data-pending-count]");
  if (requested)
    requested.textContent = String(Number(requested.textContent) + 1);
  if (pending) pending.textContent = String(Number(pending.textContent) + 1);
  if (
    ![
      "clustering-running",
      "clustering-retry-reserved",
      "cluster-failed",
    ].includes(questions.dataset.demoState)
  ) {
    setDemoState(questions, "clustering-pending");
  }
}

function createQuestionNode(text, { unclustered = false } = {}) {
  const item = document.createElement("li");
  item.className = "live-mindmap__node";
  item.dataset.nodeKind = "student-question";
  if (unclustered) item.dataset.runtimeUnclustered = "true";

  const meta = document.createElement("div");
  meta.className = "live-node-meta";
  const kind = document.createElement("span");
  const status = document.createElement("span");
  kind.textContent = "STUDENT_QUESTION";
  status.textContent = unclustered
    ? "OPEN · 클러스터 미배치"
    : "OPEN · 배치 완료";
  meta.append(kind, status);

  const copy = document.createElement("p");
  copy.textContent = text;

  const reaction = document.createElement("button");
  reaction.className = "reaction-button";
  reaction.type = "button";
  reaction.dataset.reaction = "";
  reaction.setAttribute("aria-pressed", "false");
  reaction.append("궁금해요 ");
  const count = document.createElement("span");
  count.dataset.reactionCount = "";
  count.textContent = "0";
  reaction.append(count);

  item.append(meta, copy, reaction);
  return item;
}

function applyPendingQuestions() {
  const pending = [
    ...(unclusteredQuestions?.querySelectorAll("[data-runtime-unclustered]") ||
      []),
  ];
  pending.reverse().forEach((item) => {
    delete item.dataset.runtimeUnclustered;
    const status = item.querySelector(".live-node-meta span:last-child");
    if (status) status.textContent = "OPEN · 배치 완료";
    questionBranches.prepend(item);
  });
  if (pending.length > 0) {
    const count = document.querySelector("[data-pending-count]");
    if (count) count.textContent = "0";
    announce(
      "클러스터링 성공 결과를 적용해 대기 질문을 대표질문의 branch에 배치했습니다.",
    );
  }
}

function setFormBusy(form, busy) {
  form.setAttribute("aria-busy", String(busy));
  form.querySelectorAll("button").forEach((button) => {
    button.disabled = busy;
  });
}

function submitQuestion({
  field = questionInput,
  fail = false,
  clear = true,
} = {}) {
  if (!validateLiveField(field)) return false;
  const value = normalizeLiveInput(field.value);
  setFormBusy(questionForm, true);

  if (fail) {
    setFormBusy(questionForm, false);
    showToast("질문을 저장하지 못했습니다. 입력은 유지됩니다.", "error");
    return false;
  }

  unclusteredQuestions.prepend(
    createQuestionNode(value, { unclustered: true }),
  );
  updateQuestionWatermark();
  if (clear) {
    field.value = "";
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
  setFormBusy(questionForm, false);
  showToast(
    "익명 질문을 저장하고 자동 클러스터링 pending을 갱신했습니다.",
    "success",
  );
  announce(
    "질문 저장은 완료됐습니다. 실행 중 Job이 있으면 새 질문을 다음 실행에 합칩니다.",
  );
  return true;
}

questionForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuestion();
});

document.addEventListener("click", (event) => {
  const failQuestion = event.target.closest("[data-question-fail]");
  const draftRequest = event.target.closest("[data-draft-request]");
  const draftRegister = event.target.closest("[data-draft-register]");
  const draftReset = event.target.closest("[data-draft-reset]");
  const revision = event.target.closest("[data-student-revision]");
  const finalize = event.target.closest("[data-student-finalize]");
  const reaction = event.target.closest("[data-reaction]");
  const failReaction = event.target.closest("[data-reaction-fail-once]");
  const latest = event.target.closest("[data-student-latest]");
  const terminal = event.target.closest(
    "[data-transition-processing], [data-live-terminal]",
  );

  if (failQuestion) submitQuestion({ fail: true });

  if (draftRequest) {
    if (!validateLiveField(draftInput)) return;
    setDemoState(draftState, "requesting");
    draftState.focus();
    announce("질문 문장 작성 도움을 직접 200 응답으로 요청했습니다.");
    window.setTimeout(() => {
      if (draftState.dataset.demoState === "requesting") {
        setDemoState(draftState, "suggestions");
        announce("300자 이하 질문 후보 두 개를 받았습니다.");
      }
    }, 250);
  }

  if (draftRegister) {
    if (submitQuestion({ field: draftEdit })) {
      setDemoState(draftState, "idle");
      draftInput.value = "";
      draftInput.dispatchEvent(new Event("input", { bubbles: true }));
      questions.tabIndex = -1;
      questions.focus();
    }
  }

  if (draftReset) {
    setDemoState(draftState, "idle");
    draftInput.focus();
  }

  if (revision) {
    const partial = getActivePartial();
    if (!partial) {
      showToast("현재 partial이 없습니다.", "info");
    } else {
      partialRevision += 1;
      partial.dataset.revision = String(partialRevision);
      const text = partial.querySelector("[data-student-partial-text]");
      const label = partial.querySelector("[data-student-revision-label]");
      if (text) {
        text.textContent =
          "다익스트라는 가장 가까운 정점을 반복해서 확정합니다.";
      }
      if (label) label.textContent = `revision ${partialRevision}`;
    }
  }

  if (finalize) {
    const partial = getActivePartial();
    if (!partial) {
      showToast("현재 partial이 없습니다.", "info");
    } else {
      partial.dataset.transcriptKind = "final";
      partial.dataset.sequence = "88";
      partial.removeAttribute("id");
      const text = partial.querySelector("[data-student-partial-text]");
      const meta = partial.querySelector("[data-student-partial-meta]");
      if (text) {
        text.textContent =
          "다익스트라는 가장 가까운 정점을 반복해서 확정합니다.";
      }
      if (meta) meta.textContent = "final · DB commit · sequence 88";
      announce("sequence 88 final Transcript가 저장됐습니다.");
    }
  }

  if (failReaction) {
    reactionFailOnce = true;
    showToast("다음 반응 요청을 실패로 모의합니다.", "warning");
  }

  if (reaction) {
    const previousPressed = reaction.getAttribute("aria-pressed") === "true";
    const counter = reaction.querySelector("[data-reaction-count]");
    const previousCount = Number(counter.textContent);
    reaction.setAttribute("aria-pressed", String(!previousPressed));
    counter.textContent = String(previousCount + (previousPressed ? -1 : 1));

    if (reactionFailOnce) {
      reaction.setAttribute("aria-pressed", String(previousPressed));
      counter.textContent = String(previousCount);
      reactionFailOnce = false;
      showToast("서버 거부를 모의해 이전 반응 상태로 되돌렸습니다.", "error");
    }
  }

  if (latest) {
    transcriptStream?.lastElementChild?.scrollIntoView({ block: "end" });
    showToast("가장 최근 Transcript로 이동했습니다.", "info");
  }

  if (terminal) {
    removePartial("종료 상태 전환으로 저장되지 않은 partial을 제거했습니다.");
    liveView
      .querySelectorAll("textarea, input, button")
      .forEach((control) => (control.disabled = true));
  }
});

document.querySelectorAll('input[name="draftSuggestion"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    draftEdit.value = radio.value;
    draftEdit.dispatchEvent(new Event("input", { bubbles: true }));
    setDemoState(draftState, "editing");
    draftEdit.focus();
    announce("후보를 선택했습니다. 수정 후 별도로 공개 질문을 등록합니다.");
  });
});

document
  .querySelector("[data-student-connection-switcher]")
  ?.addEventListener("click", (event) => {
    const state = event.target.closest("[data-state]")?.dataset.state;
    if (["reconnecting", "resync"].includes(state)) {
      removePartial("재연결 시 저장되지 않은 partial만 제거했습니다.");
    }
  });

document
  .querySelector("[data-student-question-switcher]")
  ?.addEventListener("click", (event) => {
    if (event.target.closest("[data-state]")?.dataset.state === "normal") {
      applyPendingQuestions();
    }
  });

if (draftState?.dataset.demoState === "error" && !draftInput.value) {
  draftInput.value =
    "음수 간선과 우선순위 큐를 함께 고려하면 어떤 최단 경로 알고리즘을 선택해야 하나요?";
  draftInput.dispatchEvent(new Event("input", { bubbles: true }));
}

if (draftState?.dataset.demoState === "editing" && !draftEdit.value) {
  draftEdit.value =
    "음수 간선이 있을 때 최단 경로 알고리즘을 어떻게 선택하나요?";
  draftEdit.dispatchEvent(new Event("input", { bubbles: true }));
}

if (["reconnecting", "resync"].includes(connection?.dataset.demoState)) {
  removePartial("재연결 초기 상태에서 저장되지 않은 partial만 제거했습니다.");
}

if (["processing", "completed"].includes(liveView?.dataset.demoState)) {
  removePartial("종료 상태에서는 live partial을 표시하지 않습니다.");
  liveView
    .querySelectorAll("textarea, input, button")
    .forEach((control) => (control.disabled = true));
}
