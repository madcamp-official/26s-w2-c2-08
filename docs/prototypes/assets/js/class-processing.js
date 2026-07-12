import { setDemoState, showToast } from "./prototype.js";
const params = new URLSearchParams(location.search);
const role = params.get("role") || "professor";
const access = params.get("access") || "normal";
if (access !== "normal") {
  const copy = {
    loading: ["정리 상태를 불러오는 중입니다", "잠시 기다려주세요."],
    error: [
      "정리 상태를 불러오지 못했습니다",
      "보호된 이전 기록은 표시하지 않습니다.",
    ],
    "not-found": [
      "class를 찾을 수 없습니다",
      "Course에서 class 상태를 다시 확인해주세요.",
    ],
    expired: ["로그인이 만료되었습니다", "다시 로그인해주세요."],
    forbidden: [
      "Course 접근 권한이 없습니다",
      "보호된 수업 기록을 표시하지 않습니다.",
    ],
  }[access] || ["화면을 표시할 수 없습니다", "Course로 돌아가주세요."];
  document.querySelector("main").innerHTML =
    `<section class="state-panel auth-expired" role="alert"><div class="state-panel__content"><h1>${copy[0]}</h1><p>${copy[1]}</p><a class="button button--primary" href="dashboard.html">대시보드</a></div></section>`;
}
document.body.dataset.role = role;
document.querySelectorAll("[data-professor-only]").forEach((e) => {
  if (role !== "professor") e.hidden = true;
});
document.querySelectorAll("[data-student-only]").forEach((e) => {
  if (role !== "student") e.hidden = true;
});
const roleLabel = document.querySelector("[data-role-label]");
const completeLabel = document.querySelector("[data-complete-label]");
if (roleLabel) roleLabel.textContent = role === "professor" ? "교수자" : "학생";
if (completeLabel)
  completeLabel.textContent =
    role === "professor" ? "교수자 완료 기록 준비됨" : "학생 복습 기록 준비됨";
document.addEventListener("click", (e) => {
  const retry = e.target.closest("[data-job-retry]");
  if (retry) {
    const target = document.querySelector(retry.dataset.stateTarget);
    target.querySelector("[data-attempt]").textContent = "attempt 2";
    setDemoState(target, "pending");
    showToast(
      `${retry.dataset.jobRetry} 같은 Job을 attempt 2로 재시도합니다.`,
      "success",
    );
  }
  if (e.target.closest("[data-finalize-transcript]")) {
    document.querySelector("#lateFinal").hidden = false;
    setDemoState(document.querySelector("#transcriptJob"), "finalized");
    showToast("추가 final 저장 후 FINALIZED가 되었습니다.", "success");
  }
  if (e.target.closest("[data-server-complete]")) {
    setDemoState(document.querySelector("#sessionState"), "completed");
    showToast("server session.updated=COMPLETED 목 상태입니다.", "success");
  }
  if (e.target.closest("[data-record-open]"))
    showToast("PROCESSING부터 GET /record 저장 데이터를 열람합니다.", "info");
});
