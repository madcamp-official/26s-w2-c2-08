import { initRecordCommon } from "./record-common.js";
import { setDemoState, showToast } from "./prototype.js";

const params = new URLSearchParams(location.search);
const role = params.get("role") === "student" ? "student" : "professor";
const scenario = params.get("scenario") || "transcribing";

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
  transcribing: {
    label: "HQ STT 실행 중",
    upload: "completed",
    transcript: "finalizing",
    coordinator: "pending",
    summary: "waiting",
    cluster: "succeeded",
    answer: "waiting",
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
    coordinator: "running",
    summary: "source-unavailable",
    cluster: "succeeded",
    answer: "running",
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
};

const config = scenarios[scenario] || scenarios.transcribing;
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

setDemoState(document.querySelector("#recordingUpload"), config.upload);
setDemoState(document.querySelector("#hqTranscript"), config.transcript);
setDemoState(document.querySelector("#coordinatorJob"), config.coordinator);
setDemoState(document.querySelector("#finalSummaryState"), config.summary);
setDemoState(document.querySelector("#finalClusterJob"), config.cluster);
setDemoState(document.querySelector("#answerProcessing"), config.answer);

if (scenario === "completed" || scenario === "completed-with-failures") {
  setDemoState(document.querySelector("#processingView"), "completed");
  if (scenario === "completed-with-failures") {
    document.querySelector("[data-complete-copy]").textContent =
      "서버가 completed_at을 기록했습니다. HQ STT 또는 AI 작업 일부가 실패했지만 저장된 PDF·LIVE Transcript·질문·Answer와 성공 결과는 열 수 있습니다.";
  }
  window.setTimeout(
    () => document.querySelector("#processingCompleteTitle")?.focus(),
    0,
  );
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
  if (event.target.closest("[data-title-edit]")) {
    const title = window.prompt(
      "class 제목",
      document.querySelector("#processingTitle").textContent,
    );
    if (title?.trim()) {
      document.querySelector("#processingTitle").textContent = title.trim();
      showToast(
        "제목만 수정했습니다. 시작·종료 시각은 바뀌지 않습니다.",
        "success",
      );
    }
  }
});

initRecordCommon();
