import { setDemoState, showToast } from "./prototype.js";

const codePointLength = (value) => [...value.normalize("NFC")].length;

const setText = (selector, value) => {
  const target = document.querySelector(selector);
  if (target) target.textContent = value;
};

function syncRecordStatus() {
  const transcript = document.querySelector("[data-record-transcript]");
  const summary = document.querySelector("[data-record-summary]");
  const clusters = document.querySelector("[data-record-clusters]");
  const answers = document.querySelector("[data-record-answers]");
  const jobs = document.querySelector("[data-record-jobs]");
  if (!transcript || !summary || !clusters || !answers || !jobs) return;

  const params = new URLSearchParams(window.location.search);
  if (!params.has("transcript")) {
    if (summary.dataset.demoState === "not-applicable") {
      setDemoState(transcript, "empty");
    } else if (summary.dataset.demoState === "source-unavailable") {
      setDemoState(transcript, "failed");
    }
  }
  if (!params.has("summary")) {
    if (transcript.dataset.demoState === "empty") {
      setDemoState(summary, "not-applicable");
    } else if (transcript.dataset.demoState === "failed") {
      setDemoState(summary, "source-unavailable");
    }
  }

  const transcriptState = transcript.dataset.demoState;
  const summaryState = summary.dataset.demoState;
  const clusterState = clusters.dataset.demoState;
  const answerState = answers.dataset.demoState;
  const finalSegments = transcript.dataset.finalSegments || "0";
  const finalGaps = transcript.dataset.finalGaps || "0";
  const totalTranscriptItems = transcript.dataset.totalItems || "0";
  const questionCount = clusters.dataset.questionCount || "0";
  const finalClusterCount = clusters.dataset.finalClusterCount || "0";
  const clusterFinalizedAt = clusters.dataset.finalizedAt || "-";

  if (!params.has("jobs")) {
    if (
      summaryState === "retrying" ||
      clusterState === "cluster-retrying" ||
      answerState === "organization-retrying"
    ) {
      setDemoState(jobs, "retrying");
    } else if (
      transcriptState === "failed" ||
      transcriptState === "data-error" ||
      summaryState === "failed" ||
      summaryState === "source-unavailable" ||
      summaryState === "data-error" ||
      clusterState === "cluster-failed" ||
      answerState === "organization-failed" ||
      answerState === "organization-data-error"
    ) {
      setDemoState(jobs, "partial-failure");
    }
  }

  const transcriptCopy = {
    finalized: {
      availability: "RECORDING v2 canonical",
      manifest: `${finalSegments} + gap ${finalGaps}`,
      meta: "RECORDING · version 2 · canonical · FINALIZED · 기술적 완료",
      count: `SEGMENT ${finalSegments} · GAP ${finalGaps}`,
      job: "SUCCEEDED",
      jobMeta: "attempt 1 · blocks_session_completion=true",
    },
    "page-error": {
      availability: "RECORDING v2 canonical",
      manifest: `${finalSegments} + gap ${finalGaps}`,
      meta: "RECORDING · version 2 · canonical · FINALIZED · 추가 페이지 오류",
      count: `SEGMENT ${finalSegments} · GAP ${finalGaps}`,
      job: "SUCCEEDED",
      jobMeta: "attempt 1 · blocks_session_completion=true",
    },
    empty: {
      availability: "RECORDING v2 canonical · EMPTY",
      manifest: "0 · RECORDING EMPTY",
      meta: "RECORDING · version 2 · canonical · EMPTY",
      count: "SEGMENT 0 · GAP 0",
      job: "SUCCEEDED",
      jobMeta: "attempt 1 · 정상 무결과",
    },
    failed: {
      availability: "RECORDING v2 FAILED · LIVE v1 보존",
      manifest: "RECORDING FAILED · LIVE 1 보존",
      meta: "latest RECORDING version 2 · FAILED · LIVE version 1 보존",
      count: "FINAL SEGMENT 0 · 보존 LIVE 1",
      job: "FAILED",
      jobMeta: "attempt 1 · retryable · 교수자 공용 Job 재시도",
    },
    "data-error": {
      availability: "Transcript 상태 불일치",
      manifest: "DATA_INTEGRITY_ERROR",
      meta: "COMPLETED · RECORDING version 2 · FINALIZING",
      count: "DATA_INTEGRITY_ERROR",
      job: "DATA_ERROR",
      jobMeta: "terminal 상태를 확인할 수 없음",
    },
    error: {
      availability: "RECORDING v2 canonical",
      manifest: `${totalTranscriptItems} · 첫 페이지 조회 오류`,
      meta: "RECORDING · version 2 · canonical · FINALIZED · 목록 조회 오류",
      count: `SEGMENT ${finalSegments} · GAP ${finalGaps}`,
      job: "SUCCEEDED",
      jobMeta: "attempt 1 · blocks_session_completion=true",
    },
  }[transcriptState];

  if (transcriptCopy) {
    setText("[data-recording-availability]", transcriptCopy.availability);
    setText("[data-manifest-transcript]", transcriptCopy.manifest);
    setText("[data-transcript-meta]", transcriptCopy.meta);
    setText("[data-transcript-count]", transcriptCopy.count);
    setText("[data-recording-job-status]", transcriptCopy.job);
    setText("[data-recording-job-meta]", transcriptCopy.jobMeta);
    const recordingRetry = document.querySelector("[data-recording-job-retry]");
    if (recordingRetry) recordingRetry.hidden = transcriptCopy.job !== "FAILED";
  }

  const summaryCopy = {
    normal: [
      "최신 HQ RECORDING FINALIZED source에 고정된 결과입니다.",
      "FINAL · AVAILABLE",
      "SUCCEEDED",
      "attempt 1",
    ],
    "not-applicable": [
      "RECORDING EMPTY라 생성할 요약 source가 없습니다.",
      "NOT_APPLICABLE · NO_FINAL_TRANSCRIPT",
      null,
      null,
    ],
    "source-unavailable": [
      "HQ RECORDING source 실패로 요약 Job을 만들지 않았습니다.",
      "FAILED · SUMMARY_SOURCE_UNAVAILABLE",
      null,
      null,
    ],
    failed: [
      "최신 HQ RECORDING source는 유효하지만 FINAL Summary Job이 실패했습니다.",
      "FINAL · FAILED · attempt 1",
      "FAILED",
      "attempt 1 · retryable",
    ],
    retrying: [
      "같은 FINAL_SUMMARY Job 행을 재시도하고 있습니다.",
      "FINAL · PENDING · attempt 2",
      "PENDING",
      "attempt 2",
    ],
    "data-error": [
      "eligible source와 Summary 원장의 정합성을 확인할 수 없습니다.",
      "DATA_INTEGRITY_ERROR",
      "DATA_ERROR",
      "Job 원장 불일치",
    ],
  }[summaryState];
  if (summaryCopy) {
    setText("[data-summary-source]", summaryCopy[0]);
    setText("[data-summary-status]", summaryCopy[1]);
    const card = document.querySelector("[data-summary-job]");
    if (card) card.hidden = !summaryCopy[2];
    setText("[data-summary-job-status]", summaryCopy[2] || "");
    setText("[data-summary-job-meta]", summaryCopy[3] || "");
  }

  const clusterCopy = {
    normal: [
      "FINAL · SUCCEEDED · attempt 1 · " + clusterFinalizedAt,
      "SUCCEEDED",
      "attempt 1 · finalized_at " + clusterFinalizedAt,
      `${questionCount} / ${finalClusterCount}`,
    ],
    "page-error": [
      "FINAL · SUCCEEDED · 추가 페이지 오류",
      "SUCCEEDED",
      "attempt 1 · finalized_at " + clusterFinalizedAt,
      `${questionCount} / ${finalClusterCount}`,
    ],
    "cluster-failed": [
      "FINAL · FAILED · attempt 1",
      "FAILED",
      "attempt 1 · retryable",
      `${questionCount} / 0`,
    ],
    "cluster-retrying": [
      "FINAL · PENDING · attempt 2",
      "PENDING",
      "attempt 2 · retrying",
      `${questionCount} / 0`,
    ],
    empty: [
      "FINAL · 대상 0건 · 표현 TBD",
      "TBD",
      "Job 생략·빈 성공 원장 미정",
      "0 / TBD",
    ],
    error: [
      "FINAL Cluster 목록 조회 오류",
      "SUCCEEDED",
      "attempt 1 · 결과 조회 오류",
      `${questionCount} / ${finalClusterCount}`,
    ],
  }[clusterState];
  if (clusterCopy) {
    setText("[data-cluster-status]", clusterCopy[0]);
    setText("[data-cluster-job-status]", clusterCopy[1]);
    setText("[data-cluster-job-meta]", clusterCopy[2]);
    setText("[data-manifest-question-clusters]", clusterCopy[3]);
    const retry = document.querySelector(
      "[data-cluster-job] [data-shared-job-retry]",
    );
    if (retry) retry.hidden = clusterCopy[1] !== "FAILED";
  }

  const summaryRetry = document.querySelector(
    "[data-summary-job] [data-shared-job-retry]",
  );
  if (summaryRetry) summaryRetry.hidden = summaryCopy?.[2] !== "FAILED";

  const answerJob = document.querySelector("[data-answer-job]");
  if (answerJob) {
    const defaultStatus = answerJob.dataset.defaultStatus || "SUCCEEDED";
    const defaultMeta = answerJob.dataset.defaultMeta || "attempt 1";
    const answerLabel = answerJob.dataset.answerLabel || "Answer";
    const answerCopy = {
      normal: [defaultStatus, defaultMeta],
      "organization-waiting-source": [
        "WAITING_SOURCE",
        `job_id=null · ${answerLabel}`,
      ],
      "organization-pending": ["PENDING", `attempt 1 · ${answerLabel}`],
      "organization-running": ["RUNNING", `attempt 1 · ${answerLabel}`],
      "organization-succeeded": ["SUCCEEDED", `attempt 1 · ${answerLabel}`],
      "organization-failed": [
        "FAILED",
        `attempt 1 · ${answerLabel} · retryable`,
      ],
      "organization-retrying": [
        "PENDING",
        `attempt 2 · ${answerLabel} · retrying`,
      ],
      "organization-data-error": [
        "DATA_ERROR",
        `${answerLabel} · Job 원장 불일치`,
      ],
      error: ["UNKNOWN", `${answerLabel} · 목록 조회 오류`],
    }[answerState] || [defaultStatus, defaultMeta];
    setText("[data-answer-job-status]", answerCopy[0]);
    setText("[data-answer-job-meta]", answerCopy[1]);
    const retry = answerJob.querySelector("[data-shared-job-retry]");
    if (retry) retry.hidden = answerCopy[0] !== "FAILED";
  }

  const failureStates = [
    transcriptState === "failed" || transcriptState === "data-error",
    summaryState === "failed" ||
      summaryState === "source-unavailable" ||
      summaryState === "data-error",
    clusterState === "cluster-failed",
    answerState === "organization-failed" ||
      answerState === "organization-data-error",
    jobs.dataset.demoState === "partial-failure",
  ];
  const retrying =
    summaryState === "retrying" ||
    clusterState === "cluster-retrying" ||
    answerState === "organization-retrying" ||
    jobs.dataset.demoState === "retrying";
  setText(
    "[data-record-health]",
    retrying
      ? "공유 Job 재시도 중"
      : failureStates.some(Boolean)
        ? "부분 실패 있음"
        : "공유 Job 정상 종료",
  );
}

function initPlayback() {
  const player = document.querySelector("[data-recording-player]");
  if (!player) return;

  const times = [...player.querySelectorAll("[data-playback-time]")];
  const seekStatus = document.querySelector("[data-recording-seek-status]");
  const duration = player.dataset.recordingDuration || "52:14";
  let selectedSeek =
    document.querySelector("[data-recording-seek][data-seek-default]") ||
    document.querySelector("[data-recording-seek]");

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
    if (label) times.forEach((item) => (item.textContent = label));
    if (progress) player.style.setProperty("--recording-progress", progress);
    updateSeekAvailability(state);
  };

  const updateSeekLabels = () => {
    const label = selectedSeek?.dataset.recordingLabel || "선택한 문장";
    seekStatus?.querySelectorAll("[data-seek-label]").forEach((item) => {
      item.textContent = label;
    });
    return label;
  };

  const markActiveSeek = (active) => {
    document.querySelectorAll("[data-recording-seek]").forEach((item) => {
      const isActive = active && item === selectedSeek;
      item.classList.toggle("is-active", isActive);
      item.setAttribute("aria-pressed", String(isActive));
    });
  };

  const setSeekState = (state, announcement) => {
    if (!seekStatus) return;
    updateSeekLabels();
    setDemoState(seekStatus, state);
    seekStatus.setAttribute("aria-busy", String(state === "seeking"));
    const liveCopy = seekStatus.querySelector("[data-seek-announcement]");
    if (liveCopy && announcement) liveCopy.textContent = announcement;
    markActiveSeek(state === "active");
  };

  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-playback-action]");
    const seek = event.target.closest("[data-recording-seek]");
    const seekOutcome = event.target.closest("[data-seek-outcome]");
    const seekRetry = event.target.closest("[data-seek-retry]");
    const seekPlay = event.target.closest("[data-seek-play]");

    if (action) {
      if (action.dataset.playbackAction === "play") {
        const start =
          seekStatus?.dataset.demoState === "active"
            ? updateSeekLabels()
            : "10:28";
        setPlayback("playing", `${start} / ${duration}`, "20%");
        showToast("재생 권한을 다시 확인한 뒤 음성을 재생합니다.", "info");
      } else if (action.dataset.playbackAction === "pause") {
        setPlayback("paused", times[0]?.textContent || `10:28 / ${duration}`);
      } else if (action.dataset.playbackAction === "retry") {
        setPlayback("ready", `00:00 / ${duration}`, "0%");
        showToast("녹음 접근 권한과 재생 URL을 다시 확인했습니다.", "success");
      }
    }

    if (seek) {
      selectedSeek = seek;
      const label = updateSeekLabels();
      setSeekState("seeking", `${label} 녹음 위치를 확인하고 있습니다.`);
      showToast("현재 권한과 recording offset을 확인합니다.");
    }

    if (seekOutcome) {
      const state = seekOutcome.dataset.seekOutcome;
      const label = updateSeekLabels();
      if (state === "active") {
        setSeekState(
          "active",
          `${label} 위치 이동을 완료했습니다. 아직 재생을 시작하지 않았습니다.`,
        );
        showToast("녹음 위치 이동을 완료했습니다.", "success");
      } else {
        setSeekState(
          "seek-error",
          `${label} 위치로 이동하지 못했습니다. 같은 위치를 다시 시도할 수 있습니다.`,
        );
        showToast("녹음 위치 이동에 실패했습니다.", "error");
      }
    }

    if (seekRetry) {
      const label = updateSeekLabels();
      setSeekState("seeking", `${label} 녹음 위치를 다시 확인하고 있습니다.`);
      showToast("같은 recording offset을 다시 확인합니다.");
    }

    if (seekPlay && seekStatus?.dataset.demoState === "active") {
      const label = updateSeekLabels();
      setPlayback("playing", `${label} / ${duration}`, "34%");
      showToast("확인된 위치에서 재생을 시작합니다.", "success");
    }
  });

  document.querySelectorAll("[data-recording-seek]").forEach((item) => {
    item.setAttribute("aria-pressed", "false");
  });
  updateSeekAvailability(player.dataset.demoState);
  if (seekStatus) {
    const initialSeekState = seekStatus.dataset.demoState || "idle";
    const initialCopy = {
      idle: "Transcript 녹음 위치 이동을 기다립니다.",
      seeking: `${updateSeekLabels()} 녹음 위치를 확인하고 있습니다.`,
      active: `${updateSeekLabels()} 위치 이동이 완료됐습니다. 아직 재생을 시작하지 않았습니다.`,
      "seek-error": `${updateSeekLabels()} 위치로 이동하지 못했습니다.`,
    }[initialSeekState];
    setSeekState(initialSeekState, initialCopy);
  }
}

function initPagination() {
  const getOwnedItems = (scope, region, selector) =>
    [...scope.querySelectorAll(selector)].filter((item) => {
      const explicitOwner = item.closest("[data-page-scope]");
      if (scope.matches("[data-page-scope]")) return explicitOwner === scope;
      return !explicitOwner && item.closest("[data-page-region]") === region;
    });

  document.addEventListener("click", (event) => {
    const more = event.target.closest("[data-load-more]");
    const retry = event.target.closest("[data-page-retry]");
    if (!more && !retry) return;

    const region = (more || retry).closest("[data-page-region]");
    if (!region) return;
    const scope = (more || retry).closest("[data-page-scope]") || region;

    if (retry && region.dataset.pageSuccessState) {
      setDemoState(region, region.dataset.pageSuccessState);
    }

    getOwnedItems(scope, region, "[data-page-extra]").forEach((item) => {
      item.hidden = false;
    });
    getOwnedItems(scope, region, "[data-loaded-count]").forEach((item) => {
      item.textContent = item.dataset.loadedComplete || item.textContent;
    });
    getOwnedItems(scope, region, "[data-load-more], [data-page-retry]").forEach(
      (item) => {
        item.hidden = true;
      },
    );
    const status = getOwnedItems(scope, region, "[data-page-status]")[0];
    if (status) {
      if (status.querySelector("[data-loaded-count]")) {
        status.append(" · 다음 cursor 페이지를 불러왔습니다.");
      } else {
        status.textContent = "다음 cursor 페이지를 불러왔습니다.";
      }
    }
    syncRecordStatus();
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

  const setFormAvailable = (available) => {
    form.querySelectorAll("textarea, button").forEach((item) => {
      item.disabled = !available;
    });
  };

  const announce = (message) => {
    if (!log) return;
    const item = document.createElement("li");
    item.className = "sr-only";
    item.dataset.reviewAnnouncement = "";
    item.textContent = message;
    log.append(item);
  };

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
    const firstState = log?.querySelector("[data-show-state]");
    log?.insertBefore(message, firstState || null);
    input.value = "";
    validate();
    setFormAvailable(false);
    setDemoState(chat, "pending");
    announce(
      "CHAT_RESPONSE Job이 PENDING입니다. 생성 중 문장은 표시하지 않습니다.",
    );
    showToast("USER Message와 CHAT_RESPONSE Job을 함께 저장했습니다.");
  });

  document.addEventListener("click", (event) => {
    const outcome = event.target.closest("[data-review-outcome]");
    const retry = event.target.closest("[data-review-retry]");
    if (outcome) {
      const state = outcome.dataset.reviewOutcome;
      setDemoState(chat, state);
      setFormAvailable(["complete", "no-evidence"].includes(state));
      announce(
        {
          complete: "저장된 최종 답변과 Evidence를 표시했습니다.",
          "no-evidence": "근거 없는 저장 완료 답변을 표시했습니다.",
          failed: "CHAT_RESPONSE가 실패했습니다. 기존 대화는 유지됩니다.",
        }[state],
      );
    }
    if (retry) {
      chat.querySelectorAll("[data-review-attempt]").forEach((item) => {
        item.textContent = "attempt 2";
      });
      setDemoState(chat, "pending");
      setFormAvailable(false);
      announce("같은 CHAT_RESPONSE Job을 attempt 2로 재시도합니다.");
      showToast("같은 CHAT_RESPONSE Job을 attempt 2로 재시도합니다.");
    }
  });

  if (count) count.textContent = "0 / 2,000자";
  input.setAttribute("aria-invalid", "false");
  if (error) error.hidden = true;
  setFormAvailable(
    ["empty", "complete", "no-evidence"].includes(chat.dataset.demoState),
  );
}

function initRecordStateSync() {
  syncRecordStatus();
  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-state-action]");
    const retry = event.target.closest("[data-record-state-target]");
    if (retry) {
      setDemoState(
        document.querySelector(retry.dataset.recordStateTarget),
        retry.dataset.recordState,
      );
    }
    if (action || retry) queueMicrotask(syncRecordStatus);
  });
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
  initRecordStateSync();
}
