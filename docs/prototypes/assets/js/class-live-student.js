import { setDemoState, showToast } from "./prototype.js";
import {
  initLiveCommon,
  normalizeLiveInput,
  refreshQuestionPriority,
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
const clusterMembers = document.querySelector("[data-question-members]");
const unclusteredQuestions = document.querySelector(
  "[data-unclustered-questions]",
);
const questionPriorityList = document.querySelector(
  "[data-question-priority-list]",
);
const announcer = document.querySelector("#studentAnnouncement");

const { announce } = initLiveCommon({ announcer });

let partialRevision = 2;
let reactionFailOnce = false;
let localQuestionSequence = 200;
let localCreatedOrder = 100;
let observedQuestionState = questions?.dataset.demoState;
let retryInFlight = observedQuestionState === "clustering-retry-reserved";

function getActivePartial() {
  return document.querySelector('[data-transcript-kind="partial"]');
}

function removePartial(reason) {
  const partial = getActivePartial();
  if (!partial) return;
  partial.remove();
  announce(reason);
}

function jobIdFrom(text, fallback = "job-cluster-006") {
  return text?.match(/job-cluster-\d+/)?.[0] || fallback;
}

function nextJobId(jobId) {
  const sequence = Number(jobId.match(/\d+$/)?.[0] || "6") + 1;
  return `job-cluster-${String(sequence).padStart(3, "0")}`;
}

function activeJobId() {
  return jobIdFrom(
    document.querySelector("[data-active-clustering-job]")?.textContent,
    "job-cluster-007",
  );
}

function setActiveJobId(jobId) {
  document.querySelectorAll("[data-active-clustering-job]").forEach((label) => {
    label.textContent = `active job: ${jobId}`;
  });
}

function setActiveClusteringAttempt(attempt) {
  document
    .querySelectorAll("[data-active-clustering-attempt]")
    .forEach((label) => (label.textContent = `attempt ${attempt}`));
}

function setQuestionState(state) {
  setDemoState(questions, state);
  document
    .querySelectorAll("[data-student-question-switcher] [data-state]")
    .forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.state === state),
      ),
    );
  observedQuestionState = state;
}

function updateQuestionWatermark(previousState) {
  const requested = document.querySelector("[data-requested-sequence]");
  const pending = document.querySelector("[data-pending-count]");
  if (requested)
    requested.textContent = String(Number(requested.textContent) + 1);
  if (pending) pending.textContent = String(Number(pending.textContent) + 1);

  if (previousState === "cluster-failed") {
    retryInFlight = false;
    setActiveJobId(nextJobId(activeJobId()));
    setActiveClusteringAttempt(1);
    setQuestionState("clustering-pending");
  } else if (previousState === "normal") {
    retryInFlight = false;
    const lastJob = jobIdFrom(
      document.querySelector("[data-normal-clustering-job]")?.textContent,
    );
    setActiveJobId(nextJobId(lastJob));
    setActiveClusteringAttempt(1);
    setQuestionState("clustering-pending");
  }
  delete questions.dataset.fixtureApplied;
}

function createReactionButton() {
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
  return reaction;
}

function createQuestionItem(
  text,
  questionId,
  { unclustered = false, backlog = false } = {},
) {
  const item = document.createElement("li");
  item.className = "question-cluster-list__item";
  item.dataset.memberKind = "student-question";
  item.dataset.questionId = questionId;
  item.dataset.localQuestion = "true";
  if (unclustered) item.dataset.runtimeUnclustered = "true";
  if (backlog) item.dataset.clusteringBacklog = "true";

  const meta = document.createElement("div");
  meta.className = "question-cluster-list__meta";
  const kind = document.createElement("span");
  const status = document.createElement("span");
  kind.textContent = "STUDENT_QUESTION";
  status.textContent = unclustered
    ? "OPEN · 클러스터 미배치"
    : "OPEN · 배치 완료";
  meta.append(kind, status);

  const copy = document.createElement("p");
  copy.textContent = text;
  item.append(meta, copy, createReactionButton());
  return item;
}

function createPriorityQuestion(text, questionId, { backlog = false } = {}) {
  const item = document.createElement("li");
  item.dataset.questionPriorityItem = "";
  item.dataset.priorityQuestionId = questionId;
  item.dataset.questionId = questionId;
  item.dataset.localQuestion = "true";
  item.dataset.reactionCount = "0";
  item.dataset.createdOrder = String(++localCreatedOrder);
  if (backlog) item.dataset.clusteringBacklog = "true";

  const copy = document.createElement("div");
  const title = document.createElement("strong");
  const meta = document.createElement("small");
  title.textContent = text;
  meta.textContent = "OPEN · Cluster 미배치 · 익명 질문";
  copy.append(title, meta);
  item.append(copy, createReactionButton());
  return item;
}

function initializeQuestionFixture() {
  if (questions?.dataset.demoState === "unclustered") {
    setDemoState(questions, "clustering-pending");
  }
  observedQuestionState = questions?.dataset.demoState;
  retryInFlight = observedQuestionState === "clustering-retry-reserved";
}

function removeStaticQuestionFixture() {
  document
    .querySelectorAll("[data-question-fixture-unclustered]")
    .forEach((item) => item.remove());
}

function captureAllQueuedQuestionsForFreshJob() {
  [...(unclusteredQuestions?.children || [])].forEach((item) => {
    delete item.dataset.clusteringBacklog;
    questionPriorityList
      ?.querySelector(
        `[data-question-priority-item][data-question-id="${item.dataset.questionId}"]`,
      )
      ?.removeAttribute("data-clustering-backlog");
  });
}

function prepareNormalQuestionSubmission() {
  removeStaticQuestionFixture();
  const requested = document.querySelector("[data-requested-sequence]");
  const applied = document.querySelector("[data-applied-sequence]");
  const pending = document.querySelector("[data-pending-count]");
  if (requested) {
    requested.textContent =
      document.querySelector("[data-normal-requested-sequence]")?.textContent ||
      "46";
  }
  if (applied) {
    applied.textContent =
      document.querySelector("[data-normal-applied-sequence]")?.textContent ||
      "46";
  }
  if (pending) pending.textContent = "0";
}

function advanceGeneration() {
  const label = document.querySelector("[data-normal-generation]");
  const matches = label?.textContent.match(/generation (\d+) · revision (\d+)/);
  const generation = Number(matches?.[1] || "7") + 1;
  const revision = Number(matches?.[2] || "12") + 1;
  if (label)
    label.textContent = `generation ${generation} · revision ${revision}`;
  const currentGeneration = document.querySelector("[data-current-generation]");
  const currentRevision = document.querySelector("[data-current-revision]");
  if (currentGeneration) currentGeneration.textContent = String(generation);
  if (currentRevision) currentRevision.textContent = String(revision);
  const representative = document.querySelector(
    "[data-current-representative]",
  );
  if (representative) {
    representative.dataset.representativeId = `rep-${generation}-${revision}`;
    representative.dataset.createdInGeneration = String(generation);
    const meta = representative.querySelector("small");
    if (meta) {
      meta.textContent = `AI 대표질문 · ACTIVE · created_in_generation=${generation}`;
    }
    const copy = representative.querySelector("p");
    if (copy) {
      copy.textContent =
        "음수 간선과 음수 사이클을 고려한 최단 경로 선택 기준은 무엇인가요?";
    }
  }
}

function applyPendingQuestions() {
  const completedState = observedQuestionState;
  const completedRetry = retryInFlight;
  if (completedState === "cluster-failed" && !completedRetry) {
    captureAllQueuedQuestionsForFreshJob();
  }
  const queued = [...(unclusteredQuestions?.children || [])];
  const captured = queued.filter(
    (item) => item.dataset.clusteringBacklog !== "true",
  );
  const backlog = queued.filter(
    (item) => item.dataset.clusteringBacklog === "true",
  );
  captured.reverse().forEach((item) => {
    delete item.dataset.runtimeUnclustered;
    item.removeAttribute("data-question-fixture-unclustered");
    const status = item.querySelector(
      ".question-cluster-list__meta span:last-child",
    );
    if (status) status.textContent = "OPEN · 배치 완료";
    const questionId = item.dataset.questionId;
    const priorityItem = questionPriorityList?.querySelector(
      `[data-question-priority-item][data-question-id="${questionId}"]`,
    );
    if (priorityItem) {
      priorityItem.removeAttribute("data-question-fixture-unclustered");
      priorityItem.removeAttribute("data-show-state");
      priorityItem.hidden = false;
      const priorityMeta = priorityItem.querySelector("small");
      if (priorityMeta) {
        priorityMeta.textContent = "OPEN · Cluster 배치 완료 · 익명 질문";
      }
    }
    clusterMembers.prepend(item);
  });
  if (queued.length === 0) return;

  const requested = document.querySelector("[data-requested-sequence]");
  const applied = document.querySelector("[data-applied-sequence]");
  const count = document.querySelector("[data-pending-count]");
  const previousApplied = Number(applied?.textContent || "46");
  const nextApplied = previousApplied + captured.length;
  if (applied) applied.textContent = String(nextApplied);
  if (count) count.textContent = String(backlog.length);
  const normalRequested = document.querySelector(
    "[data-normal-requested-sequence]",
  );
  const normalApplied = document.querySelector(
    "[data-normal-applied-sequence]",
  );
  if (requested && normalRequested) {
    normalRequested.textContent = requested.textContent;
  }
  if (normalApplied) normalApplied.textContent = String(nextApplied);

  const completedJobId =
    completedState === "cluster-failed" && !completedRetry
      ? nextJobId(activeJobId())
      : activeJobId();
  const normalJob = document.querySelector("[data-normal-clustering-job]");
  const normalAttempt = document.querySelector(
    "[data-normal-clustering-attempt]",
  );
  const currentLastJob = document.querySelector(
    "[data-current-last-clustering-job]",
  );
  const currentLastAttempt = document.querySelector(
    "[data-current-last-clustering-attempt]",
  );
  const completedAttempt = completedRetry ? 2 : 1;
  if (normalJob) normalJob.textContent = `last job: ${completedJobId}`;
  if (normalAttempt) {
    normalAttempt.textContent = `attempt ${completedAttempt}`;
  }
  if (currentLastJob) currentLastJob.textContent = completedJobId;
  if (currentLastAttempt) {
    currentLastAttempt.textContent = `attempt ${completedAttempt}`;
  }
  if (captured.length > 0) advanceGeneration();

  if (backlog.length > 0) {
    const freshJobId = nextJobId(completedJobId);
    backlog.forEach((item) => {
      delete item.dataset.clusteringBacklog;
      questionPriorityList
        ?.querySelector(
          `[data-question-priority-item][data-question-id="${item.dataset.questionId}"]`,
        )
        ?.removeAttribute("data-clustering-backlog");
    });
    setActiveJobId(freshJobId);
    retryInFlight = false;
    setActiveClusteringAttempt(1);
    setQuestionState("clustering-pending");
    delete questions.dataset.fixtureApplied;
    announce(
      `현재 Job을 종료하고 새 질문 ${backlog.length}개를 fresh ${freshJobId}에 한꺼번에 예약했습니다.`,
    );
  } else {
    retryInFlight = false;
    setActiveClusteringAttempt(1);
    setQuestionState("normal");
    questions.dataset.fixtureApplied = "true";
    announce(
      "클러스터링 성공 결과를 적용해 captured 질문을 대표질문의 member list에 배치했습니다.",
    );
  }
  refreshQuestionPriority();
}

function setFormBusy(form, busy) {
  form.setAttribute("aria-busy", String(busy));
  form.querySelectorAll("button").forEach((button) => {
    button.disabled = busy;
  });
}

function lockStudentLive(state) {
  liveView.dataset.terminalLocked = "true";
  liveView.dataset.terminalState = state;
  liveView
    .querySelectorAll("textarea, input, button")
    .forEach((control) => (control.disabled = true));
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

  const previousQuestionState = questions?.dataset.demoState;
  if (previousQuestionState === "normal") prepareNormalQuestionSubmission();
  if (previousQuestionState === "cluster-failed") {
    captureAllQueuedQuestionsForFreshJob();
  }
  const backlog = [
    "clustering-pending",
    "clustering-running",
    "clustering-retry-reserved",
  ].includes(previousQuestionState);
  const questionId = `question-local-${++localQuestionSequence}`;
  unclusteredQuestions.prepend(
    createQuestionItem(value, questionId, {
      unclustered: true,
      backlog,
    }),
  );
  questionPriorityList.append(
    createPriorityQuestion(value, questionId, { backlog }),
  );
  refreshQuestionPriority();
  updateQuestionWatermark(previousQuestionState);
  observedQuestionState = questions?.dataset.demoState;
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

initializeQuestionFixture();

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
  const viewStateAction = event.target
    .closest("[data-state]")
    ?.closest('[data-state-switcher][data-state-target="#studentLiveView"]');

  if (
    viewStateAction &&
    liveView.dataset.terminalLocked === "true" &&
    event.target.closest("[data-state]")?.dataset.state !==
      liveView.dataset.terminalState
  ) {
    setDemoState(liveView, liveView.dataset.terminalState);
    showToast("종료된 LIVE 화면으로 돌아갈 수 없습니다.", "info");
    return;
  }

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
    const questionId =
      reaction.closest("[data-question-id]")?.dataset.questionId;
    const nextPressed = !previousPressed;
    const nextCount = previousCount + (previousPressed ? -1 : 1);
    const localQuestion = document.querySelector(
      `[data-question-id="${questionId}"][data-local-question="true"]`,
    );
    const syncReaction = (pressed, count) => {
      document
        .querySelectorAll(`[data-question-id="${questionId}"] [data-reaction]`)
        .forEach((button) => {
          button.setAttribute("aria-pressed", String(pressed));
          const linkedCounter = button.querySelector("[data-reaction-count]");
          if (linkedCounter) linkedCounter.textContent = String(count);
        });
      document
        .querySelectorAll(
          `[data-question-priority-item][data-question-id="${questionId}"]`,
        )
        .forEach((item) => (item.dataset.reactionCount = String(count)));
      refreshQuestionPriority();
    };
    syncReaction(nextPressed, nextCount);

    if (reactionFailOnce || localQuestion) {
      syncReaction(previousPressed, previousCount);
      const message = localQuestion
        ? "자기 질문에는 반응할 수 없어 서버 거부 후 이전 상태로 되돌렸습니다."
        : "서버 거부를 모의해 이전 반응 상태로 되돌렸습니다.";
      reactionFailOnce = false;
      showToast(message, "error");
    }
  }

  if (latest) {
    transcriptStream?.lastElementChild?.scrollIntoView({ block: "end" });
    showToast("가장 최근 Transcript로 이동했습니다.", "info");
  }

  if (terminal) {
    removePartial("종료 상태 전환으로 저장되지 않은 partial을 제거했습니다.");
    lockStudentLive(terminal.dataset.state || "processing");
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
    const nextState = event.target.closest("[data-state]")?.dataset.state;
    if (questions.dataset.fixtureApplied === "true" && nextState !== "normal") {
      event.stopPropagation();
      setQuestionState("normal");
      showToast(
        "적용된 질문을 이전 fixture로 되돌릴 수 없습니다. 다른 상태는 새로고침해 확인해 주세요.",
        "info",
      );
      return;
    }
    if (nextState === "normal" && observedQuestionState !== "normal") {
      applyPendingQuestions();
      return;
    }
    if (nextState === "clustering-retry-reserved") {
      retryInFlight = true;
    } else if (nextState === "cluster-failed") {
      retryInFlight = false;
    }
    if (["clustering-pending", "clustering-running"].includes(nextState)) {
      setActiveClusteringAttempt(retryInFlight ? 2 : 1);
    }
    if (nextState) observedQuestionState = nextState;
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
  lockStudentLive(liveView.dataset.demoState);
}
