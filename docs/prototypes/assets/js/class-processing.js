import { initRecordCommon } from "./record-common.js";
import { setDemoState, showToast } from "./prototype.js";

const params = new URLSearchParams(location.search);
const role = params.get("role") === "student" ? "student" : "professor";
const scenario = params.get("scenario") || "transcribing";
const requestedView = params.get("view") || params.get("access");
const recordRegionState = ["normal", "loading", "error", "page-error"].includes(
  params.get("region"),
)
  ? params.get("region")
  : "normal";

const scenarios = {
  uploading: {
    label: "원본 녹음 업로드 중",
    upload: "in-progress",
    transcript: "awaiting-upload",
    coordinator: "pending",
    summary: "waiting",
    cluster: "running",
    answer: "waiting",
  },
  "upload-interrupted": {
    label: "원본 녹음 업로드 중단",
    upload: "interrupted",
    transcript: "awaiting-upload",
    coordinator: "pending",
    summary: "waiting",
    cluster: "running",
    answer: "waiting",
  },
  "upload-resuming": {
    label: "원본 녹음 업로드 재개 중",
    upload: "resuming",
    transcript: "awaiting-upload",
    coordinator: "pending",
    summary: "waiting",
    cluster: "running",
    answer: "waiting",
  },
  "upload-failed": {
    label: "원본 녹음 저장 실패 · fallback 정리 중",
    upload: "failed",
    transcript: "source-unavailable",
    coordinator: "succeeded",
    summary: "source-unavailable",
    cluster: "succeeded",
    answer: "running-live-fallback",
  },
  transcribing: {
    label: "HQ STT 실행 중",
    upload: "completed",
    transcript: "finalizing",
    coordinator: "pending",
    summary: "waiting",
    cluster: "succeeded",
    answer: "waiting",
  },
  empty: {
    label: "HQ STT 정상 종료 · 요약 대상 없음",
    upload: "completed",
    transcript: "empty",
    coordinator: "succeeded",
    summary: "not-applicable",
    cluster: "succeeded",
    answer: "running-live-fallback",
  },
  organizing: {
    label: "Answer·Summary 정리 중",
    upload: "completed",
    transcript: "finalized",
    coordinator: "succeeded",
    summary: "running",
    cluster: "succeeded",
    answer: "running",
  },
  "hq-failed": {
    label: "HQ STT 실패 · fallback 정리 중",
    upload: "completed",
    transcript: "failed",
    coordinator: "succeeded",
    summary: "source-unavailable",
    cluster: "succeeded",
    answer: "running-live-fallback",
  },
  "finishing-with-failure": {
    label: "일부 실패 · 남은 Answer 정리 중",
    upload: "completed",
    transcript: "finalized",
    coordinator: "failed",
    summary: "available",
    cluster: "failed",
    answer: "running",
  },
  "integrity-error": {
    label: "요약 원장 불일치 · 남은 Answer 정리 중",
    upload: "completed",
    transcript: "finalized",
    coordinator: "succeeded",
    summary: "data-error",
    cluster: "succeeded",
    answer: "running",
  },
};

const config = scenarios[scenario] || scenarios.transcribing;
const transcriptPresentation = {
  finalized: {
    manifest: "RECORDING v2 · 132 + final gap 1",
    title: "RECORDING canonical · version 2",
    copy: "저장 Segment 132개와 final Gap 1개를 timeline cursor로 조회합니다.",
  },
  empty: {
    manifest: "RECORDING v2 · 0 + final gap 1",
    title: "RECORDING canonical · version 2 · EMPTY",
    copy: "확정 Segment는 0개이며 final Gap 1개를 timeline cursor로 조회합니다.",
  },
  live: {
    manifest: "LIVE v1 · 129 + 임시 gap 1",
    title: "LIVE canonical · version 1",
    copy: "저장 Segment 129개와 임시 Gap을 timeline cursor로 조회합니다.",
  },
};
const selectedTranscript = ["finalized", "empty"].includes(config.transcript)
  ? transcriptPresentation[config.transcript]
  : transcriptPresentation.live;
const recordingManifest = {
  preparing: "UPLOAD_PENDING",
  "in-progress": "UPLOADING",
  interrupted: "UPLOADING · 연결 중단",
  resuming: "UPLOADING · 재개 중",
  completed: "UPLOADED",
  failed: "FAILED",
}[config.upload];
const summaryManifest = {
  waiting: "PENDING · Job 없음",
  running: "PENDING · Job RUNNING (attempt 1)",
  available: "AVAILABLE",
  "not-applicable": "NOT_APPLICABLE",
  "source-unavailable": "FAILED · SUMMARY_SOURCE_UNAVAILABLE",
  "data-error": "DATA_INTEGRITY_ERROR",
}[config.summary];
const clusterManifest = {
  pending: "24 / CURRENT 4 · FINAL PENDING",
  running: "24 / CURRENT 4 · FINAL RUNNING",
  succeeded: "24 / CURRENT 4 · FINAL 4",
  failed: "24 / CURRENT 4 · FINAL FAILED",
}[config.cluster];
const accessStates = new Set([
  "loading",
  "error",
  "forbidden",
  "expired",
  "not-found",
]);
const terminalScenario =
  requestedView === "completed" ||
  scenario === "completed" ||
  scenario === "completed-with-failures";

document.body.dataset.role = role;
document.querySelectorAll("[data-professor-only]").forEach((element) => {
  element.hidden = role !== "professor";
});
document.querySelectorAll("[data-student-only]").forEach((element) => {
  element.hidden = role !== "student";
});
document.querySelector("[data-role-label]").textContent =
  role === "professor" ? "교수자" : "학생";
document.querySelector("[data-scenario-label]").textContent = config.label;
document.querySelectorAll("[data-scenario-link]").forEach((link) => {
  const target = new URL(link.href);
  target.searchParams.set("role", role);
  link.href = `${target.pathname.split("/").pop()}?${target.searchParams}`;
});

document.querySelector("[data-manifest-recording]").textContent =
  recordingManifest;
document.querySelector("[data-manifest-transcript]").textContent =
  selectedTranscript.manifest;
document.querySelector("[data-manifest-summary]").textContent = summaryManifest;
document.querySelector("[data-manifest-clusters]").textContent =
  clusterManifest;
document.querySelector("[data-transcript-preview-title]").textContent =
  selectedTranscript.title;
document.querySelector("[data-transcript-preview-copy]").textContent =
  selectedTranscript.copy;

setDemoState(document.querySelector("#recordingUpload"), config.upload);
setDemoState(document.querySelector("#hqTranscript"), config.transcript);
setDemoState(document.querySelector("#coordinatorJob"), config.coordinator);
setDemoState(document.querySelector("#finalSummaryState"), config.summary);
setDemoState(document.querySelector("#finalClusterJob"), config.cluster);
setDemoState(document.querySelector("#finalClusterPreview"), config.cluster);
setDemoState(document.querySelector("#answerProcessing"), config.answer);
setDemoState(document.querySelector("#storedRecordRegion"), recordRegionState);

if (terminalScenario) {
  setDemoState(document.querySelector("#processingView"), "completed");
  document.querySelector("[data-session-state-label]").textContent =
    "CLASS_COMPLETED_RECORD · COMPLETED";
  document.querySelector("[data-session-time-label]").innerHTML =
    "2026년 7월 12일 10:00 시작 · 10:52 종료 · completed_at 11:02:18 · <span data-role-label></span> 화면";
  document.querySelector("[data-role-label]").textContent =
    role === "professor" ? "교수자" : "학생";
  if (scenario === "completed-with-failures") {
    document.querySelector("[data-complete-copy]").textContent =
      "서버가 completed_at을 기록했습니다. HQ STT 또는 AI 작업 일부가 실패했지만 저장된 PDF·LIVE Transcript·질문·Answer와 성공 결과는 열 수 있습니다.";
  }
  window.setTimeout(
    () => document.querySelector("#processingCompleteTitle")?.focus(),
    0,
  );
} else if (accessStates.has(requestedView)) {
  document.querySelector("[data-processing-header]").hidden = true;
  setDemoState(document.querySelector("#processingView"), requestedView);
}

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-upload-resume]")) {
    setDemoState(document.querySelector("#recordingUpload"), "resuming");
    showToast("서버가 확인한 offset부터 업로드 재개를 준비합니다.");
  }
  if (event.target.closest("[data-manifest-refresh]")) {
    showToast(
      "최신 Session·상태·count·조회 경로를 다시 받았습니다.",
      "success",
    );
  }
  if (event.target.closest("[data-manifest-retry]")) {
    document.querySelector("[data-processing-header]").hidden = false;
  }
  if (event.target.closest("[data-record-region-retry]")) {
    setDemoState(document.querySelector("#storedRecordRegion"), "normal");
    showToast(
      "다른 영역을 유지하고 저장 기록 첫 cursor 페이지만 다시 조회했습니다.",
      "success",
    );
  }
  if (event.target.closest("[data-job-retry]")) {
    setDemoState(document.querySelector("#coordinatorJob"), "pending");
    showToast(
      "기존 기록을 유지하고 실패한 후처리 Job을 새 attempt로 다시 요청했습니다.",
      "success",
    );
  }
  if (event.target.closest("[data-title-edit]")) {
    const title = window.prompt(
      "class 제목",
      document.querySelector("#processingTitle").textContent,
    );
    if (title !== null) {
      const normalized = title.trim();
      document.querySelector("#processingTitle").textContent =
        normalized || "알고리즘 · 2026년 7월 12일 10:00 (서버 자동 제목 예시)";
      showToast(
        normalized
          ? "제목만 수정했습니다. 시작·종료 시각은 바뀌지 않습니다."
          : "빈 제목을 서버 자동 생성 제목으로 바꿨습니다.",
        "success",
      );
    }
  }
});

initRecordCommon();
