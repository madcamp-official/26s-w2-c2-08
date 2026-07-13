import {
  closeDialog,
  openDialog,
  setDemoState,
  showToast,
} from "./prototype.js";
import {
  initLiveCommon,
  normalizeLiveInput,
  refreshQuestionPriority,
} from "./live-common.js";

const eventState = document.querySelector("#eventState");
const publisherState = document.querySelector("#publisherState");
const audioState = document.querySelector("#audioState");
const recordingState = document.querySelector("#recordingState");
const sttState = document.querySelector("#sttState");
const questionsPanel = document.querySelector("#questionsPanel");
const answerState = document.querySelector("#answerState");
const endFlow = document.querySelector("#endFlow");
const endDialog = document.querySelector("#endDialog");
const leaveDialog = document.querySelector("#leaveDialog");
const materialDialog = document.querySelector("#materialDialog");
const materialsPanel = document.querySelector("#materialsPanel");
const materialList = document.querySelector("[data-material-list]");
const materialInput = document.querySelector("#liveMaterialInput");
const materialError = document.querySelector("[data-material-error]");
const materialCount = document.querySelector("[data-material-count]");
const announcement = document.querySelector("#liveAnnouncement");
const transcriptStream = document.querySelector("#transcriptStream");
const liveView = document.querySelector("#liveView");
const questionPriorityList = document.querySelector(
  "[data-question-priority-list]",
);
const unclusteredQuestionList = document.querySelector(
  "#profUnclusteredQuestionsTitle + p + ul",
);
const questionBranches = document.querySelector(".live-mindmap__branches");

const { announce } = initLiveCommon({ announcer: announcement });

if (questionsPanel?.dataset.demoState === "unclustered") {
  setDemoState(questionsPanel, "clustering-pending");
}

let activeAnswer = null;
let partialRevision = 2;
let pendingMaterialRow = null;
let endingSession = false;
let materialSequence = 0;
let observedQuestionState = questionsPanel?.dataset.demoState;
let retryInFlight = observedQuestionState === "clustering-retry-reserved";

function setActiveClusteringAttempt(attempt) {
  document
    .querySelectorAll("[data-active-clustering-attempt]")
    .forEach((label) => (label.textContent = `attempt ${attempt}`));
}

function getActivePartial() {
  return document.querySelector('[data-transcript-kind="partial"]');
}

function isCapturing() {
  return ["waiting", "candidate", "not-ready"].includes(
    answerState?.dataset.demoState,
  );
}

function setAnswerControlsDisabled(disabled) {
  document.querySelectorAll("[data-answer-select]").forEach((button) => {
    const target = button.closest("[data-answer-target]");
    const answered = target?.dataset.answerTargetStatus === "answered";
    button.disabled = disabled || answered;
  });
  document.querySelectorAll("[data-priority-answer]").forEach((button) => {
    const target = document.querySelector(
      `[data-answer-target-id="${button.dataset.priorityAnswer}"]`,
    );
    const answered = target?.dataset.answerTargetStatus === "answered";
    button.disabled = disabled || answered;
  });
}

function updateTargetStatus(target, status) {
  if (!target) return;
  target.dataset.answerTargetStatus = status;
  const label = target.querySelector("[data-answer-status-label]");
  if (label) label.textContent = status.toUpperCase();
  const targetId = target.dataset.answerTargetId;
  if (!targetId) return;
  document
    .querySelectorAll(
      `[data-question-priority-item][data-question-id="${targetId}"] [data-priority-status-label]`,
    )
    .forEach((item) => (item.textContent = status.toUpperCase()));
}

function replaceProfessorRepresentative() {
  const central = questionsPanel.querySelector(
    ".live-mindmap__center[data-answer-target]",
  );
  if (!central) return;
  const previousStatus = central.dataset.answerTargetStatus;
  const previousId = central.dataset.answerTargetId;
  const previousGeneration = central.dataset.createdInGeneration || "7";
  const previousText = normalizeLiveInput(
    central.querySelector("[data-answer-target-text]")?.textContent || "",
  );

  if (["selected", "answered"].includes(previousStatus)) {
    const preserved = document.createElement("li");
    preserved.className = "live-mindmap__node";
    preserved.dataset.nodeKind = "representative-preserved";
    preserved.dataset.answerTarget = "";
    preserved.dataset.answerTargetKind = "representative";
    preserved.dataset.answerTargetId = previousId;
    preserved.dataset.answerTargetStatus = previousStatus;

    const meta = document.createElement("div");
    meta.className = "live-node-meta";
    const kind = document.createElement("span");
    kind.textContent = `source_kind=AI_REPRESENTATIVE · created_in_generation=${previousGeneration} · PRESERVED`;
    const status = document.createElement("span");
    status.dataset.answerStatusLabel = "";
    status.textContent = previousStatus.toUpperCase();
    meta.append(kind, status);

    const copy = document.createElement("p");
    copy.dataset.answerTargetText = "";
    copy.textContent = previousText;
    const answer = document.createElement("button");
    answer.className = "button button--secondary";
    answer.type = "button";
    answer.dataset.answerSelect = "";
    answer.textContent = "이 보존 대표질문 답변";
    answer.disabled = true;
    preserved.append(meta, copy, answer);
    questionBranches?.append(preserved);
    if (activeAnswer?.target === central) activeAnswer.target = preserved;
  }

  central.dataset.answerTargetId = "rep-8-13";
  central.dataset.answerTargetStatus = "open";
  central.dataset.createdInGeneration = String(Number(previousGeneration) + 1);
  const status = document.createElement("span");
  status.dataset.answerStatusLabel = "";
  status.textContent = "OPEN";
  central
    .querySelector("small")
    ?.replaceChildren(
      `AI 대표질문 · ACTIVE · created_in_generation=${central.dataset.createdInGeneration} · `,
      status,
    );
  const copy = central.querySelector("[data-answer-target-text]");
  if (copy) {
    copy.textContent =
      "음수 간선과 음수 사이클을 고려한 최단 경로 선택 기준은 무엇인가요?";
  }
  setAnswerControlsDisabled(isCapturing());
}

function applyProfessorPendingQuestions() {
  const pending = [...(unclusteredQuestionList?.children || [])];
  pending.reverse().forEach((item) => {
    item.removeAttribute("data-question-fixture-unclustered");
    const kind = item.querySelector(".live-node-meta span:first-child");
    if (kind) kind.textContent = "STUDENT_QUESTION";
    const questionId = item.dataset.questionId;
    const priorityItem = questionPriorityList?.querySelector(
      `[data-question-priority-item][data-question-id="${questionId}"]`,
    );
    if (priorityItem) {
      priorityItem.removeAttribute("data-question-fixture-unclustered");
      priorityItem.removeAttribute("data-show-state");
      priorityItem.hidden = false;
      const priorityMeta = priorityItem.querySelector("small");
      const priorityStatus = priorityItem.querySelector(
        "[data-priority-status-label]",
      );
      if (priorityMeta && priorityStatus) {
        priorityMeta.replaceChildren(
          `궁금해요 ${priorityItem.dataset.reactionCount} · Cluster 배치 완료 · `,
          priorityStatus,
        );
      }
    }
    questionBranches?.prepend(item);
  });
  if (pending.length > 0) {
    replaceProfessorRepresentative();
    const requested = document.querySelector(
      '.live-clustering-status__header p[data-show-state~="clustering-pending"]',
    );
    const requestedSequence =
      requested?.textContent.match(/requested sequence (\d+)/)?.[1] || "48";
    const normalRequested = document.querySelector(
      "[data-normal-requested-sequence]",
    );
    const normalApplied = document.querySelector(
      "[data-normal-applied-sequence]",
    );
    const normalGeneration = document.querySelector("[data-normal-generation]");
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
    const resultJobId =
      observedQuestionState === "cluster-failed" && !retryInFlight
        ? "job-cluster-008"
        : "job-cluster-007";
    const resultAttempt = retryInFlight ? 2 : 1;
    if (normalRequested) normalRequested.textContent = requestedSequence;
    if (normalApplied) normalApplied.textContent = requestedSequence;
    if (normalGeneration)
      normalGeneration.textContent = "generation 8 · revision 13";
    const currentGeneration = document.querySelector(
      "[data-current-generation]",
    );
    const currentRevision = document.querySelector("[data-current-revision]");
    if (currentGeneration) currentGeneration.textContent = "8";
    if (currentRevision) currentRevision.textContent = "13";
    if (normalJob) normalJob.textContent = `last job: ${resultJobId}`;
    if (normalAttempt) {
      normalAttempt.textContent = `attempt ${resultAttempt}`;
    }
    if (currentLastJob) currentLastJob.textContent = resultJobId;
    if (currentLastAttempt) {
      currentLastAttempt.textContent = `attempt ${resultAttempt}`;
    }
    retryInFlight = false;
    setActiveClusteringAttempt(1);
    questionsPanel.dataset.fixtureApplied = "true";
    refreshQuestionPriority();
    announce(
      "클러스터링 성공 결과를 적용해 미배치 질문을 대표질문의 branch에 배치했습니다.",
    );
  }
}

function latestFinalSequence() {
  return Math.max(
    0,
    ...[...document.querySelectorAll('[data-transcript-kind="final"]')].map(
      (item) => Number(item.dataset.sequence || 0),
    ),
  );
}

function startAnswer(button, returnButton = button) {
  if (isCapturing()) return;
  const target = button.closest("[data-answer-target]");
  if (!target || target.dataset.answerTargetStatus === "answered") return;

  const snapshot = normalizeLiveInput(
    target.querySelector("[data-answer-target-text]")?.textContent || "",
  );
  const sequence = latestFinalSequence();
  activeAnswer = {
    target,
    targetId: target.dataset.answerTargetId,
    targetKind: target.dataset.answerTargetKind,
    snapshot,
    captureStartedAfterSequence: sequence,
    returnButton,
  };

  document.querySelectorAll("[data-answer-snapshot]").forEach((item) => {
    item.textContent = snapshot;
  });
  document.querySelectorAll("[data-answer-boundary]").forEach((item) => {
    item.textContent = `sequence ${sequence} 이후`;
  });
  updateTargetStatus(target, "selected");
  setAnswerControlsDisabled(true);
  setDemoState(answerState, "waiting");
  answerState.focus();
  announce(
    `${activeAnswer.targetKind} 하나를 선택하고 질문 문구 snapshot을 저장했습니다.`,
  );
}

function cancelAnswer() {
  if (!activeAnswer) {
    setDemoState(answerState, "idle");
    setAnswerControlsDisabled(false);
    return;
  }
  const { target, returnButton } = activeAnswer;
  if (target.dataset.nodeKind === "representative-preserved") {
    target.remove();
  } else {
    updateTargetStatus(target, "open");
  }
  document
    .querySelectorAll('[data-transcript-kind="candidate"]')
    .forEach((item) => (item.dataset.transcriptKind = "final"));
  activeAnswer = null;
  setDemoState(answerState, "idle");
  setAnswerControlsDisabled(false);
  returnButton?.focus();
  announce(
    "CAPTURING Answer를 hard delete했습니다. CANCELLED 기록은 남기지 않습니다.",
  );
}

function completeAnswer() {
  if (!activeAnswer || answerState.dataset.demoState !== "candidate") {
    setDemoState(answerState, "not-ready");
    answerState.focus();
    announce("새 final이 없어 Answer는 CAPTURING을 유지합니다.");
    return;
  }

  const completedTarget = activeAnswer.target;
  updateTargetStatus(completedTarget, "answered");
  document
    .querySelectorAll('[data-transcript-kind="candidate"]')
    .forEach((item) => (item.dataset.transcriptKind = "final"));
  activeAnswer = null;
  setAnswerControlsDisabled(false);
  setDemoState(answerState, "completed");
  answerState.focus();
  announce(
    "선택한 target 하나만 답변 완료했습니다. 같은 Cluster의 다른 질문 상태는 바꾸지 않았습니다.",
  );
}

function removePartial(reason) {
  const partial = getActivePartial();
  if (!partial) return;
  partial.remove();
  announce(reason);
}

function shouldWarnBeforeLeave() {
  const recordingAtRisk = ["recording", "finalizing", "ready-upload"].includes(
    recordingState?.dataset.demoState,
  );
  const publisherAtRisk = ["active", "reconnecting", "resumed"].includes(
    publisherState?.dataset.demoState,
  );
  return recordingAtRisk || (!endingSession && publisherAtRisk);
}

function lockLiveControls() {
  endingSession = true;
  liveView.dataset.terminalLocked = "true";
  liveView.dataset.terminalState = "processing";
  liveView
    ?.querySelectorAll(
      "[data-show-state='normal'] input, [data-show-state='normal'] textarea, [data-show-state='normal'] button",
    )
    .forEach((control) => (control.disabled = true));
}

function handleBeforeUnload(event) {
  if (!shouldWarnBeforeLeave()) return;
  event.preventDefault();
  event.returnValue = "";
}

window.addEventListener("beforeunload", handleBeforeUnload);

function updateMaterialCount() {
  const count =
    materialList?.querySelectorAll("[data-material-row]").length || 0;
  if (materialCount) materialCount.textContent = String(count);
  if (materialInput) materialInput.disabled = count >= 10;
  return count;
}

function materialDisplayName(originalName) {
  const dot = originalName.lastIndexOf(".");
  const stem = dot > 0 ? originalName.slice(0, dot) : originalName;
  const extension = dot > 0 ? originalName.slice(dot) : "";
  const names = new Set(
    [...materialList.querySelectorAll("[data-material-name]")].map(
      (item) => item.dataset.materialName,
    ),
  );
  if (!names.has(originalName)) return originalName;
  let suffix = 1;
  while (names.has(`${stem} (${suffix})${extension}`)) suffix += 1;
  return `${stem} (${suffix})${extension}`;
}

function ensureMaterialOpenAction(row) {
  let actions = row.querySelector(":scope > .cluster");
  const deleteButton = row.querySelector("[data-material-delete]");
  if (!actions) {
    actions = document.createElement("div");
    actions.className = "cluster";
    if (deleteButton) actions.append(deleteButton);
    row.append(actions);
  }
  if (!actions.querySelector("a")) {
    if (!row.dataset.materialId) {
      materialSequence += 1;
      row.dataset.materialId = `material-live-${String(materialSequence).padStart(3, "0")}`;
    }
    const link = document.createElement("a");
    link.className = "button button--ghost";
    link.href = `/api/v1/materials/${row.dataset.materialId}/content`;
    link.textContent = "원본 열기";
    link.setAttribute(
      "aria-label",
      `${row.dataset.materialName || "PDF 자료"} 원본 열기`,
    );
    actions.prepend(link);
  }
}

function createMaterialRow(name, status = "uploaded") {
  const row = document.createElement("li");
  row.className = "live-material-row";
  row.dataset.materialRow = "";
  row.dataset.materialName = name;
  row.dataset.materialStatus = status;

  const copy = document.createElement("div");
  const title = document.createElement("strong");
  const meta = document.createElement("small");
  title.textContent = name;
  meta.textContent =
    status === "ready"
      ? "READY · 새 AI 검색 근거로 사용"
      : "UPLOADED · 처리 대기 · LIVE 기능 차단 없음";
  copy.append(title, meta);

  const remove = document.createElement("button");
  remove.className = "button button--danger";
  remove.type = "button";
  remove.dataset.materialDelete = "";
  remove.textContent = `${name} 삭제`;
  const actions = document.createElement("div");
  actions.className = "cluster";
  actions.append(remove);
  row.append(copy, actions);
  ensureMaterialOpenAction(row);
  return row;
}

function detachMaterialEvidence(name) {
  document.querySelectorAll("[data-evidence-material-name]").forEach((link) => {
    if (link.dataset.evidenceMaterialName !== name) return;
    const replacement = document.createElement("span");
    replacement.className = "live-evidence-link";
    replacement.setAttribute("aria-disabled", "true");
    const label = document.createElement("strong");
    const meta = document.createElement("small");
    label.textContent = link.querySelector("strong")?.textContent || name;
    meta.textContent =
      "source_kind: MATERIAL · label snapshot 유지 · link: null";
    replacement.append(label, meta);
    link.replaceWith(replacement);
  });
}

function setMaterialError(message) {
  if (!materialError) return;
  materialError.textContent = message;
  materialError.hidden = !message;
  materialInput?.setAttribute("aria-invalid", String(Boolean(message)));
  if (message) materialInput?.focus();
}

function applyMaterialFixture() {
  const fixture = materialsPanel?.dataset.demoState;
  if (fixture === "empty") {
    materialList?.replaceChildren();
  }
  if (fixture === "full" && materialList) {
    let count = updateMaterialCount();
    while (count < 10) {
      materialList.append(
        createMaterialRow(`추가 자료 ${count + 1}.pdf`, "ready"),
      );
      count += 1;
    }
  }
  if (fixture === "all-ready" && materialList) {
    materialList.querySelectorAll("[data-material-row]").forEach((row) => {
      row.dataset.materialStatus = "ready";
      const meta = row.querySelector("small");
      if (meta) meta.textContent = "READY · 새 AI 검색 근거로 사용";
      row.querySelector("[data-material-retry]")?.remove();
      ensureMaterialOpenAction(row);
    });
  }
  updateMaterialCount();
}

function initializeAnswerFixture() {
  const state = answerState?.dataset.demoState;
  const target = document.querySelector('[data-answer-target-id="rep-7-12"]');
  if (!target) return;
  if (state === "completed") {
    updateTargetStatus(target, "answered");
    setAnswerControlsDisabled(false);
    return;
  }
  if (!["waiting", "candidate", "not-ready"].includes(state)) return;
  const snapshot = normalizeLiveInput(
    target.querySelector("[data-answer-target-text]")?.textContent || "",
  );
  const sequence = latestFinalSequence();
  activeAnswer = {
    target,
    targetId: target.dataset.answerTargetId,
    targetKind: target.dataset.answerTargetKind,
    snapshot,
    captureStartedAfterSequence: sequence,
    returnButton: target.querySelector("[data-answer-select]"),
  };
  document.querySelectorAll("[data-answer-snapshot]").forEach((item) => {
    item.textContent = snapshot;
  });
  document.querySelectorAll("[data-answer-boundary]").forEach((item) => {
    item.textContent = `sequence ${sequence} 이후`;
  });
  updateTargetStatus(target, "selected");
  if (state === "candidate") {
    const partial = getActivePartial();
    if (partial) {
      partial.removeAttribute("id");
      partial.dataset.transcriptKind = "candidate";
      partial.dataset.sequence = String(sequence + 1);
      const time = partial.querySelector("[data-transcript-time]");
      const text = partial.querySelector("[data-partial-text]");
      const meta = partial.querySelector("[data-partial-meta]");
      if (time) time.textContent = "10:34";
      if (text) {
        text.textContent =
          "다익스트라는 음수 가중치가 없을 때 최단 경로를 구합니다.";
      }
      if (meta) {
        meta.textContent = `final · DB commit · sequence ${sequence + 1}`;
      }
    }
  }
  setAnswerControlsDisabled(true);
}

document.addEventListener("click", (event) => {
  const publisherStart = event.target.closest("[data-publisher-start]");
  const micRequest = event.target.closest("[data-mic-request]");
  const micAllow = event.target.closest("[data-mic-allow]");
  const micDeny = event.target.closest("[data-mic-deny]");
  const reconnect = event.target.closest("[data-event-reconnect]");
  const revision = event.target.closest("[data-partial-revision]");
  const finalize = event.target.closest("[data-partial-finalize]");
  const answerSelect = event.target.closest("[data-answer-select]");
  const priorityAnswer = event.target.closest("[data-priority-answer]");
  const answerComplete = event.target.closest("[data-answer-complete]");
  const answerCancel = event.target.closest("[data-answer-cancel]");
  const materialDelete = event.target.closest("[data-material-delete]");
  const materialDeleteConfirm = event.target.closest(
    "[data-material-delete-confirm]",
  );
  const materialRetry = event.target.closest("[data-material-retry]");
  const materialOpen = event.target.closest(
    '.live-material-row a[href^="/api/v1/materials/"]',
  );
  const leavePreview = event.target.closest("[data-leave-preview]");
  const endOpen = event.target.closest("[data-end-open]");
  const endConfirm = event.target.closest("[data-end-confirm]");
  const viewProcessing = event.target
    .closest('[data-state="processing"]')
    ?.closest('[data-state-switcher][data-state-target="#liveView"]');

  if (viewProcessing) {
    lockLiveControls();
    removePartial("PROCESSING 상태에서는 저장되지 않은 partial을 숨깁니다.");
  }

  const viewStateAction = event.target
    .closest("[data-state]")
    ?.closest('[data-state-switcher][data-state-target="#liveView"]');
  if (
    viewStateAction &&
    liveView.dataset.terminalLocked === "true" &&
    event.target.closest("[data-state]")?.dataset.state !== "processing"
  ) {
    setDemoState(liveView, "processing");
    showToast("종료된 LIVE 화면으로 돌아갈 수 없습니다.", "info");
  }

  if (publisherStart) {
    setDemoState(publisherState, "starting");
    setDemoState(audioState, "permission");
    announce(
      "마이크 권한을 확인합니다. 아직 audio.start가 성공하지 않아 publisher를 선점하지 않았습니다.",
    );
  }
  if (micRequest) {
    if (publisherState.dataset.demoState === "conflict") {
      showToast(
        "다른 publisher가 전송 중이라 Audio만 시작할 수 없습니다.",
        "error",
      );
    } else {
      setDemoState(publisherState, "starting");
      setDemoState(audioState, "connecting");
      announce(
        "마이크 권한 목 응답을 기다립니다. publisher는 audio.start 성공 전까지 선점하지 않습니다.",
      );
    }
  }
  if (micAllow) {
    if (publisherState.dataset.demoState === "conflict") {
      setDemoState(audioState, "error");
      showToast(
        "다른 publisher가 전송 중이라 Audio를 시작할 수 없습니다.",
        "error",
      );
    } else {
      setDemoState(publisherState, "active");
      setDemoState(audioState, "listening");
      setDemoState(recordingState, "recording");
      setDemoState(sttState, "listening");
      announce("한 마이크 입력을 실시간 PCM과 로컬 녹음으로 분기했습니다.");
    }
  }
  if (micDeny) {
    if (publisherState.dataset.demoState !== "conflict") {
      setDemoState(publisherState, "checking");
    }
    setDemoState(audioState, "denied");
    setDemoState(recordingState, "idle");
    announce("마이크 권한은 거부됐지만 조회 기능은 계속 사용할 수 있습니다.");
  }
  if (reconnect) {
    setDemoState(eventState, "reconnecting");
    removePartial("재연결 시 저장되지 않은 partial만 제거했습니다.");
  }
  if (revision) {
    const partial = getActivePartial();
    if (!partial) {
      showToast("현재 partial이 없습니다.", "info");
    } else {
      partialRevision += 1;
      partial.dataset.revision = String(partialRevision);
      const text = partial.querySelector("[data-partial-text]");
      const label = partial.querySelector("[data-partial-revision-label]");
      if (text) {
        text.textContent =
          "다익스트라는 음수 가중치가 없을 때 최단 경로를 구합니다.";
      }
      if (label) label.textContent = `revision ${partialRevision}`;
    }
  }
  if (finalize) {
    const partial = getActivePartial();
    if (!partial) {
      showToast("현재 partial이 없습니다.", "info");
    } else {
      partial.dataset.transcriptKind = activeAnswer ? "candidate" : "final";
      partial.dataset.sequence = "128";
      partial.removeAttribute("id");
      const time = partial.querySelector("[data-transcript-time]");
      const text = partial.querySelector("[data-partial-text]");
      const meta = partial.querySelector("[data-partial-meta]");
      if (time) time.textContent = "10:34";
      if (text) {
        text.textContent =
          "다익스트라는 음수 가중치가 없을 때 최단 경로를 구합니다.";
      }
      if (meta) meta.textContent = "final · DB commit · sequence 128";
      if (activeAnswer) setDemoState(answerState, "candidate");
      announce("sequence 128 final이 DB에 저장됐습니다.");
    }
  }
  if (answerSelect) startAnswer(answerSelect);
  if (priorityAnswer) {
    const target = document.querySelector(
      `[data-answer-target-id="${priorityAnswer.dataset.priorityAnswer}"]`,
    );
    const canonicalAnswer = target?.querySelector("[data-answer-select]");
    if (canonicalAnswer) startAnswer(canonicalAnswer, priorityAnswer);
  }
  if (answerComplete) completeAnswer();
  if (answerCancel) cancelAnswer();

  if (materialDelete) {
    pendingMaterialRow = materialDelete.closest("[data-material-row]");
    const name = pendingMaterialRow?.dataset.materialName || "선택 자료";
    const label = materialDialog.querySelector("[data-material-delete-name]");
    if (label) label.textContent = name;
    openDialog(materialDialog, materialDelete);
  }
  if (materialDeleteConfirm && pendingMaterialRow) {
    const name = pendingMaterialRow.dataset.materialName;
    detachMaterialEvidence(name);
    pendingMaterialRow.remove();
    pendingMaterialRow = null;
    closeDialog(materialDialog);
    updateMaterialCount();
    const materialsTitle = document.querySelector("#materialsTitle");
    if (materialsTitle) {
      materialsTitle.tabIndex = -1;
      materialsTitle.focus();
    }
    showToast(`${name} 링크를 즉시 해제했습니다.`, "success");
  }
  if (materialRetry) {
    const row = materialRetry.closest("[data-material-row]");
    row.dataset.materialStatus = "processing";
    row.querySelector("small").textContent =
      "PROCESSING · 같은 Material Job attempt 2 · LIVE 기능 차단 없음";
    materialRetry.remove();
    ensureMaterialOpenAction(row);
    showToast("같은 Material 행의 attempt를 증가해 재시도합니다.", "success");
  }
  if (materialOpen) {
    event.preventDefault();
    showToast(
      "정적 Prototype에서는 Material 권한 재검사와 원본 열기만 모의합니다.",
      "info",
    );
  }
  if (leavePreview) openDialog(leaveDialog, leavePreview);

  if (endOpen) {
    if (isCapturing()) {
      showToast(
        "진행 중인 답변을 완료하거나 취소한 뒤 종료해 주세요.",
        "error",
      );
      answerState.focus();
    } else {
      setDemoState(endFlow, "confirm");
      openDialog(endDialog, endOpen);
    }
  }
  if (endConfirm) {
    closeDialog(endDialog);
    lockLiveControls();
    removePartial("종료 시 저장되지 않은 live partial을 제거했습니다.");
    setDemoState(endFlow, "processing");
    setDemoState(eventState, "stopped");
    setDemoState(recordingState, "finalizing");
    questionsPanel.dataset.clusteringFenced = "true";
    setDemoState(liveView, "processing");
    const processingHeading = liveView.querySelector(
      '[data-show-state="processing"] h2',
    );
    if (processingHeading) {
      processingHeading.tabIndex = -1;
      processingHeading.focus();
    }
    window.setTimeout(() => {
      setDemoState(recordingState, "ready-upload");
    }, 300);
    announce(
      "Session이 즉시 PROCESSING으로 전환됐습니다. 로컬 녹음은 별도로 upload에 인계합니다.",
    );
  }
});

document
  .querySelector("[data-publisher-switcher]")
  ?.addEventListener("click", (event) => {
    const state = event.target.closest("[data-state]")?.dataset.state;
    if (state === "conflict") {
      setDemoState(audioState, "error");
      announce(
        "두 번째 publisher의 Audio만 거부했습니다. 조회 기능은 그대로 유지합니다.",
      );
    }
  });

document
  .querySelector("[data-professor-question-switcher]")
  ?.addEventListener("click", (event) => {
    const nextState = event.target.closest("[data-state]")?.dataset.state;
    if (
      questionsPanel.dataset.fixtureApplied === "true" &&
      nextState !== "normal"
    ) {
      event.stopPropagation();
      setDemoState(questionsPanel, "normal");
      event.currentTarget
        .querySelectorAll("[data-state]")
        .forEach((button) =>
          button.setAttribute(
            "aria-pressed",
            String(button.dataset.state === "normal"),
          ),
        );
      observedQuestionState = "normal";
      showToast(
        "적용된 질문을 이전 fixture로 되돌릴 수 없습니다. 다른 상태는 새로고침해 확인해 주세요.",
        "info",
      );
      return;
    }
    if (nextState === "normal" && observedQuestionState !== "normal") {
      applyProfessorPendingQuestions();
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

document
  .querySelector("[data-material-upload]")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    const files = [...(materialInput.files || [])];
    if (files.length === 0) {
      setMaterialError("업로드할 PDF를 선택해 주세요.");
      return;
    }
    const remaining = 10 - updateMaterialCount();
    if (files.length > remaining) {
      setMaterialError(
        `남은 자리는 ${remaining}개입니다. 강의자료는 최대 10개까지 연결할 수 있습니다.`,
      );
      return;
    }
    const invalidType = files.find(
      (file) =>
        !file.name.toLowerCase().endsWith(".pdf") ||
        !["", "application/pdf"].includes(file.type),
    );
    if (invalidType) {
      setMaterialError(
        `${invalidType.name}: 내용과 형식이 유효한 PDF 파일만 업로드할 수 있습니다.`,
      );
      return;
    }
    const tooLarge = files.find((file) => file.size > 100_000_000);
    if (tooLarge) {
      setMaterialError(
        `${tooLarge.name}: PDF 한 개는 100 MB(100,000,000 bytes) 이하여야 합니다.`,
      );
      return;
    }
    setMaterialError("");
    files.forEach((file) => {
      const displayName = materialDisplayName(file.name);
      materialList.append(createMaterialRow(displayName));
    });
    materialInput.value = "";
    updateMaterialCount();
    showToast(
      `${files.length}개 PDF를 UPLOADED 상태로 추가했습니다.`,
      "success",
    );
  });

document
  .querySelector("[data-title-form]")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#classTitleInput");
    const title = normalizeLiveInput(input.value) || "서버 자동 제목 응답";
    document.querySelector("#classTitle").textContent = title;
    input.value = title;
    closeDialog(document.querySelector("#titleDialog"));
    showToast("class 제목을 저장했습니다.", "success");
  });

document
  .querySelector("[data-new-transcript]")
  ?.addEventListener("click", () => {
    transcriptStream?.lastElementChild?.scrollIntoView({ block: "end" });
    showToast("가장 최근 Transcript로 이동했습니다.", "info");
  });

if (["reconnecting", "resync"].includes(eventState?.dataset.demoState)) {
  removePartial("재연결 초기 상태에서 저장되지 않은 partial만 제거했습니다.");
}

applyMaterialFixture();
initializeAnswerFixture();

if (liveView?.dataset.demoState === "processing") {
  lockLiveControls();
  removePartial("PROCESSING 상태에서는 저장되지 않은 partial을 숨깁니다.");
}

if (new URLSearchParams(window.location.search).get("leave") === "warning") {
  openDialog(leaveDialog, document.querySelector("[data-leave-preview]"));
}
