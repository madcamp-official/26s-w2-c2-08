import {
  closeDialog,
  openDialog,
  setDemoState,
  showToast,
} from "./prototype.js";
import { initLiveCommon, normalizeLiveInput } from "./live-common.js";

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

const { announce } = initLiveCommon({ announcer: announcement });

let activeAnswer = null;
let partialRevision = 2;
let pendingMaterialRow = null;
let endingSession = false;

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
}

function updateTargetStatus(target, status) {
  if (!target) return;
  target.dataset.answerTargetStatus = status;
  const label = target.querySelector("[data-answer-status-label]");
  if (label) label.textContent = status.toUpperCase();
}

function latestFinalSequence() {
  return Math.max(
    0,
    ...[...document.querySelectorAll('[data-transcript-kind="final"]')].map(
      (item) => Number(item.dataset.sequence || 0),
    ),
  );
}

function startAnswer(button) {
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
  const { target } = activeAnswer;
  updateTargetStatus(target, "open");
  document
    .querySelectorAll('[data-transcript-kind="candidate"]')
    .forEach((item) => (item.dataset.transcriptKind = "final"));
  activeAnswer = null;
  setDemoState(answerState, "idle");
  setAnswerControlsDisabled(false);
  target.querySelector("[data-answer-select]")?.focus();
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
  return (
    !endingSession &&
    publisherState?.dataset.demoState === "active" &&
    recordingState?.dataset.demoState === "recording"
  );
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
  while (names.has(`${stem}(${suffix})${extension}`)) suffix += 1;
  return `${stem}(${suffix})${extension}`;
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
  row.append(copy, remove);
  return row;
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
  updateMaterialCount();
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
  const answerComplete = event.target.closest("[data-answer-complete]");
  const answerCancel = event.target.closest("[data-answer-cancel]");
  const materialDelete = event.target.closest("[data-material-delete]");
  const materialDeleteConfirm = event.target.closest(
    "[data-material-delete-confirm]",
  );
  const materialRetry = event.target.closest("[data-material-retry]");
  const leavePreview = event.target.closest("[data-leave-preview]");
  const endOpen = event.target.closest("[data-end-open]");
  const endConfirm = event.target.closest("[data-end-confirm]");

  if (publisherStart) {
    setDemoState(publisherState, "active");
    setDemoState(audioState, "permission");
    announce("첫 audio.start가 성공해 이 탭이 active publisher가 됐습니다.");
  }
  if (micRequest) {
    if (publisherState.dataset.demoState === "conflict") {
      showToast(
        "다른 publisher가 전송 중이라 Audio만 시작할 수 없습니다.",
        "error",
      );
    } else {
      setDemoState(publisherState, "active");
      setDemoState(audioState, "connecting");
      announce("마이크 권한 목 응답을 기다립니다.");
    }
  }
  if (micAllow) {
    setDemoState(publisherState, "active");
    setDemoState(audioState, "listening");
    setDemoState(recordingState, "recording");
    setDemoState(sttState, "listening");
    announce("한 마이크 입력을 실시간 PCM과 로컬 녹음으로 분기했습니다.");
  }
  if (micDeny) {
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
    showToast("같은 Material 행의 attempt를 증가해 재시도합니다.", "success");
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
    endingSession = true;
    setDemoState(endFlow, "processing");
    setDemoState(eventState, "stopped");
    setDemoState(recordingState, "finalizing");
    questionsPanel.dataset.clusteringFenced = "true";
    document
      .querySelectorAll(
        "#liveView [data-show-state='normal'] input, #liveView [data-show-state='normal'] textarea, #liveView [data-show-state='normal'] button",
      )
      .forEach((control) => (control.disabled = true));
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
  .querySelector("[data-material-upload]")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    const file = materialInput.files?.[0];
    if (!file) {
      setMaterialError("업로드할 PDF를 선택해 주세요.");
      return;
    }
    if (updateMaterialCount() >= 10) {
      setMaterialError(
        "강의자료는 최대 10개까지 연결할 수 있습니다. 기존 자료를 삭제해 주세요.",
      );
      return;
    }
    const pdf =
      file.type === "application/pdf" ||
      file.name.toLowerCase().endsWith(".pdf");
    if (!pdf) {
      setMaterialError("내용과 형식이 유효한 PDF 파일만 업로드할 수 있습니다.");
      return;
    }
    if (file.size > 100_000_000) {
      setMaterialError(
        "PDF 한 개는 100 MB(100,000,000 bytes) 이하여야 합니다.",
      );
      return;
    }
    setMaterialError("");
    const displayName = materialDisplayName(file.name);
    materialList.append(createMaterialRow(displayName));
    materialInput.value = "";
    updateMaterialCount();
    showToast(`${displayName}을 UPLOADED 상태로 추가했습니다.`, "success");
  });

document
  .querySelector("[data-title-form]")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#classTitleInput");
    const title =
      normalizeLiveInput(input.value) ||
      "2026년 7월 12일 14:00의 알고리즘 class";
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

if (isCapturing()) setAnswerControlsDisabled(true);
applyMaterialFixture();

if (new URLSearchParams(window.location.search).get("leave") === "warning") {
  openDialog(leaveDialog, document.querySelector("[data-leave-preview]"));
}
