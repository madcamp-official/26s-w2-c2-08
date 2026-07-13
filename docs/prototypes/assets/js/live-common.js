import { setDemoState, showToast } from "./prototype.js";

export function normalizeLiveInput(value) {
  return value.trim().normalize("NFC");
}

export function codePointLength(value) {
  return [...normalizeLiveInput(value)].length;
}

function updateCounter(field) {
  const counter = document.querySelector(`[data-count-for="${field.id}"]`);
  const actual = codePointLength(field.value);
  if (counter) {
    counter.textContent = `${actual} / ${field.dataset.liveLimit}`;
    counter.dataset.overLimit = String(
      actual > Number(field.dataset.liveLimit),
    );
  }
  return actual;
}

export function validateLiveField(field, { focus = true } = {}) {
  if (!field) return false;
  const actual = updateCounter(field);
  const maximum = Number(field.dataset.liveLimit);
  const empty = actual === 0;
  const overLimit = actual > maximum;
  const invalid = empty || overLimit;
  const error = document.querySelector(`[data-limit-error-for="${field.id}"]`);

  field.setAttribute("aria-invalid", String(invalid));
  if (error) {
    error.hidden = !invalid;
    error.textContent = empty
      ? "공백이 아닌 내용을 입력해 주세요."
      : `최대 ${maximum.toLocaleString("ko-KR")}자까지 입력할 수 있습니다. 현재 ${actual.toLocaleString("ko-KR")}자입니다.`;
  }
  if (invalid && focus) field.focus();
  return !invalid;
}

function initLimitedFields(root) {
  root.querySelectorAll("[data-live-limit]").forEach((field) => {
    updateCounter(field);
    field.addEventListener("input", () => {
      const actual = updateCounter(field);
      if (field.getAttribute("aria-invalid") !== "true") return;
      const valid = actual > 0 && actual <= Number(field.dataset.liveLimit);
      if (valid) {
        field.setAttribute("aria-invalid", "false");
        const error = document.querySelector(
          `[data-limit-error-for="${field.id}"]`,
        );
        if (error) error.hidden = true;
      }
    });
  });
}

function setAttempt(container, selector) {
  const labels = container?.querySelectorAll(selector) || [];
  const current = Number(labels[0]?.dataset.attempt || "1");
  const next = current + 1;
  labels.forEach((label) => {
    label.dataset.attempt = String(next);
    label.textContent = `attempt ${next}`;
  });
}

function initLiveAi(root, announce) {
  const summary = root.querySelector("[data-live-summary-state]");
  const chat = root.querySelector("[data-live-chat-state]");
  const chatForm = root.querySelector("[data-live-chat-form]");
  const chatInput = root.querySelector("[data-live-chat-input]");

  root.addEventListener("click", (event) => {
    const summaryAction = event.target.closest("[data-live-summary-action]");
    const chatAction = event.target.closest("[data-live-chat-action]");

    if (summaryAction) {
      const action = summaryAction.dataset.liveSummaryAction;
      if (action === "retry") {
        setAttempt(summary, "[data-live-summary-attempt]");
        setDemoState(summary, "pending");
        announce("같은 LIVE_SUMMARY Job을 attempt + 1로 다시 요청했습니다.");
        return;
      }
      setDemoState(summary, action);
      const messages = {
        pending: "개인 LIVE Summary Job을 만들고 polling을 시작했습니다.",
        running: "개인 LIVE Summary Job이 실행 중입니다.",
        complete: "저장된 개인 LIVE Summary 결과를 불러왔습니다.",
        "not-ready":
          "확정된 live Transcript가 없어 Summary Job을 만들지 않았습니다.",
        error: "개인 LIVE Summary Job이 실패했습니다.",
      };
      announce(messages[action] || "Summary 상태를 변경했습니다.");
    }

    if (chatAction) {
      const action = chatAction.dataset.liveChatAction;
      if (action === "retry") {
        setAttempt(chat, "[data-live-chat-attempt]");
        setDemoState(chat, "pending");
        announce("동일 USER Message로 같은 CHAT_RESPONSE Job을 재시도합니다.");
        return;
      }
      setDemoState(chat, action);
      const messages = {
        evidence: "저장된 최종 Chat 답변과 Evidence를 불러왔습니다.",
        "no-evidence": "근거 없는 저장 완료 Chat 답변을 불러왔습니다.",
        error: "개인 Chat Job이 실패했습니다.",
      };
      announce(messages[action] || "Chat 상태를 변경했습니다.");
    }
  });

  chatForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!validateLiveField(chatInput)) return;
    setDemoState(chat, "pending");
    chatForm.setAttribute("aria-busy", "true");
    chatForm.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
    window.setTimeout(() => {
      chatForm.setAttribute("aria-busy", "false");
      chatForm.querySelectorAll("button").forEach((button) => {
        button.disabled = false;
      });
    }, 350);
    announce(
      "USER Message와 CHAT_RESPONSE Job을 함께 저장하고 requester-only polling을 시작했습니다.",
    );
  });
}

export function purgeLivePrivateAi(root = document) {
  root.querySelectorAll("[data-live-ai]").forEach((section) => {
    section.querySelectorAll("textarea").forEach((field) => {
      field.value = "";
      updateCounter(field);
    });
    section.dataset.livePurged = "true";
    section.querySelectorAll("[data-live-private-content]").forEach((item) => {
      item.hidden = true;
    });
    section.querySelectorAll("[data-live-private-purged]").forEach((item) => {
      item.hidden = false;
    });
  });
}

export function initLiveCommon({
  root = document,
  announcer = root.querySelector("[data-live-announcer]"),
} = {}) {
  const announce = (message) => {
    if (announcer) announcer.textContent = message;
  };

  initLimitedFields(root);
  root
    .querySelectorAll("[data-live-ai]")
    .forEach((section) => initLiveAi(section, announce));

  root.addEventListener("click", (event) => {
    const processing = event.target.closest("[data-live-processing]");
    if (!processing) return;
    purgeLivePrivateAi(root);
    announce(
      "Session이 PROCESSING으로 전환되어 개인 LIVE Summary·Chat과 선택 Job 정보를 삭제했습니다.",
    );
    showToast("개인 LIVE AI 데이터가 삭제되었습니다.", "info");
  });

  if (
    new URLSearchParams(window.location.search).get("view") === "processing"
  ) {
    purgeLivePrivateAi(root);
  }

  return { announce };
}
