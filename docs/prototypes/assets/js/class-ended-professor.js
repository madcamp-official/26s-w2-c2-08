import { initRecordCommon } from "./record-common.js";
import { closeDialog, setDemoState, showToast } from "./prototype.js";

const materialList = document.querySelector("[data-material-list]");
const materialInput = document.querySelector("#completedMaterialInput");

function updateMaterialCount() {
  const count =
    materialList?.querySelectorAll("[data-material-row]").length || 0;
  document.querySelectorAll("[data-material-count]").forEach((item) => {
    item.textContent = String(count);
  });
}

materialInput?.addEventListener("change", () => {
  const file = materialInput.files?.[0];
  if (!file) return;
  if (
    file.type !== "application/pdf" &&
    !file.name.toLowerCase().endsWith(".pdf")
  ) {
    showToast("PDF 파일만 업로드할 수 있습니다.", "error");
    materialInput.value = "";
    return;
  }
  if (file.size > 100000000) {
    showToast("PDF는 파일당 100 MB 이하여야 합니다.", "error");
    materialInput.value = "";
    return;
  }
  if (materialList.querySelectorAll("[data-material-row]").length >= 10) {
    showToast("이 class에는 PDF를 최대 10개까지 연결할 수 있습니다.", "error");
    materialInput.value = "";
    return;
  }

  const duplicate = [...materialList.querySelectorAll("strong")].some(
    (item) => item.textContent === file.name,
  );
  const dot = file.name.lastIndexOf(".");
  const displayName = duplicate
    ? `${file.name.slice(0, dot)} (1)${file.name.slice(dot)}`
    : file.name;
  const row = document.createElement("li");
  row.className = "record-material";
  row.dataset.materialRow = "";
  row.innerHTML = `<span class="material-item__icon">PDF</span><div><strong></strong><small>UPLOADED · 처리 대기 · 아직 AI 근거 아님</small></div><button class="button button--ghost" type="button" data-material-delete>삭제</button>`;
  row.querySelector("strong").textContent = displayName;
  materialList.append(row);
  updateMaterialCount();
  setDemoState(document.querySelector("#profMaterials"), "uploading");
  materialInput.value = "";
  showToast("PDF를 연결하고 background 처리를 시작했습니다.", "success");
});

document.addEventListener("click", (event) => {
  const materialDelete = event.target.closest("[data-material-delete]");
  const answerEdit = event.target.closest("[data-answer-text-edit]");
  if (materialDelete) {
    materialDelete.closest("[data-material-row]")?.remove();
    updateMaterialCount();
    setDemoState(document.querySelector("#profMaterials"), "deleting");
    showToast(
      "링크를 즉시 해제했습니다. 저장물은 background에서 정리합니다.",
      "success",
    );
  }
  if (answerEdit) {
    const card = answerEdit.closest(".record-answer");
    const current = card.querySelector("[data-professor-answer-text]");
    const next = window.prompt(
      "교수자 답변",
      current?.textContent.trim() || "",
    );
    if (next?.trim() && current) {
      current.textContent = next.trim();
      showToast(
        "교수자 text를 저장했습니다. AI 정리 결과는 덮어쓰지 않습니다.",
        "success",
      );
    }
  }
  if (event.target.closest("[data-class-delete-confirm]")) {
    closeDialog(document.querySelector("#classDeleteDialog"));
    showToast(
      "class 삭제 완료 후 Course 화면으로 이동하는 목 상태입니다.",
      "success",
    );
  }
});

document
  .querySelector("#titleEditForm")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#titleEditInput");
    if (!input.value.trim()) return;
    document.querySelector("#professorRecordTitle").textContent =
      input.value.trim();
    closeDialog(document.querySelector("#titleEditDialog"));
    showToast(
      "class 제목을 수정했습니다. 기록 시각은 그대로입니다.",
      "success",
    );
  });

document
  .querySelector("#textAnswerForm")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    const target = document.querySelector("#textAnswerTarget").value;
    const content = document.querySelector("#textAnswerInput").value.trim();
    if (!content) return;
    closeDialog(document.querySelector("#textAnswerDialog"));
    showToast(`“${target}” 한 질문에 TEXT Answer를 저장했습니다.`, "success");
  });

updateMaterialCount();
initRecordCommon();
