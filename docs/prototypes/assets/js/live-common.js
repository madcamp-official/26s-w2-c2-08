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

function moveFocusToState(container) {
  if (!container) return;
  container.tabIndex = -1;
  container.focus();
}

function setChatLocked(form, locked) {
  if (!form) return;
  form.setAttribute("aria-busy", String(locked));
  form.querySelectorAll("textarea, button").forEach((control) => {
    control.disabled = locked;
  });
}

function hasLiveSummarySource() {
  const transcript = document.querySelector('[data-query-state="transcript"]');
  return transcript?.dataset.demoState !== "empty";
}

function clearPrivateResultCache(section) {
  section.querySelectorAll("[data-live-chat-snapshot]").forEach((item) => {
    item.textContent = "";
  });
  section
    .querySelectorAll(
      '[data-live-summary-state] [data-show-state="complete"], [data-live-chat-state] [data-show-state="evidence"], [data-live-chat-state] [data-show-state="no-evidence"]',
    )
    .forEach((item) => item.replaceChildren());
}

function sortQuestionPriority(section, sort) {
  const list = section.querySelector("[data-question-priority-list]");
  if (!list) return;
  const items = [...list.querySelectorAll("[data-question-priority-item]")];
  items.sort((left, right) => {
    const recentDelta =
      Number(right.dataset.createdOrder) - Number(left.dataset.createdOrder);
    const idDelta = (right.dataset.questionId || "").localeCompare(
      left.dataset.questionId || "",
    );
    if (sort === "RECENT") return recentDelta || idDelta;
    const reactionDelta =
      Number(right.dataset.reactionCount) - Number(left.dataset.reactionCount);
    return reactionDelta || recentDelta || idDelta;
  });
  items.forEach((item) => list.append(item));
  section.dataset.questionSort = sort;
  section.querySelectorAll("[data-question-sort]").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.questionSort === sort),
    );
  });
  const description = section.querySelector("[data-question-sort-description]");
  if (description) {
    description.textContent =
      sort === "POPULAR"
        ? "인기순 · reaction_count DESC, created_at DESC, id DESC"
        : "최신순 · created_at DESC, id DESC";
  }
}

export function refreshQuestionPriority(root = document) {
  root.querySelectorAll("[data-question-priority]").forEach((section) => {
    sortQuestionPriority(section, section.dataset.questionSort || "POPULAR");
  });
}

function initQuestionPriority(root, announce) {
  refreshQuestionPriority(root);
  root.addEventListener("click", (event) => {
    const action = event.target.closest("[data-question-sort]");
    if (!action) return;
    const section = action.closest("[data-question-priority]");
    sortQuestionPriority(section, action.dataset.questionSort);
    announce(
      `${action.dataset.questionSort} 정렬을 전체 질문 목록에만 적용했습니다. Cluster membership 순서는 바꾸지 않습니다.`,
    );
  });
}

function initLiveAi(root, announce) {
  const summary = root.querySelector("[data-live-summary-state]");
  const chat = root.querySelector("[data-live-chat-state]");
  const chatForm = root.querySelector("[data-live-chat-form]");
  const chatInput = root.querySelector("[data-live-chat-input]");

  if (chat) {
    chat.setAttribute("role", "log");
    chat.setAttribute("aria-label", "개인 AI 대화와 처리 상태");
  }
  if (chat?.dataset.demoState === "pending") setChatLocked(chatForm, true);
  if (summary && !hasLiveSummarySource()) {
    setDemoState(summary, "not-ready");
  }

  root.addEventListener("click", (event) => {
    const evidenceLink = event.target.closest("a.live-evidence-link");
    const summaryAction = event.target.closest("[data-live-summary-action]");
    const chatAction = event.target.closest("[data-live-chat-action]");

    if (evidenceLink) {
      event.preventDefault();
      announce(
        "정적 Prototype에서는 Evidence 권한을 재검사한 뒤 안정적인 공개 link로 이동하는 동작만 모의합니다.",
      );
      showToast("Evidence 공개 link 이동을 모의했습니다.", "info");
      return;
    }

    if (summaryAction) {
      const action = summaryAction.dataset.liveSummaryAction;
      if (action !== "not-ready" && !hasLiveSummarySource()) {
        setDemoState(summary, "not-ready");
        moveFocusToState(summary);
        announce(
          "확정된 live Transcript가 0건이라 Summary Job 없이 409 SUMMARY_TRANSCRIPT_NOT_READY로 거부했습니다.",
        );
        return;
      }
      if (action === "retry") {
        setAttempt(summary, "[data-live-summary-attempt]");
        setDemoState(summary, "pending");
        moveFocusToState(summary);
        announce("같은 LIVE_SUMMARY Job을 attempt + 1로 다시 요청했습니다.");
        return;
      }
      setDemoState(summary, action);
      if (action === "pending") moveFocusToState(summary);
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
        setChatLocked(chatForm, true);
        moveFocusToState(chat);
        announce("동일 USER Message로 같은 CHAT_RESPONSE Job을 재시도합니다.");
        return;
      }
      setDemoState(chat, action);
      if (["evidence", "no-evidence", "error"].includes(action)) {
        setChatLocked(chatForm, false);
      }
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
    const snapshot = normalizeLiveInput(chatInput.value);
    root.querySelectorAll("[data-live-chat-snapshot]").forEach((item) => {
      item.textContent = snapshot;
    });
    root.dataset.activeChatMessage = snapshot;
    root.dataset.activeChatJob = "job-live-chat-demo";
    setDemoState(chat, "pending");
    setChatLocked(chatForm, true);
    moveFocusToState(chat);
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
    delete section.dataset.activeChatMessage;
    delete section.dataset.activeChatJob;
    clearPrivateResultCache(section);
    section.querySelectorAll("[data-live-summary-state]").forEach((state) => {
      state.dataset.demoState = "purged";
      delete state.dataset.selectedJobId;
    });
    section.querySelectorAll("[data-live-chat-state]").forEach((state) => {
      state.dataset.demoState = "purged";
      delete state.dataset.selectedJobId;
      delete state.dataset.selectedChatId;
    });
    section
      .querySelectorAll("button, textarea, input")
      .forEach((control) => (control.disabled = true));
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
  initQuestionPriority(root, announce);
  root
    .querySelectorAll("[data-live-ai]")
    .forEach((section) => initLiveAi(section, announce));

  root.addEventListener("click", (event) => {
    const terminal = event.target.closest(
      "[data-live-processing], [data-live-terminal]",
    );
    if (!terminal) return;
    purgeLivePrivateAi(root);
    announce(
      "Session이 PROCESSING으로 전환되어 개인 LIVE Summary·Chat과 선택 Job 정보를 삭제했습니다.",
    );
    showToast("개인 LIVE AI 데이터가 삭제되었습니다.", "info");
  });

  if (
    ["processing", "completed"].includes(
      new URLSearchParams(window.location.search).get("view"),
    )
  ) {
    purgeLivePrivateAi(root);
  }

  return { announce };
}
