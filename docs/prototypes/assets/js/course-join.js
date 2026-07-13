import { setDemoState, showToast } from "./prototype.js";

const form = document.querySelector("[data-course-join-form]");
const input = document.querySelector("#joinCode");
const error = document.querySelector('[data-field-error-for="joinCode"]');

function normalizeJoinCode(value) {
  return value.trim().toUpperCase();
}

function setValidity(valid) {
  input.setAttribute("aria-invalid", String(!valid));
  error.hidden = valid;
}

if (form && input && error) {
  input.addEventListener("input", () => {
    const selectionStart = input.selectionStart ?? input.value.length;
    const previousLength = input.value.length;
    const normalized = normalizeJoinCode(input.value);
    input.value = normalized;
    const nextSelection = Math.max(
      0,
      selectionStart - (previousLength - normalized.length),
    );
    input.setSelectionRange(nextSelection, nextSelection);
    setValidity(true);
  });

  input.addEventListener("blur", () => {
    input.value = normalizeJoinCode(input.value);
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    input.value = normalizeJoinCode(input.value);

    if (!/^[A-Z]{6}$/.test(input.value)) {
      setValidity(false);
      input.focus();
      showToast("영문 대문자 6자리 참여 코드를 확인해주세요.", "error");
      return;
    }

    setValidity(true);
    const target = document.querySelector(form.dataset.stateTarget);
    setDemoState(target, form.dataset.successState || "success");
    showToast(
      form.dataset.successToast || "Course 참여 결과를 표시했습니다.",
      "success",
    );
  });
}
