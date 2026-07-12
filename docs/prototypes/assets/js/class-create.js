import { setDemoState, showToast } from "./prototype.js";

const classStage = document.querySelector("#classStage");
const sessionForm = document.querySelector("#sessionForm");
const fileInput = document.querySelector("#materialFiles");
const selectedList = document.querySelector("#selectedFiles");
const selectedWrap = document.querySelector("#selectedFilesWrap");
const uploadSelection = document.querySelector("#uploadSelection");
const fileError = document.querySelector("#materialFilesError");
const materialState = document.querySelector("#materialState");

let selectedFiles = [];

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
    showToast("class 제목과 날짜를 확인해주세요.", "error");
    return;
  }
  setDemoState(classStage, "ready");
  showToast("READY class 생성 상태를 표시했습니다.", "success");
});

fileInput?.addEventListener("change", () => {
  const files = [...fileInput.files];
  const invalid = files.filter(
    (file) =>
      file.type !== "application/pdf" &&
      !file.name.toLowerCase().endsWith(".pdf"),
  );
  if (invalid.length > 0) {
    fileInput.setAttribute("aria-invalid", "true");
    fileError.hidden = false;
    fileError.textContent = `${invalid[0].name}: PDF 파일만 선택할 수 있습니다.`;
    showToast("PDF가 아닌 선택 파일을 제외했습니다.", "error");
  } else {
    fileInput.setAttribute("aria-invalid", "false");
    fileError.hidden = true;
  }
  selectedFiles = files.filter((file) => !invalid.includes(file));
  renderSelectedFiles();
});

uploadSelection?.addEventListener("click", () => {
  if (selectedFiles.length === 0) return;
  const count = selectedFiles.length;
  selectedFiles = [];
  fileInput.value = "";
  renderSelectedFiles();
  setDemoState(materialState, "uploading");
  showToast(`${count}개 파일의 개별 업로드 목 상태를 표시했습니다.`, "success");
});

document.addEventListener("click", (event) => {
  const retry = event.target.closest("[data-material-retry]");
  if (!retry) return;
  const item = retry.closest(".material-item");
  item.dataset.materialState = "processing";
  item.querySelector("[data-material-status]").textContent = "PROCESSING";
  item.querySelector("[data-material-attempt]").textContent = "attempt 2";
  retry.hidden = true;
  showToast(
    `${retry.dataset.materialRetry} 처리 Job의 attempt를 2로 올렸습니다.`,
    "success",
  );
});
