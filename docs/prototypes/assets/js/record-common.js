import { setDemoState, showToast } from "./prototype.js";

const codePointLength = (value) => [...value.normalize("NFC")].length;

function initPlayback() {
  const player = document.querySelector("[data-recording-player]");
  if (!player) return;

  const time = player.querySelector("[data-playback-time]");
  const updateSeekAvailability = (state) => {
    const allowed = ["ready", "playing", "paused", "ended"].includes(state);
    document.querySelectorAll("[data-recording-seek]").forEach((item) => {
      item.disabled = !allowed;
      item.title = allowed
        ? "재생 권한 확인 후 녹음 위치로 이동"
        : "녹음 접근 권한 확인 뒤 사용할 수 있습니다";
    });
  };
  const setPlayback = (state, label, progress) => {
    setDemoState(player, state);
    if (time && label) time.textContent = label;
    if (progress) player.style.setProperty("--recording-progress", progress);
    updateSeekAvailability(state);
  };

  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-playback-action]");
    const seek = event.target.closest("[data-recording-seek]");

    if (action) {
      if (action.dataset.playbackAction === "play") {
        setPlayback("playing", "10:28 / 52:14", "20%");
        showToast("재생 권한을 다시 확인한 뒤 음성을 재생합니다.", "info");
      } else if (action.dataset.playbackAction === "pause") {
        setPlayback("paused", time?.textContent || "10:28 / 52:14");
      } else if (action.dataset.playbackAction === "retry") {
        setPlayback("ready", "00:00 / 52:14", "0%");
        showToast("녹음 접근 권한과 재생 URL을 다시 확인했습니다.", "success");
      }
    }

    if (seek) {
      setPlayback("playing", `${seek.dataset.recordingLabel} / 52:14`, "34%");
      document
        .querySelectorAll("[data-recording-seek]")
        .forEach((item) => item.classList.toggle("is-active", item === seek));
      showToast("현재 권한을 확인하고 서버 recording offset으로 이동합니다.");
    }
  });

  updateSeekAvailability(player.dataset.demoState);
}

function initPagination() {
  document.addEventListener("click", (event) => {
    const more = event.target.closest("[data-load-more]");
    const retry = event.target.closest("[data-page-retry]");
    if (!more && !retry) return;

    const region = (more || retry).closest("[data-page-region]");
    if (!region) return;

    region.querySelectorAll("[data-page-extra]").forEach((item) => {
      item.hidden = false;
    });
    region.querySelectorAll("[data-loaded-count]").forEach((item) => {
      item.textContent = item.dataset.loadedComplete || item.textContent;
    });
    region
      .querySelectorAll("[data-load-more], [data-page-retry]")
      .forEach((item) => {
        item.hidden = true;
      });
    const status = region.querySelector("[data-page-status]");
    if (status) status.textContent = "다음 cursor 페이지를 불러왔습니다.";
    showToast("기존 항목을 유지하고 다음 cursor 페이지를 추가했습니다.");
  });
}

function initEvidence() {
  document.addEventListener("click", (event) => {
    const evidence = event.target.closest("[data-evidence-link]");
    if (!evidence || evidence.disabled) return;
    const state = evidence.dataset.evidenceState || "ready";
    if (state === "error") {
      showToast(
        "이 근거만 열지 못했습니다. 저장된 AI 답변은 유지됩니다.",
        "error",
      );
      return;
    }
    showToast(
      `${evidence.dataset.sourceKind} 공개 link의 현재 권한을 확인합니다.`,
      "info",
    );
  });
}

function initReviewChat() {
  const chat = document.querySelector("[data-review-chat]");
  const form = chat?.querySelector("[data-review-form]");
  const input = form?.querySelector("[data-review-input]");
  const error = form?.querySelector("[data-review-error]");
  const count = form?.querySelector("[data-review-count]");
  const log = chat?.querySelector("[data-review-log]");
  if (!chat || !form || !input) return;

  const validate = () => {
    const normalized = input.value.trim().normalize("NFC");
    const length = codePointLength(normalized);
    if (count) count.textContent = `${length} / 2,000자`;
    const reason =
      length === 0
        ? "질문을 입력해주세요."
        : length > 2000
          ? `2,000자 이하로 입력해주세요. 현재 ${length}자입니다.`
          : "";
    input.setAttribute("aria-invalid", String(Boolean(reason)));
    if (error) {
      error.textContent = reason;
      error.hidden = !reason;
    }
    return !reason;
  };

  input.addEventListener("input", validate);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!validate()) {
      input.focus();
      return;
    }
    const message = document.createElement("li");
    message.className = "record-chat-message";
    message.dataset.role = "user";
    message.textContent = input.value.trim().normalize("NFC");
    log?.append(message);
    input.value = "";
    validate();
    setDemoState(chat, "pending");
    showToast("USER Message와 CHAT_RESPONSE Job을 함께 저장했습니다.");
  });

  document.addEventListener("click", (event) => {
    const outcome = event.target.closest("[data-review-outcome]");
    const retry = event.target.closest("[data-review-retry]");
    if (outcome) setDemoState(chat, outcome.dataset.reviewOutcome);
    if (retry) {
      chat.querySelectorAll("[data-review-attempt]").forEach((item) => {
        item.textContent = "attempt 2";
      });
      setDemoState(chat, "pending");
      showToast("같은 CHAT_RESPONSE Job을 attempt 2로 재시도합니다.");
    }
  });

  if (count) count.textContent = "0 / 2,000자";
  input.setAttribute("aria-invalid", "false");
  if (error) error.hidden = true;
}

function initManifestRetry() {
  document.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-manifest-retry]");
    if (!retry) return;
    const view = document.querySelector(retry.dataset.stateTarget);
    setDemoState(view, "normal");
    showToast("compact record manifest를 다시 조회했습니다.", "success");
  });
}

export function initRecordCommon() {
  initPlayback();
  initPagination();
  initEvidence();
  initReviewChat();
  initManifestRetry();
}
