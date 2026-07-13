import {
  closeDialog,
  openDialog,
  setDemoState,
  showToast,
} from "./prototype.js";

const sessionTarget = document.querySelector(
  "#currentSession, #studentCurrentSession",
);

const sessionHeroStates = {
  live: ["진행 중 class", "status-chip--live"],
  ready: ["시작 전 class", "status-chip--info"],
  processing: ["정리 중 class", "status-chip--warning"],
  none: ["active class 없음", "status-chip--info"],
  loading: ["class 확인 중", "status-chip--info"],
  error: ["class 상태 오류", "status-chip--danger"],
};

function syncSessionState(state = sessionTarget?.dataset.demoState) {
  if (!state) return;

  document.querySelectorAll("[data-session-hero-status]").forEach((status) => {
    const [label, tone] = sessionHeroStates[state] || sessionHeroStates.error;
    status.className = `status-chip ${tone}`;
    status.textContent = label;
  });

  const classActions = document.querySelector("#classActions");
  if (classActions) {
    setDemoState(
      classActions,
      state === "none"
        ? "available"
        : ["ready", "live", "processing"].includes(state)
          ? "limited"
          : "unknown",
    );
  }

  const courseDeleteAction = document.querySelector("#courseDeleteAction");
  if (courseDeleteAction) {
    setDemoState(
      courseDeleteAction,
      state === "none"
        ? "safe"
        : ["ready", "live", "processing"].includes(state)
          ? "blocked"
          : "unknown",
    );
  }
}

if (sessionTarget) {
  syncSessionState();
  new MutationObserver(() => syncSessionState()).observe(sessionTarget, {
    attributes: true,
    attributeFilter: ["data-demo-state"],
  });
}

const joinCode = document.querySelector("#professorJoinCode");
const joinCodeDialog = document.querySelector("#joinCodeRotateDialog");
const joinCodeFlow = document.querySelector("#joinCodeRotateFlow");
const rotatedCodes = ["QWERTY", "ZXCVBN", "ASDFGH"];
let nextCodeIndex = 0;

function setJoinCodeDialogLabel(state) {
  const dialog = joinCodeDialog?.querySelector('[role="dialog"]');
  if (!dialog) return;
  const error = state === "error";
  dialog.setAttribute(
    "aria-labelledby",
    error ? "joinCodeRotateErrorTitle" : "joinCodeRotateTitle",
  );
  dialog.setAttribute(
    "aria-describedby",
    error ? "joinCodeRotateErrorDescription" : "joinCodeRotateDescription",
  );
}

function focusJoinCodeState(state) {
  window.setTimeout(() => {
    const panel = joinCodeFlow?.querySelector(
      `[data-show-state="${state}"]:not([hidden])`,
    );
    const target =
      state === "error"
        ? panel?.querySelector("[data-join-code-retry]")
        : panel?.querySelector("[data-join-code-confirm]");
    target?.focus();
  }, 0);
}

document
  .querySelector("[data-join-code-rotate]")
  ?.addEventListener("click", (event) => {
    setJoinCodeDialogLabel("confirm");
    setDemoState(joinCodeFlow, "confirm");
    openDialog(joinCodeDialog, event.currentTarget);
  });

document
  .querySelector("[data-join-code-fail]")
  ?.addEventListener("click", () => {
    document.querySelectorAll("[data-join-code-current]").forEach((target) => {
      target.textContent = joinCode?.textContent.trim() || "ALGORT";
    });
    setJoinCodeDialogLabel("error");
    setDemoState(joinCodeFlow, "error");
    focusJoinCodeState("error");
    showToast("새 코드 발급에 실패해 기존 코드를 유지합니다.", "error");
  });

document
  .querySelector("[data-join-code-retry]")
  ?.addEventListener("click", () => {
    setJoinCodeDialogLabel("confirm");
    setDemoState(joinCodeFlow, "confirm");
    focusJoinCodeState("confirm");
  });

document
  .querySelector("[data-join-code-confirm]")
  ?.addEventListener("click", () => {
    if (!joinCode) return;
    const previousCode = joinCode.textContent.trim();
    let replacement = rotatedCodes[nextCodeIndex % rotatedCodes.length];
    nextCodeIndex += 1;
    if (replacement === previousCode) {
      replacement = rotatedCodes[nextCodeIndex % rotatedCodes.length];
      nextCodeIndex += 1;
    }
    joinCode.textContent = replacement;
    closeDialog(joinCodeDialog);
    showToast(
      `새 코드 ${replacement}를 발급했습니다. ${previousCode}는 즉시 무효이며 기존 학생은 그대로 참여합니다.`,
      "success",
    );
  });

let activeTitleTarget = null;
const titleDialog = document.querySelector("#titleEditDialog");
const titleInput = document.querySelector("#sessionTitleEdit");
const titleEditState = document.querySelector("[data-title-edit-state]");

function updateTitleControlNames(titleTarget) {
  const title = titleTarget.textContent.trim();
  const container = titleTarget.closest(
    "[data-session-row], .current-session__card",
  );
  if (!container) return;

  container.querySelectorAll("[data-title-edit]").forEach((button) => {
    button.setAttribute("aria-label", `${title} class 제목 수정`);
  });
  container.querySelectorAll("[data-session-delete]").forEach((button) => {
    button.setAttribute("aria-label", `${title} class 삭제`);
  });
  container.querySelectorAll("[data-session-record-link]").forEach((link) => {
    link.setAttribute(
      "aria-label",
      `${title} · ${link.dataset.dateLabel} 기록 열기`,
    );
  });
}

document
  .querySelectorAll("[data-session-title]")
  .forEach(updateTitleControlNames);

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-title-edit]");
  if (!trigger || !titleDialog || !titleInput) return;
  activeTitleTarget = document.getElementById(trigger.dataset.titleTarget);
  if (!activeTitleTarget) return;
  titleInput.value = activeTitleTarget.textContent.trim();
  if (titleEditState) titleEditState.textContent = trigger.dataset.sessionState;
  openDialog(titleDialog, trigger);
  window.setTimeout(() => {
    titleInput.focus();
    titleInput.select();
  }, 0);
});

document
  .querySelector("[data-title-edit-form]")
  ?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!activeTitleTarget || !titleInput) return;
    const nextTitle = titleInput.value.trim() || "자동 생성 제목 · 형식 미정";
    activeTitleTarget.textContent = nextTitle;
    updateTitleControlNames(activeTitleTarget);
    closeDialog(titleDialog);
    showToast("class 제목 목 응답을 반영했습니다.", "success");
    activeTitleTarget = null;
  });

let activeDeleteTrigger = null;
const sessionDeleteDialog = document.querySelector("#sessionDeleteDialog");

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-session-delete]");
  if (!trigger || !sessionDeleteDialog) return;
  if (!["READY", "COMPLETED"].includes(trigger.dataset.sessionState)) return;
  activeDeleteTrigger = trigger;
  const titleTarget = document.getElementById(trigger.dataset.titleTarget);
  document.querySelector("[data-session-delete-name]").textContent =
    titleTarget?.textContent.trim() || "선택한 class";
  document.querySelector("[data-session-delete-state]").textContent =
    trigger.dataset.sessionState;
  openDialog(sessionDeleteDialog, trigger);
});

document
  .querySelector("[data-session-delete-confirm]")
  ?.addEventListener("click", () => {
    if (!activeDeleteTrigger) return;
    const state = activeDeleteTrigger.dataset.sessionState;
    let focusFallback = null;
    if (state === "READY" && sessionTarget) {
      setDemoState(sessionTarget, "none");
      syncSessionState("none");
      focusFallback = document.querySelector("#currentSessionTitle");
    } else if (state === "COMPLETED") {
      const row = activeDeleteTrigger.closest("[data-session-row]");
      focusFallback =
        row?.nextElementSibling?.querySelector("a[href]") ||
        row?.previousElementSibling?.querySelector("a[href]") ||
        document.querySelector("#historyTitle");
      row?.remove();
      const count = document
        .querySelector("#historyTitle")
        ?.closest(".cluster")
        ?.querySelector(".badge");
      if (count)
        count.textContent = String(Math.max(0, Number(count.textContent) - 1));
    }
    closeDialog(sessionDeleteDialog);
    if (focusFallback) {
      if (!focusFallback.matches("a, button, input, select, textarea")) {
        focusFallback.tabIndex = -1;
      }
      focusFallback.focus();
    }
    showToast(`${state} class를 삭제한 목 결과입니다.`, "success");
    activeDeleteTrigger = null;
  });

const courseDeleteDialog = document.querySelector("#courseDeleteDialog");

document
  .querySelector("[data-course-delete]")
  ?.addEventListener("click", (event) => {
    if (sessionTarget?.dataset.demoState !== "none") {
      showToast(
        "active class 삭제 정책이 미정이라 Course를 삭제하지 않습니다.",
        "error",
      );
      return;
    }
    openDialog(courseDeleteDialog, event.currentTarget);
  });

document
  .querySelector("[data-course-delete-confirm]")
  ?.addEventListener("click", () => {
    if (sessionTarget?.dataset.demoState !== "none") {
      closeDialog(courseDeleteDialog);
      showToast(
        "current_session이 있어 Course를 삭제하지 않았습니다.",
        "error",
      );
      return;
    }
    window.location.assign(
      "dashboard.html?notice=active%20class가%20없는%20Course%20삭제%20목%20응답을%20확인했습니다.",
    );
  });
