const ownedCourses = document.querySelector("#ownedCourses");
const joinedCourses = document.querySelector("#joinedCourses");
const ownedLiveCard = document.querySelector("[data-owned-live-card]");

function syncCourseCount(target, key, normalCount) {
  const output = document.querySelector(`[data-course-count="${key}"]`);
  if (!target || !output) return;
  const state = target.dataset.demoState;
  output.textContent =
    state === "normal" ? String(normalCount) : state === "empty" ? "0" : "—";
}

function syncDashboardStates() {
  syncCourseCount(ownedCourses, "owned", 2);
  syncCourseCount(joinedCourses, "joined", 3);
  if (ownedLiveCard) {
    ownedLiveCard.hidden = ownedCourses?.dataset.demoState === "empty";
  }
}

[ownedCourses, joinedCourses].forEach((target) => {
  if (!target) return;
  new MutationObserver(syncDashboardStates).observe(target, {
    attributes: true,
    attributeFilter: ["data-demo-state"],
  });
});

syncDashboardStates();
