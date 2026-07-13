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
  updated: 0,
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
const fileInputLabel = document.querySelector('label[for="materialFiles"]');
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
const fullMaterialList = document.querySelector("#fullMaterialList");
const fullMaterialIcon = document.querySelector("[data-full-material-icon]");
const fullMaterialHeading = document.querySelector(
  "[data-full-material-heading]",
);
const fullMaterialCopy = document.querySelector("[data-full-material-copy]");
const updatedMaterialList = document.querySelector("#updatedMaterialList");
const updatedStateButton = document.querySelector(
  '#materialState [data-state="updated"]',
);

let selectedFiles = [];
let activeMaterialCount = 0;
let materialBlocksStart = false;
let lastCanonicalMaterialState = "empty";
let selectionCapacityError = false;
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
      const remainingCancelButtons = [
        ...selectedList.querySelectorAll(".material-item button"),
      ];
      const focusFallback =
        remainingCancelButtons[
          Math.min(index, remainingCancelButtons.length - 1)
        ] ||
        (fileInput && !fileInput.disabled ? fileInput : null) ||
        document.querySelector("#materialsTitle");
      if (focusFallback) {
        if (!focusFallback.matches("button, input")) {
          focusFallback.tabIndex = -1;
        }
        focusFallback.focus();
      }
      showToast(`${file.name} 선택을 취소했습니다.`, "info");
    });
    selectedList.append(item);
  });
  syncSelectionCapacity();
}

function syncSelectionCapacity() {
  if (!uploadSelection) return true;
  const remaining = MAX_MATERIAL_COUNT - activeMaterialCount;
  const exceedsCapacity = selectedFiles.length > remaining;
  uploadSelection.disabled =
    selectedFiles.length === 0 || exceedsCapacity || remaining === 0;

  if (exceedsCapacity) {
    selectionCapacityError = true;
    setFileError(
      `남은 자리는 ${remaining}개입니다. 현재 선택을 줄인 뒤 다시 요청해 주세요.`,
    );
  } else if (selectionCapacityError) {
    selectionCapacityError = false;
    setFileError();
  }
  return !exceedsCapacity;
}

function renderFullMaterialFixture() {
  if (!fullMaterialList || fullMaterialList.children.length > 0) return;

  for (let index = 0; index < MAX_MATERIAL_COUNT; index += 1) {
    const suffix = index === 0 ? "" : ` (${index})`;
    const name = `강의자료${suffix}.pdf`;
    const item = document.createElement("li");
    item.className = "material-item";
    item.dataset.materialState = "ready";
    item.innerHTML = `
      <span class="material-item__icon" aria-hidden="true">PDF</span>
      <div class="material-item__body">
        <strong></strong>
        <small>${12 + index * 3}페이지 · 검색 준비 완료</small>
        <div class="material-item__detail">
          <span class="material-status">READY</span>
          <span class="material-attempt">attempt 1</span>
        </div>
      </div>
      <div class="material-item__actions">
        <button class="button button--ghost" type="button">원본 열기</button>
        <button class="button button--danger" type="button">삭제</button>
      </div>`;
    item.querySelector("strong").textContent = name;
    const [openButton, deleteButton] = item.querySelectorAll("button");
    openButton.dataset.toast = `${name} 권한 확인 원본 열기 상태를 표시했습니다.`;
    openButton.setAttribute("aria-label", `${name} 권한 확인 후 원본 열기`);
    deleteButton.dataset.materialDelete = name;
    deleteButton.setAttribute("aria-label", `${name} 삭제`);
    fullMaterialList.append(item);
  }
}

function getMaterialPanelsForState(state) {
  if (!materialState) return [];
  return [...materialState.querySelectorAll("[data-show-state]")].filter(
    (panel) =>
      panel.closest("[data-demo-state]") === materialState &&
      panel.dataset.showState.split(" ").includes(state),
  );
}

function getMaterialRowsForState(state) {
  return getMaterialPanelsForState(state).flatMap((panel) => [
    ...panel.querySelectorAll(".material-item"),
  ]);
}

function uniqueMaterialName(fileName, list) {
  const names = new Set(
    [...list.querySelectorAll(".material-item strong")].map((item) =>
      item.textContent.trim(),
    ),
  );
  if (!names.has(fileName)) return fileName;

  const extensionIndex = fileName.toLowerCase().lastIndexOf(".pdf");
  const basename =
    extensionIndex === -1 ? fileName : fileName.slice(0, extensionIndex);
  const extension = extensionIndex === -1 ? "" : fileName.slice(extensionIndex);
  let suffix = 1;
  while (names.has(`${basename} (${suffix})${extension}`)) suffix += 1;
  return `${basename} (${suffix})${extension}`;
}

function createUploadedMaterialRow(fileName, list) {
  const name = uniqueMaterialName(fileName, list);
  const item = document.createElement("li");
  item.className = "material-item";
  item.dataset.materialState = "uploaded";
  item.innerHTML = `
    <span class="material-item__icon" aria-hidden="true">PDF</span>
    <div class="material-item__body">
      <strong></strong>
      <small>202 Accepted · 기존 자료와 별개로 처리 대기 중</small>
      <div class="material-item__detail">
        <span class="material-status">UPLOADED</span>
        <span class="material-attempt">attempt 1</span>
      </div>
    </div>
    <div class="material-item__actions">
      <button class="button button--ghost" type="button">원본 열기</button>
      <button class="button button--danger" type="button">삭제</button>
    </div>`;
  item.querySelector("strong").textContent = name;
  const [openButton, deleteButton] = item.querySelectorAll("button");
  openButton.dataset.toast = `${name} 권한 확인 원본 열기 상태를 표시했습니다.`;
  openButton.setAttribute("aria-label", `${name} 권한 확인 후 원본 열기`);
  deleteButton.dataset.materialDelete = name;
  deleteButton.setAttribute("aria-label", `${name} 삭제`);
  return item;
}

function renderUpdatedMaterialState(files) {
  if (!updatedMaterialList) return;
  const retainedRows = getMaterialRowsForState(lastCanonicalMaterialState).map(
    (row) => row.cloneNode(true),
  );
  updatedMaterialList.replaceChildren(...retainedRows);
  files.forEach((file) => {
    updatedMaterialList.append(
      createUploadedMaterialRow(file.name, updatedMaterialList),
    );
  });

  MATERIAL_COUNTS.updated = Math.min(
    MAX_MATERIAL_COUNT,
    activeMaterialCount + files.length,
  );
  if (updatedStateButton) updatedStateButton.hidden = false;
  setDemoState(materialState, "updated");
  syncMaterialState("updated");
}

function syncFullMaterialCopy() {
  if (!fullMaterialList) return;
  const count = fullMaterialList.querySelectorAll(".material-item").length;
  fullMaterialList.setAttribute("aria-label", `${count}개가 연결된 PDF 목록`);
  if (fullMaterialIcon) fullMaterialIcon.textContent = String(count);
  if (fullMaterialHeading) {
    fullMaterialHeading.textContent = `강의자료 ${count}/10개가 연결되어 있습니다`;
  }
  if (fullMaterialCopy) {
    fullMaterialCopy.textContent =
      count >= MAX_MATERIAL_COUNT
        ? "409 MATERIAL_LIMIT_EXCEEDED · UPLOADED, PROCESSING, READY, FAILED를 모두 active 개수에 포함합니다. 기존 자료를 삭제해야 새 PDF를 선택할 수 있습니다."
        : `삭제 결과를 반영해 ${MAX_MATERIAL_COUNT - count}개를 더 연결할 수 있습니다. 남은 자료의 이름과 상태는 그대로 유지합니다.`;
  }
}

function syncStartAvailability(blocksStart) {
  materialBlocksStart = blocksStart;
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

  startFlow
    ?.querySelectorAll(
      '[data-state-switcher][data-state-target="#startFlow"] [data-state]',
    )
    .forEach((button) => {
      const isMaterialProcessing =
        button.dataset.state === "material-processing";
      button.disabled = blocksStart
        ? !isMaterialProcessing
        : isMaterialProcessing;
    });

  if (blocksStart) {
    setDemoState(startFlow, "material-processing");
  } else if (startFlow?.dataset.demoState === "material-processing") {
    setDemoState(startFlow, "idle");
  }
}

function currentMaterialBlocksStart() {
  if (!materialState) return false;
  const state = materialState.dataset.demoState;
  return getMaterialPanelsForState(state)
    .filter((panel) => !panel.hidden)
    .some((panel) => panel.querySelector('[data-material-state="processing"]'));
}

function syncMaterialState(
  state = materialState?.dataset.demoState || "empty",
) {
  const fixtureCount = MATERIAL_COUNTS[state];
  activeMaterialCount = fixtureCount ?? activeMaterialCount;
  if (fixtureCount !== null && fixtureCount !== undefined) {
    lastCanonicalMaterialState = state;
  }
  if (materialCountOutput) {
    materialCountOutput.textContent = String(activeMaterialCount);
  }

  const isFull = activeMaterialCount >= MAX_MATERIAL_COUNT;
  if (fileInput) fileInput.disabled = isFull;
  if (fileInputLabel) {
    fileInputLabel.setAttribute("aria-disabled", String(isFull));
  }
  syncSelectionCapacity();
  syncFullMaterialCopy();
  syncStartAvailability(
    fixtureCount === null ? materialBlocksStart : currentMaterialBlocksStart(),
  );
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
  const readyHeading = document.querySelector("#sessionSummaryTitle");
  if (readyHeading) {
    readyHeading.tabIndex = -1;
    readyHeading.focus();
  }
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
    selectionCapacityError = false;
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
    selectionCapacityError = false;
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
    selectionCapacityError = false;
    fileInput.value = "";
    setFileError(
      `남은 자리는 ${remaining}개입니다. 강의자료는 최대 10개까지 연결할 수 있습니다.`,
    );
    renderSelectedFiles();
    showToast("active 자료 개수 제한을 초과했습니다.", "error");
    return;
  }

  setFileError();
  selectionCapacityError = false;
  selectedFiles = files;
  renderSelectedFiles();
  syncSelectionCapacity();
});

uploadSelection?.addEventListener("click", () => {
  if (selectedFiles.length === 0) return;
  if (!syncSelectionCapacity()) {
    showToast("현재 남은 active 자료 자리를 다시 확인해 주세요.", "error");
    return;
  }
  const files = [...selectedFiles];
  const count = files.length;
  selectedFiles = [];
  fileInput.value = "";
  renderSelectedFiles();
  renderUpdatedMaterialState(files);
  const materialsHeading = document.querySelector("#materialsTitle");
  if (materialsHeading) {
    materialsHeading.tabIndex = -1;
    materialsHeading.focus();
  }
  showToast(
    `${count}개 파일의 개별 202 Accepted 목 상태를 기존 목록에 반영했습니다.`,
    "success",
  );
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
  item.setAttribute("aria-busy", "true");
  const description = item.querySelector(".material-item__body > small");
  if (description) {
    description.textContent =
      "같은 Material 처리 Job 행에서 재시도 중 · 기존 결과는 아직 사용할 수 없음";
  }
  item.querySelector("[data-material-status]").textContent = "PROCESSING";
  item.querySelector("[data-material-attempt]").textContent = "attempt 2";
  retry.hidden = true;
  syncStartAvailability(currentMaterialBlocksStart());
  const materialsHeading = document.querySelector("#materialsTitle");
  if (materialsHeading) {
    materialsHeading.tabIndex = -1;
    materialsHeading.focus();
  }
  showToast(
    `${retry.dataset.materialRetry} 처리 Job의 attempt를 2로 올렸습니다.`,
    "success",
  );
});

confirmMaterialDelete?.addEventListener("click", () => {
  const row = pendingDeleteRow;
  const focusFallback =
    row?.nextElementSibling?.querySelector("button, a[href]") ||
    row?.previousElementSibling?.querySelector("button, a[href]") ||
    document.querySelector("#materialsTitle");
  pendingDeleteRow?.remove();
  activeMaterialCount = Math.max(0, activeMaterialCount - 1);
  const currentState = materialState?.dataset.demoState;
  if (currentState && MATERIAL_COUNTS[currentState] !== null) {
    MATERIAL_COUNTS[currentState] = activeMaterialCount;
  }
  if (materialCountOutput) {
    materialCountOutput.textContent = String(activeMaterialCount);
  }
  if (fileInput) fileInput.disabled = false;
  if (fileInputLabel) fileInputLabel.setAttribute("aria-disabled", "false");
  syncSelectionCapacity();
  syncFullMaterialCopy();
  syncStartAvailability(currentMaterialBlocksStart());
  closeDialog(materialDeleteDialog);
  if (focusFallback) {
    if (!focusFallback.matches("a, button, input, select, textarea")) {
      focusFallback.tabIndex = -1;
    }
    focusFallback.focus();
  }
  showToast(
    `${pendingDeleteName} 연결을 즉시 해제했습니다. 최신 목록을 다시 확인합니다.`,
    "success",
  );
  pendingDeleteRow = null;
  pendingDeleteName = "";
});

renderFullMaterialFixture();
syncMaterialState();
