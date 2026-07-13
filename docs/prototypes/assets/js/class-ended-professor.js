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

  const existingNames = new Set(
    [...materialList.querySelectorAll("strong")].map((item) =>
      item.textContent.trim(),
    ),
  );
  const dot = file.name.lastIndexOf(".");
  const basename = dot > 0 ? file.name.slice(0, dot) : file.name;
  const extension = dot > 0 ? file.name.slice(dot) : "";
  let displayName = file.name;
  let suffix = 1;
  while (existingNames.has(displayName)) {
    displayName = `${basename} (${suffix})${extension}`;
    suffix += 1;
  }
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
    if (
      !window.confirm(
        "이 PDF를 목록·열람·새 AI 검색에서 즉시 분리할까요? 저장물 정리는 백그라운드에서 진행됩니다.",
      )
    ) {
      return;
    }
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
    const customTitle = input.value.trim();
    const nextTitle = customTitle || input.dataset.autoTitle;
    document.querySelector("#professorRecordTitle").textContent = nextTitle;
    input.value = nextTitle;
    closeDialog(document.querySelector("#titleEditDialog"));
    showToast(
      customTitle
        ? "class 제목을 수정했습니다. 기록 시각은 그대로입니다."
        : "빈 제목을 서버 자동 제목으로 되돌렸습니다. 기록 시각은 그대로입니다.",
      "success",
    );
  });

document
  .querySelector("#textAnswerForm")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    const targetSelect = document.querySelector("#textAnswerTarget");
    const selected = targetSelect.selectedOptions[0];
    const target = selected?.textContent.trim();
    const content = document.querySelector("#textAnswerInput").value.trim();
    if (!target || !content) return;

    const answer = document.createElement("article");
    answer.className = "record-answer";
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = `${selected.dataset.targetKind} snapshot · TEXT`;
    const title = document.createElement("h3");
    title.textContent = target;
    const label = document.createElement("strong");
    label.textContent = "교수자 답변";
    const copy = document.createElement("p");
    copy.dataset.professorAnswerText = "";
    copy.textContent = content;
    const edit = document.createElement("button");
    edit.className = "button button--ghost";
    edit.type = "button";
    edit.dataset.answerTextEdit = "";
    edit.textContent = "교수자 text 수정";
    answer.append(badge, title, label, copy, edit);

    const answerRegion = document.querySelector("#profAnswers");
    answerRegion.querySelector(".record-pagination")?.before(answer);
    const currentCount = answerRegion.querySelectorAll(".record-answer").length;
    document.querySelector("[data-answer-count]").textContent =
      `${currentCount} ANSWERS`;
    document.querySelector("[data-manifest-answers-jobs]").textContent =
      `${currentCount} / 7`;

    [...document.querySelectorAll("#profQuestions .record-question")]
      .find(
        (item) => item.querySelector("strong")?.textContent.trim() === target,
      )
      ?.querySelector(".badge")
      ?.replaceChildren("ANSWERED · TEXT Answer");
    selected.remove();
    document.querySelector("#textAnswerInput").value = "";
    if (targetSelect.options.length === 0) {
      document.querySelector('[data-dialog-open="textAnswerDialog"]').disabled =
        true;
    }
    closeDialog(document.querySelector("#textAnswerDialog"));
    showToast(`“${target}” 한 질문에 TEXT Answer를 저장했습니다.`, "success");
  });

updateMaterialCount();
initRecordCommon();
