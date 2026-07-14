import { setDemoState, showToast } from "./prototype.js";

const archiveConfig = {
  materials: {
    title: "PDF 자료",
    description:
      "모든 class에 현재 연결된 PDF를 모아 보고, 권한을 다시 확인한 뒤 열거나 개별 다운로드합니다.",
    empty: "현재 연결된 PDF 자료가 없습니다",
  },
  transcripts: {
    title: "Transcript",
    description:
      "class별 Transcript 상태를 먼저 확인하고, 선택한 class의 timeline만 필요할 때 불러옵니다.",
    empty: "표시할 Transcript가 없습니다",
  },
  summaries: {
    title: "AI 요약",
    description:
      "Course 구성원에게 공유되는 FINAL 요약만 모아 봅니다. 개인 LIVE Summary와 Chat은 포함하지 않습니다.",
    empty: "공유된 FINAL 요약이 없습니다",
  },
  qna: {
    title: "질의응답",
    description:
      "작성자 정보 없이 학생 질문과 공개 Answer를 읽고, 관리가 필요하면 해당 class 기록으로 이동합니다.",
    empty: "아직 모아 볼 질의응답이 없습니다",
  },
};

const validSessionStates = new Set(["live", "ready", "processing", "none"]);
const validListStates = new Set(["normal", "loading", "empty", "error"]);
const validContentStates = new Set(["normal", "loading", "empty", "error"]);
const params = new URLSearchParams(window.location.search);

function readParam(name, valid, fallback) {
  const value = params.get(name);
  return value && valid.has(value) ? value : fallback;
}

let archive = archiveConfig[params.get("archive")]
  ? params.get("archive")
  : "materials";
let sessionState = readParam("session", validSessionStates, "live");
let classListState = readParam("classes", validListStates, "normal");
let contentState = readParam("content", validContentStates, "normal");
let selectedClass = params.get("class") || "f2";

function syncQuery() {
  params.set("archive", archive);
  params.set("session", sessionState);
  params.set("classes", classListState);
  params.set("content", contentState);
  params.set("class", selectedClass);
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}?${params}`,
  );
}

function syncArchive() {
  const config = archiveConfig[archive];
  document.querySelectorAll("[data-archive-link]").forEach((link) => {
    const active = link.dataset.archiveLink === archive;
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");

    const linkParams = new URLSearchParams(params);
    linkParams.set("archive", link.dataset.archiveLink);
    link.href = `course-workspace.html?${linkParams}`;
  });

  document.querySelectorAll("[data-archive-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.archivePanel !== archive;
  });
  document.querySelectorAll("[data-archive-title]").forEach((target) => {
    target.textContent = config.title;
  });
  document.querySelectorAll("[data-archive-description]").forEach((target) => {
    target.textContent = config.description;
  });
  document.querySelectorAll("[data-archive-empty]").forEach((target) => {
    target.textContent = config.empty;
  });
}

function syncStateButtons() {
  const current = {
    session: sessionState,
    classes: classListState,
    content: contentState,
  };
  document.querySelectorAll("[data-query-param]").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(current[button.dataset.queryParam] === button.dataset.queryValue),
    );
  });
}

function syncSelectedClass() {
  document.querySelectorAll("[data-class-select]").forEach((link) => {
    const active = link.dataset.classSelect === selectedClass;
    link.setAttribute("aria-current", String(active));
    const linkParams = new URLSearchParams(params);
    linkParams.set("class", link.dataset.classSelect);
    link.href = `course-workspace.html?${linkParams}`;
  });
}

function syncAll() {
  setDemoState(document.querySelector("#liveClassSlot"), sessionState);
  setDemoState(document.querySelector("#completedClassList"), classListState);
  setDemoState(document.querySelector("#archiveContent"), contentState);
  syncQuery();
  syncArchive();
  syncStateButtons();
  syncSelectedClass();
}

document.addEventListener("click", (event) => {
  const stateButton = event.target.closest("[data-query-param]");
  if (stateButton) {
    const { queryParam, queryValue } = stateButton.dataset;
    if (queryParam === "session") sessionState = queryValue;
    if (queryParam === "classes") classListState = queryValue;
    if (queryParam === "content") contentState = queryValue;
    syncAll();
    return;
  }

  const classLink = event.target.closest("[data-class-select]");
  if (classLink && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
    event.preventDefault();
    selectedClass = classLink.dataset.classSelect;
    syncAll();
    document.querySelector("#archiveHeading")?.focus();
    showToast("선택한 class 기준으로 archive 예시를 표시합니다.", "info");
  }

  const loadMore = event.target.closest("[data-class-load-more]");
  if (loadMore) {
    document.querySelectorAll("[data-later-class]").forEach((item) => {
      item.hidden = false;
    });
    loadMore.hidden = true;
    showToast("다음 cursor의 완료 class 예시를 추가했습니다.", "success");
  }
});

const classRail = document.querySelector(".course-class-rail");
const desktopWorkspace = window.matchMedia("(min-width: 901px)");
const keepDesktopRailOpen = () => {
  if (desktopWorkspace.matches && classRail) classRail.open = true;
};

desktopWorkspace.addEventListener?.("change", keepDesktopRailOpen);
keepDesktopRailOpen();
syncAll();
