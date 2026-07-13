import {
  closeDialog,
  openDialog,
  setDemoState,
  showToast,
} from "./prototype.js";

const MAX_MATERIAL_COUNT = 10;
const MAX_FILE_BYTES = 100_000_000;
const MATERIAL_COUNTS = {
  empty: 0,
  uploading: 1,
  processing: 2,
  mixed: 3,
  "all-ready": 2,
  failed: 1,
  full: 10,
  "size-error": null,
  "mime-error": null,
  "delete-conflict": null,
  "delete-missing": null,
  "load-error": null,
};

const classStage = document.querySelector("#classStage");
const sessionForm = document.querySelector("#sessionForm");
const sessionTitleForm = document.querySelector("#sessionTitleForm");
const readySessionTitle = document.querySelector("#readySessionTitle");
const sessionTitleOutputs = document.querySelectorAll("[data-session-title]");
const sessionDateOutput = document.querySelector("[data-session-date]");
const confirmSessionDelete = document.querySelector("#confirmSessionDelete");

const materialState = document.querySelector("#materialState");
const materialCountOutput = document.querySelector("[data-material-count]");
const fileInput = document.querySelector("#materialFiles");
const selectedList = document.querySelector("#selectedFiles");
const selectedWrap = document.querySelector("#selectedFilesWrap");
const uploadSelection = document.querySelector("#uploadSelection");
const fileError = document.querySelector("#materialFilesError");
const readiness = document.querySelector("[data-material-readiness]");
const readinessTitle = document.querySelector(
  "[data-material-readiness-title]",
);
const readinessCopy = document.querySelector("[data-material-readiness-copy]");
const startFlow = document.querySelector("#startFlow");
const startSessionButton = document.querySelector("#startSessionButton");
const materialDeleteDialog = document.querySelector("#materialDeleteDialog");
const materialDeleteName = document.querySelector(
  "[data-material-delete-name]",
);
const confirmMaterialDelete = document.querySelector("#confirmMaterialDelete");

let selectedFiles = [];
let activeMaterialCount = 0;
let pendingDeleteRow = null;
let pendingDeleteName = "";

function renderSessionTitle(value) {
  const normalized = value.trim();
  const title = normalized || "서버 자동 제목 응답";
  sessionTitleOutputs.forEach((output) => {
    output.textContent = title;
  });
  if (readySessionTitle) readySessionTitle.value = normalized;
  return title;
}

function renderSessionDate(value) {
  if (!sessionDateOutput || !value) return;
  const [year, month, day] = value.split("-").map(Number);
  sessionDateOutput.dateTime = value;
  sessionDateOutput.textContent = `${year}년 ${month}월 ${day}일`;
}

function setFileError(message = "") {
  if (!fileInput || !fileError) return;
  fileInput.setAttribute("aria-invalid", String(Boolean(message)));
  fileError.hidden = !message;
  fileError.textContent = message;
}

function renderSelectedFiles() {
  if (!selectedList || !selectedWrap || !uploadSelection) return;
  selectedList.replaceChildren();
  selectedWrap.hidden = selectedFiles.length === 0;
  uploadSelection.disabled = selectedFiles.length === 0;

  selectedFiles.forEach((file, index) => {
    const item = document.createElement("li");
    item.className = "material-item";
    item.dataset.materialState = "selected";
    item.innerHTML = `
      <span class="material-item__icon" aria-hidden="true">PDF</span>
      <div class="material-item__body">
        <strong></strong>
        <small>서버 수락 전 선택 파일 · 아직 업로드되지 않음</small>
        <div class="material-item__detail">
          <span class="material-status">선택됨</span>
        </div>
      </div>
      <div class="material-item__actions">
        <button class="button button--ghost" type="button">선택 취소</button>
      </div>`;
    item.querySelector("strong").textContent = file.name;
    const cancel = item.querySelector("button");
    cancel.setAttribute("aria-label", `${file.name} 선택 취소`);
    cancel.addEventListener("click", () => {
      selectedFiles = selectedFiles.filter(
        (_, fileIndex) => fileIndex !== index,
      );
      renderSelectedFiles();
      showToast(`${file.name} 선택을 취소했습니다.`, "info");
    });
    selectedList.append(item);
  });
}

function syncMaterialState(
  state = materialState?.dataset.demoState || "empty",
) {
  activeMaterialCount = MATERIAL_COUNTS[state] ?? activeMaterialCount;
  if (materialCountOutput) {
    materialCountOutput.textContent = String(activeMaterialCount);
  }

  const isFull = activeMaterialCount >= MAX_MATERIAL_COUNT;
  if (fileInput) fileInput.disabled = isFull;

  const blocksStart = state === "processing" || state === "mixed";
  if (startSessionButton) startSessionButton.disabled = blocksStart;
  if (readiness) readiness.dataset.ready = blocksStart ? "warning" : "true";
  if (readinessTitle) {
    readinessTitle.textContent = blocksStart
      ? "PROCESSING 자료로 시작 차단"
      : "자료 상태상 시작 가능";
  }
  if (readinessCopy) {
    readinessCopy.textContent = blocksStart
      ? "완료·실패를 기다리거나 해당 자료 삭제 필요"
      : "PDF 없음·UPLOADED·READY·FAILED는 시작 가능";
  }

  if (blocksStart) {
    setDemoState(startFlow, "material-processing");
  } else if (startFlow?.dataset.demoState === "material-processing") {
    setDemoState(startFlow, "idle");
  }
}

sessionForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const invalid = [...sessionForm.querySelectorAll("[required]")].filter(
    (field) => !field.value.trim(),
  );
  sessionForm.querySelectorAll("[required]").forEach((field) => {
    const isInvalid = invalid.includes(field);
    field.setAttribute("aria-invalid", String(isInvalid));
    const error = document.querySelector(
      `[data-field-error-for="${field.id}"]`,
    );
    if (error) error.hidden = !isInvalid;
  });
  if (invalid.length > 0) {
    invalid[0].focus();
    showToast("수업 날짜를 확인해주세요.", "error");
    return;
  }
  renderSessionTitle(sessionForm.elements.title.value);
  renderSessionDate(sessionForm.elements.lecture_date.value);
  setDemoState(classStage, "ready");
  showToast("READY class 생성 상태를 표시했습니다.", "success");
});

sessionTitleForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const title = renderSessionTitle(readySessionTitle.value);
  showToast(
    title === "서버 자동 제목 응답"
      ? "서버 자동 제목 응답 상태를 표시했습니다."
      : "class 제목 수정 상태를 표시했습니다.",
    "success",
  );
});

confirmSessionDelete?.addEventListener("click", () => {
  closeDialog(confirmSessionDelete.closest(".dialog-backdrop"));
  window.location.href =
    "course-professor.html?session=none&notice=READY+class+삭제+상태를+표시했습니다.&tone=success";
});

fileInput?.addEventListener("change", () => {
  const files = [...fileInput.files];
  const invalidType = files.find((file) => {
    const hasPdfName = file.name.toLowerCase().endsWith(".pdf");
    const hasPdfType =
      file.type === "application/pdf" || file.type.length === 0;
    return !hasPdfName || !hasPdfType;
  });
  const tooLarge = files.find((file) => file.size > MAX_FILE_BYTES);
  const remaining = MAX_MATERIAL_COUNT - activeMaterialCount;

  if (invalidType) {
    selectedFiles = [];
    fileInput.value = "";
    setFileError(
      `${invalidType.name}: 내용과 형식이 유효한 PDF 파일만 업로드할 수 있습니다.`,
    );
    setDemoState(materialState, "mime-error");
    syncMaterialState("mime-error");
    renderSelectedFiles();
    showToast("PDF가 아닌 파일은 보내지 않았습니다.", "error");
    return;
  }

  if (tooLarge) {
    selectedFiles = [];
    fileInput.value = "";
    setFileError(
      `${tooLarge.name}: PDF 한 개는 100 MB(100,000,000 bytes) 이하여야 합니다.`,
    );
    setDemoState(materialState, "size-error");
    syncMaterialState("size-error");
    renderSelectedFiles();
    showToast("용량을 초과한 파일은 보내지 않았습니다.", "error");
    return;
  }

  if (files.length > remaining) {
    selectedFiles = [];
    fileInput.value = "";
    setFileError(
      `남은 자리는 ${remaining}개입니다. 강의자료는 최대 10개까지 연결할 수 있습니다.`,
    );
    renderSelectedFiles();
    showToast("active 자료 개수 제한을 초과했습니다.", "error");
    return;
  }

  setFileError();
  selectedFiles = files;
  renderSelectedFiles();
});

uploadSelection?.addEventListener("click", () => {
  if (selectedFiles.length === 0) return;
  const count = selectedFiles.length;
  selectedFiles = [];
  fileInput.value = "";
  renderSelectedFiles();
  setDemoState(materialState, "uploading");
  syncMaterialState("uploading");
  showToast(`${count}개 파일의 개별 업로드 목 상태를 표시했습니다.`, "success");
});

document.addEventListener("click", (event) => {
  const materialStateButton = event.target.closest(
    '[data-state-switcher][data-state-target="#materialState"] [data-state]',
  );
  const materialStateAction = event.target.closest(
    '[data-state-action][data-state-target="#materialState"]',
  );
  const nextState =
    materialStateButton?.dataset.state || materialStateAction?.dataset.state;
  if (nextState) syncMaterialState(nextState);

  const deleteButton = event.target.closest("[data-material-delete]");
  if (deleteButton) {
    pendingDeleteRow = deleteButton.closest(".material-item");
    pendingDeleteName = deleteButton.dataset.materialDelete;
    if (materialDeleteName) materialDeleteName.textContent = pendingDeleteName;
    openDialog(materialDeleteDialog, deleteButton);
    return;
  }

  const retry = event.target.closest("[data-material-retry]");
  if (!retry) return;
  const item = retry.closest(".material-item");
  item.dataset.materialState = "processing";
  item.querySelector("[data-material-status]").textContent = "PROCESSING";
  item.querySelector("[data-material-attempt]").textContent = "attempt 2";
  retry.hidden = true;
  setDemoState(materialState, "processing");
  syncMaterialState("processing");
  showToast(
    `${retry.dataset.materialRetry} 처리 Job의 attempt를 2로 올렸습니다.`,
    "success",
  );
});

confirmMaterialDelete?.addEventListener("click", () => {
  pendingDeleteRow?.remove();
  activeMaterialCount = Math.max(0, activeMaterialCount - 1);
  if (materialCountOutput) {
    materialCountOutput.textContent = String(activeMaterialCount);
  }
  if (fileInput) fileInput.disabled = false;
  closeDialog(materialDeleteDialog);
  showToast(
    `${pendingDeleteName} 연결을 즉시 해제했습니다. 최신 목록을 다시 확인합니다.`,
    "success",
  );
  pendingDeleteRow = null;
  pendingDeleteName = "";
});

syncMaterialState();
