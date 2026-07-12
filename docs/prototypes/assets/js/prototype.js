const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

let activeDialog = null;
let dialogTrigger = null;

export function showToast(message, tone = "info") {
  const region = document.querySelector("[data-toast-region]");
  if (!region) return;

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.dataset.tone = tone;
  toast.setAttribute("role", tone === "error" ? "alert" : "status");
  toast.textContent = message;
  region.replaceChildren(toast);

  window.setTimeout(() => {
    if (toast.isConnected) toast.remove();
  }, 3200);
}

function getFocusableElements(container) {
  return [...container.querySelectorAll(focusableSelector)].filter(
    (element) =>
      !element.hidden &&
      !element.closest("[hidden]") &&
      element.getAttribute("aria-hidden") !== "true",
  );
}

export function openDialog(dialog, trigger = document.activeElement) {
  if (!dialog) return;
  activeDialog = dialog;
  dialogTrigger = trigger;
  dialog.hidden = false;
  document.body.classList.add("is-locked");
  const [firstFocusable] = getFocusableElements(dialog);
  window.setTimeout(() => firstFocusable?.focus(), 0);
}

export function closeDialog(dialog = activeDialog) {
  if (!dialog) return;
  dialog.hidden = true;
  document.body.classList.remove("is-locked");
  activeDialog = null;
  const returnTarget = dialogTrigger;
  dialogTrigger = null;
  returnTarget?.focus();
}

function trapDialogFocus(event) {
  if (!activeDialog || event.key !== "Tab") return;
  const focusable = getFocusableElements(activeDialog);
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function initProfileDisclosure() {
  const trigger = document.querySelector("[data-profile-trigger]");
  const popover = document.querySelector("[data-profile-popover]");
  if (!trigger || !popover) return;

  const setOpen = (open) => {
    popover.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    if (open) popover.querySelector(focusableSelector)?.focus();
  };

  trigger.addEventListener("click", () => setOpen(popover.hidden));
  document.addEventListener("click", (event) => {
    if (
      !popover.hidden &&
      !popover.contains(event.target) &&
      !trigger.contains(event.target)
    ) {
      setOpen(false);
    }
  });
}

function getOwnedStateItems(target) {
  return [...target.querySelectorAll("[data-show-state]")].filter(
    (item) => item.closest("[data-demo-state]") === target,
  );
}

function initStateSwitchers() {
  document.querySelectorAll("[data-state-switcher]").forEach((switcher) => {
    const targetSelector = switcher.dataset.stateTarget;
    const target = targetSelector
      ? document.querySelector(targetSelector)
      : null;
    if (!target) return;

    switcher.addEventListener("click", (event) => {
      const button = event.target.closest("[data-state]");
      if (!button) return;
      const state = button.dataset.state;
      target.dataset.demoState = state;
      switcher.querySelectorAll("[data-state]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      getOwnedStateItems(target).forEach((item) => {
        const states = item.dataset.showState.split(" ");
        item.hidden = !states.includes(state);
      });
    });
  });
}

export function setDemoState(target, state) {
  if (!target || !state) return;
  target.dataset.demoState = state;
  getOwnedStateItems(target).forEach((item) => {
    const states = item.dataset.showState.split(" ");
    item.hidden = !states.includes(state);
  });

  if (!target.id) return;
  document
    .querySelectorAll(
      `[data-state-switcher][data-state-target="#${target.id}"]`,
    )
    .forEach((switcher) => {
      switcher.querySelectorAll("[data-state]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item.dataset.state === state));
      });
    });
}

function initDemoForms() {
  document.querySelectorAll("[data-demo-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const invalidFields = [...form.querySelectorAll("[required]")].filter(
        (field) => !field.value.trim(),
      );

      form.querySelectorAll("[required]").forEach((field) => {
        const invalid = invalidFields.includes(field);
        field.setAttribute("aria-invalid", String(invalid));
        const error = document.querySelector(
          `[data-field-error-for="${field.id}"]`,
        );
        if (error) error.hidden = !invalid;
      });

      if (invalidFields.length > 0) {
        invalidFields[0].focus();
        showToast("필수 입력을 확인해주세요.", "error");
        return;
      }

      const target = document.querySelector(form.dataset.stateTarget);
      setDemoState(target, form.dataset.successState || "success");
      showToast(
        form.dataset.successToast || "목 결과를 표시했습니다.",
        "success",
      );
    });

    form.addEventListener("input", (event) => {
      if (!event.target.matches("[required]")) return;
      event.target.setAttribute("aria-invalid", "false");
      const error = document.querySelector(
        `[data-field-error-for="${event.target.id}"]`,
      );
      if (error) error.hidden = true;
    });
  });
}

function initNormalizedInputs() {
  document.querySelectorAll("[data-uppercase-input]").forEach((input) => {
    input.addEventListener("input", () => {
      const start = input.selectionStart;
      input.value = input.value.toLocaleUpperCase("en-US");
      input.setSelectionRange(start, start);
    });
  });
}

function initCopyActions() {
  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-copy]");
    if (!trigger) return;
    const source = document.querySelector(trigger.dataset.copy);
    if (!source) return;
    const value = source.value || source.textContent.trim();

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const helper = document.createElement("textarea");
        helper.value = value;
        helper.setAttribute("aria-hidden", "true");
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.append(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
      }
      showToast(trigger.dataset.copySuccess || "복사했습니다.", "success");
    } catch {
      showToast("복사하지 못했습니다. 값을 직접 선택해주세요.", "error");
    }
  });
}

function initDisclosures() {
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-disclosure-trigger]");
    if (!trigger) return;
    const panel = document.getElementById(
      trigger.getAttribute("aria-controls"),
    );
    if (!panel) return;
    const open = trigger.getAttribute("aria-expanded") !== "true";
    trigger.setAttribute("aria-expanded", String(open));
    panel.hidden = !open;
  });
}

function initPressedGroups() {
  document.querySelectorAll("[data-pressed-group]").forEach((group) => {
    group.addEventListener("click", (event) => {
      const button = event.target.closest("button[aria-pressed]");
      if (!button || !group.contains(button)) return;
      group.querySelectorAll("button[aria-pressed]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
    });
  });
}

function initTranscriptRangeLinks() {
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-transcript-range-link]");
    if (!trigger) return;
    const target = document.querySelector(trigger.dataset.transcriptTarget);
    if (!target) return;
    const start = Number(trigger.dataset.startSequence);
    const end = Number(trigger.dataset.endSequence);
    target.querySelectorAll("[data-sequence]").forEach((segment) => {
      const sequence = Number(segment.dataset.sequence);
      segment.classList.toggle(
        "is-record-highlighted",
        sequence >= start && sequence <= end,
      );
    });
    const first = target.querySelector(`[data-sequence="${start}"]`);
    if (first) {
      first.tabIndex = -1;
      first.focus({ preventScroll: true });
      first.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    showToast(
      `Transcript sequence ${start}~${end} 범위를 표시했습니다.`,
      "info",
    );
  });
}

function initSharedJobRetries() {
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-shared-job-retry]");
    if (!trigger) return;
    const card = trigger.closest("[data-record-job]");
    if (!card) return;
    const attempt = card.querySelector("[data-job-attempt]");
    const nextAttempt = Number(attempt?.dataset.attempt || "1") + 1;
    if (attempt) {
      attempt.dataset.attempt = String(nextAttempt);
      attempt.textContent = `attempt ${nextAttempt}`;
    }
    card.dataset.jobStatus = "pending";
    card.querySelector("[data-job-status]").textContent = "PENDING";
    trigger.hidden = true;
    showToast(
      `${trigger.dataset.sharedJobRetry} 같은 Job을 재시도합니다.`,
      "success",
    );
  });
}

function initStateActions() {
  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-state-action]");
    if (!action) return;
    const target = document.querySelector(action.dataset.stateTarget);
    setDemoState(target, action.dataset.state);
  });
}

function initQueryStates() {
  const params = new URLSearchParams(window.location.search);
  document.querySelectorAll("[data-query-state]").forEach((target) => {
    const state =
      params.get(target.dataset.queryState) ||
      target.dataset.queryDefault ||
      "default";
    setDemoState(target, state);
  });
}

function initGreeting() {
  const greeting = document.querySelector("[data-greeting]");
  const date = document.querySelector("[data-today]");
  if (!greeting && !date) return;
  const now = new Date();
  const hour = now.getHours();
  const copy =
    hour < 12
      ? "좋은 오전이에요"
      : hour < 18
        ? "좋은 오후예요"
        : "좋은 저녁이에요";
  if (greeting) greeting.textContent = copy;
  if (date) {
    date.dateTime = now.toISOString().slice(0, 10);
    date.textContent = new Intl.DateTimeFormat("ko-KR", {
      year: "numeric",
      month: "long",
      day: "numeric",
      weekday: "long",
    }).format(now);
  }
}

function initCommonActions() {
  document.addEventListener("click", (event) => {
    const toastTrigger = event.target.closest("[data-toast]");
    const dialogOpen = event.target.closest("[data-dialog-open]");
    const dialogClose = event.target.closest("[data-dialog-close]");

    if (toastTrigger) {
      showToast(
        toastTrigger.dataset.toast,
        toastTrigger.dataset.toastTone || "info",
      );
    }

    if (dialogOpen) {
      openDialog(
        document.getElementById(dialogOpen.dataset.dialogOpen),
        dialogOpen,
      );
    }

    if (dialogClose) closeDialog(dialogClose.closest(".dialog-backdrop"));
    if (event.target.classList.contains("dialog-backdrop"))
      closeDialog(event.target);
  });

  document.addEventListener("keydown", (event) => {
    trapDialogFocus(event);
    if (event.key === "Escape") {
      if (activeDialog) closeDialog();
      const popover = document.querySelector("[data-profile-popover]");
      const trigger = document.querySelector("[data-profile-trigger]");
      if (popover && !popover.hidden) {
        popover.hidden = true;
        trigger?.setAttribute("aria-expanded", "false");
        trigger?.focus();
      }
    }
  });
}

function initQueryToast() {
  const params = new URLSearchParams(window.location.search);
  const message = params.get("notice");
  if (message) showToast(message, params.get("tone") || "success");
}

initProfileDisclosure();
initStateSwitchers();
initStateActions();
initQueryStates();
initDemoForms();
initNormalizedInputs();
initCopyActions();
initDisclosures();
initPressedGroups();
initTranscriptRangeLinks();
initSharedJobRetries();
initGreeting();
initCommonActions();
initQueryToast();
