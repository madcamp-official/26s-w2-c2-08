import { initRecordCommon } from "./record-common.js";
import { closeDialog, setDemoState, showToast } from "./prototype.js";

const materialList = document.querySelector("[data-material-list]");
const materialInput = document.querySelector("#completedMaterialInput");
const textAnswerInput = document.querySelector("#textAnswerInput");
const textAnswerError = document.querySelector("#textAnswerError");
const textAnswerCount = document.querySelector("[data-text-answer-count]");

const normalizeText = (value) => value.trim().normalize("NFC");
const codePointLength = (value) => [...value].length;

function validateText(input, error, count) {
  const normalized = normalizeText(input.value);
  const length = codePointLength(normalized);
  if (count) count.textContent = `${length} / 2,000자`;
  const message =
    length === 0
      ? "답변을 입력해 주세요."
      : length > 2000
        ? `2,000자 이하로 입력해 주세요. 현재 ${length}자입니다.`
        : "";
  input.setAttribute("aria-invalid", String(Boolean(message)));
  if (error) {
    error.textContent = message;
    error.hidden = !message;
  }
  return message ? null : normalized;
}

function createAnswerActions() {
  const actions = document.createElement("div");
  actions.className = "record-admin-actions";
  const edit = document.createElement("button");
  edit.className = "button button--ghost";
  edit.type = "button";
  edit.dataset.answerTextEdit = "";
  edit.textContent = "교수자 text 수정";
  const withdraw = document.createElement("button");
  withdraw.className = "button button--ghost";
  withdraw.type = "button";
  withdraw.dataset.answerTextWithdraw = "";
  withdraw.textContent = "교수자 text 철회";
  actions.append(edit, withdraw);
  return actions;
}

function startAnswerEdit(trigger) {
  const card = trigger.closest(".record-answer");
  const current = card?.querySelector("[data-professor-answer-text]");
  const actions = trigger.closest(".record-admin-actions");
  if (!card || !current || card.querySelector(".record-answer-edit-form")) {
    return;
  }

  const index = [...document.querySelectorAll(".record-answer")].indexOf(card);
  const form = document.createElement("form");
  form.className = "record-answer-edit-form";
  const label = document.createElement("label");
  label.htmlFor = `answerTextEdit${index}`;
  label.textContent = "교수자 답변 수정";
  const textarea = document.createElement("textarea");
  textarea.id = label.htmlFor;
  textarea.value = current.textContent.trim();
  const count = document.createElement("span");
  const error = document.createElement("p");
  error.hidden = true;
  error.setAttribute("role", "alert");
  const formActions = document.createElement("div");
  formActions.className = "record-admin-actions";
  const cancel = document.createElement("button");
  cancel.className = "button button--ghost";
  cancel.type = "button";
  cancel.textContent = "취소";
  const save = document.createElement("button");
  save.className = "button button--primary";
  save.type = "submit";
  save.textContent = "수정 저장";
  formActions.append(cancel, save);
  form.append(label, textarea, count, error, formActions);

  const closeEditor = () => {
    form.remove();
    current.hidden = false;
    if (actions) actions.hidden = false;
    trigger.focus();
  };
  textarea.addEventListener("input", () =>
    validateText(textarea, error, count),
  );
  cancel.addEventListener("click", closeEditor);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const next = validateText(textarea, error, count);
    if (!next) {
      textarea.focus();
      return;
    }
    current.textContent = next;
    closeEditor();
    showToast(
      "교수자 text를 저장했습니다. AI 정리 결과는 덮어쓰지 않습니다.",
      "success",
    );
  });

  current.hidden = true;
  if (actions) actions.hidden = true;
  card.append(form);
  validateText(textarea, error, count);
  textarea.focus();
}

function updateMaterialCount() {
  const count =
    materialList?.querySelectorAll("[data-material-row]").length || 0;
  document.querySelectorAll("[data-material-count]").forEach((item) => {
    item.textContent = String(count);
  });
}

materialInput?.addEventListener("change", () => {
  const files = [...(materialInput.files || [])];
  if (!files.length || !materialList) return;
  const existingNames = new Set(
    [...materialList.querySelectorAll("strong")].map((item) =>
      item.textContent.trim(),
    ),
  );
  let accepted = 0;
  let activeCount = materialList.querySelectorAll("[data-material-row]").length;

  files.forEach((file) => {
    if (activeCount >= 10) {
      showToast("10개를 넘는 파일은 요청하지 않았습니다.", "error");
      return;
    }
    if (
      file.type !== "application/pdf" &&
      !file.name.toLowerCase().endsWith(".pdf")
    ) {
      showToast(`${file.name}: PDF 파일만 업로드할 수 있습니다.`, "error");
      return;
    }
    if (file.size > 100000000) {
      showToast(`${file.name}: 파일당 100 MB 이하여야 합니다.`, "error");
      return;
    }

    const dot = file.name.lastIndexOf(".");
    const basename = dot > 0 ? file.name.slice(0, dot) : file.name;
    const extension = dot > 0 ? file.name.slice(dot) : "";
    let displayName = file.name;
    let suffix = 1;
    while (existingNames.has(displayName)) {
      displayName = `${basename} (${suffix})${extension}`;
      suffix += 1;
    }
    existingNames.add(displayName);
    const row = document.createElement("li");
    row.className = "record-material";
    row.dataset.materialRow = "";
    row.innerHTML = `<span class="material-item__icon">PDF</span><div><strong></strong><small>UPLOADED · 처리 대기 · 아직 AI 근거 아님</small></div><button class="button button--ghost" type="button" data-material-delete>삭제</button>`;
    row.querySelector("strong").textContent = displayName;
    materialList.append(row);
    activeCount += 1;
    accepted += 1;
  });

  if (accepted) {
    updateMaterialCount();
    setDemoState(document.querySelector("#profMaterials"), "uploading");
    showToast(
      `${accepted}개 PDF를 연결하고 파일별 background 처리를 시작했습니다.`,
      "success",
    );
  }
  materialInput.value = "";
});

document.addEventListener("click", (event) => {
  const materialDelete = event.target.closest("[data-material-delete]");
  const answerEdit = event.target.closest("[data-answer-text-edit]");
  const answerWithdraw = event.target.closest("[data-answer-text-withdraw]");
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
    startAnswerEdit(answerEdit);
  }
  if (answerWithdraw) {
    const card = answerWithdraw.closest(".record-answer");
    const current = card?.querySelector("[data-professor-answer-text]");
    if (current) {
      current.textContent = "교수자 text가 철회되었습니다.";
      answerWithdraw.closest(".record-admin-actions")?.remove();
      showToast(
        "교수자 text를 철회했습니다. 질문 snapshot과 AI 정리는 유지합니다.",
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
  if (event.target.closest("[data-recording-delete-confirm]")) {
    closeDialog(document.querySelector("#recordingDeleteDialog"));
    document.querySelector("[data-recording-player]").hidden = true;
    document.querySelector("[data-recording-seek-status]").hidden = true;
    document.querySelector(".recording-delete-control").hidden = true;
    document.querySelector("[data-recording-deleted]").hidden = false;
    document.querySelector("[data-recording-availability]").textContent =
      "RECORDING 조기 삭제";
    const heading = document.querySelector("#profRecordingTitle");
    heading.tabIndex = -1;
    heading.focus();
    showToast(
      "녹음을 삭제했습니다. Transcript·질문·답변은 유지합니다.",
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
    const content = validateText(
      textAnswerInput,
      textAnswerError,
      textAnswerCount,
    );
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
    answer.append(badge, title, label, copy, createAnswerActions());

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
    textAnswerInput.value = "";
    validateText(textAnswerInput, textAnswerError, textAnswerCount);
    if (targetSelect.options.length === 0) {
      targetSelect.disabled = true;
      textAnswerInput.disabled = true;
      event.currentTarget.querySelector('button[type="submit"]').disabled =
        true;
    }
    showToast(`“${target}” 한 질문에 TEXT Answer를 저장했습니다.`, "success");
  });

textAnswerInput?.addEventListener("input", () =>
  validateText(textAnswerInput, textAnswerError, textAnswerCount),
);
if (textAnswerInput) {
  textAnswerInput.setAttribute("aria-invalid", "false");
}
updateMaterialCount();
initRecordCommon();
