/**
 * app.js - Frontend Controller for GreenGraph Automator.
 * Interactive GitHub contribution heatmap visualizer and Git workflow controller.
 */

// Application State
const state = {
  presets: {},
  currentPreset: "progressive",
  yearConfigs: {},
  weekendWeight: 0.35,
  startYear: 2019,
  endDate: "2026-10-12",
  activeYearFilter: "all",
  gitInfo: {},
  simulation: null,
  isGenerating: false,
  pollTimer: null
};

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// DOM Elements
const el = {
  repoStatusPill: document.getElementById("repoStatusPill"),
  badgeRepoName: document.getElementById("badgeRepoName"),
  badgeBranchName: document.getElementById("badgeBranchName"),
  badgeCommitCount: document.getElementById("badgeCommitCount"),
  statTotalCommits: document.getElementById("statTotalCommits"),
  statYearlyAvg: document.getElementById("statYearlyAvg"),
  statActiveRate: document.getElementById("statActiveRate"),
  statActiveDays: document.getElementById("statActiveDays"),
  statMaxStreak: document.getElementById("statMaxStreak"),
  statBusiestCount: document.getElementById("statBusiestCount"),
  statBusiestDate: document.getElementById("statBusiestDate"),
  heatmapsContainer: document.getElementById("heatmapsContainer"),
  heatmapLoading: document.getElementById("heatmapLoading"),
  yearFilterTabs: document.getElementById("yearFilterTabs"),
  presetButtons: document.getElementById("presetButtons"),
  weekendWeightSlider: document.getElementById("weekendWeightSlider"),
  weekendWeightVal: document.getElementById("weekendWeightVal"),
  yearlyMatrixGrid: document.getElementById("yearlyMatrixGrid"),
  authorNameInput: document.getElementById("authorNameInput"),
  authorEmailInput: document.getElementById("authorEmailInput"),
  saveAuthorBtn: document.getElementById("saveAuthorBtn"),
  modeClean: document.getElementById("modeClean"),
  modeAppend: document.getElementById("modeAppend"),
  bypassHooksCheckbox: document.getElementById("bypassHooksCheckbox"),
  targetBranchInput: document.getElementById("targetBranchInput"),
  targetRemoteInput: document.getElementById("targetRemoteInput"),
  previewSimBtn: document.getElementById("previewSimBtn"),
  generateCommitsBtn: document.getElementById("generateCommitsBtn"),
  pushRemoteBtn: document.getElementById("pushRemoteBtn"),
  execStatusChip: document.getElementById("execStatusChip"),
  execStatusDesc: document.getElementById("execStatusDesc"),
  progressText: document.getElementById("progressText"),
  progressStats: document.getElementById("progressStats"),
  progressFill: document.getElementById("progressFill"),
  terminalLogs: document.getElementById("terminalLogs"),
  clearLogsBtn: document.getElementById("clearLogsBtn"),
  pushModal: document.getElementById("pushModal"),
  modalRemote: document.getElementById("modalRemote"),
  modalRemoteUrl: document.getElementById("modalRemoteUrl"),
  modalBranch: document.getElementById("modalBranch"),
  cancelPushBtn: document.getElementById("cancelPushBtn"),
  confirmPushBtn: document.getElementById("confirmPushBtn"),
  graphTooltip: document.getElementById("graphTooltip")
};

// ==========================================================================
// Initialization
// ==========================================================================

async function init() {
  setupEventListeners();
  await Promise.all([fetchGitStatus(), fetchPresets()]);
  buildYearlyMatrixInputs();
  await runSimulation();
}

async function fetchGitStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error("Failed to fetch git status");
    const data = await res.json();
    state.gitInfo = data;

    // Update UI elements
    const remote = data.remote_url || "";
    const repoSlug = remote ? remote.replace(/^.*github\.com[\/:]/, "").replace(/\.git$/, "") : "Local Git Repo";
    el.badgeRepoName.textContent = repoSlug;
    el.badgeBranchName.textContent = data.branch || "main";
    el.badgeCommitCount.textContent = (data.commit_count || 0).toLocaleString();

    if (data.user_name) el.authorNameInput.value = data.user_name;
    if (data.user_email) el.authorEmailInput.value = data.user_email;
    if (data.branch) el.targetBranchInput.value = data.branch;
  } catch (err) {
    console.error("Git status error:", err);
    el.badgeRepoName.textContent = "Offline / No Git";
  }
}

async function fetchPresets() {
  try {
    const res = await fetch("/api/presets");
    if (!res.ok) throw new Error("Failed to fetch presets");
    state.presets = await res.json();

    // Default to progressive
    const progressive = state.presets["progressive"];
    if (progressive) {
      state.yearConfigs = JSON.parse(JSON.stringify(progressive.years));
      state.weekendWeight = progressive.weekend_weight || 0.35;
      el.weekendWeightSlider.value = state.weekendWeight;
      el.weekendWeightVal.textContent = `${state.weekendWeight}x`;
    }
  } catch (err) {
    console.error("Presets fetch error:", err);
  }
}

// ==========================================================================
// Yearly Matrix UI Builder
// ==========================================================================

function buildYearlyMatrixInputs() {
  el.yearlyMatrixGrid.innerHTML = "";
  const years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];

  years.forEach(year => {
    const cfg = state.yearConfigs[year] || { active_day_pct: 50, min_commits: 1, max_commits: 3 };

    const card = document.createElement("div");
    card.className = "year-card";
    card.id = `yearCard-${year}`;

    card.innerHTML = `
      <div class="year-card-header">
        <span class="year-card-title">${year}</span>
        <span class="year-card-commits" id="yearBadge-${year}">-- commits</span>
      </div>
      <div>
        <div class="slider-label-group">
          <label style="font-size:0.75rem; color:var(--text-muted)">Active Days</label>
          <span class="slider-value" id="valActive-${year}">${cfg.active_day_pct}%</span>
        </div>
        <input type="range" class="year-active-slider" data-year="${year}" min="0" max="100" step="1" value="${cfg.active_day_pct}">
      </div>
      <div>
        <div class="slider-label-group">
          <label style="font-size:0.75rem; color:var(--text-muted)">Max Commits/Day</label>
          <span class="slider-value" id="valMaxCommits-${year}">${cfg.max_commits}</span>
        </div>
        <input type="range" class="year-commits-slider" data-year="${year}" min="1" max="12" step="1" value="${cfg.max_commits}">
      </div>
    `;

    el.yearlyMatrixGrid.appendChild(card);
  });

  // Attach input listeners with debounce
  document.querySelectorAll(".year-active-slider").forEach(slider => {
    slider.addEventListener("input", (e) => {
      const year = parseInt(e.target.dataset.year);
      const val = parseInt(e.target.value);
      document.getElementById(`valActive-${year}`).textContent = `${val}%`;
      if (!state.yearConfigs[year]) state.yearConfigs[year] = { min_commits: 1, max_commits: 3 };
      state.yearConfigs[year].active_day_pct = val;
      debouncedSimulate();
    });
  });

  document.querySelectorAll(".year-commits-slider").forEach(slider => {
    slider.addEventListener("input", (e) => {
      const year = parseInt(e.target.dataset.year);
      const val = parseInt(e.target.value);
      document.getElementById(`valMaxCommits-${year}`).textContent = `${val}`;
      if (!state.yearConfigs[year]) state.yearConfigs[year] = { active_day_pct: 50, min_commits: 1 };
      state.yearConfigs[year].max_commits = val;
      debouncedSimulate();
    });
  });
}

function updateMatrixInputsFromState() {
  const years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];
  years.forEach(year => {
    const cfg = state.yearConfigs[year] || { active_day_pct: 50, max_commits: 3 };
    const actSlider = document.querySelector(`.year-active-slider[data-year="${year}"]`);
    const comSlider = document.querySelector(`.year-commits-slider[data-year="${year}"]`);
    const actVal = document.getElementById(`valActive-${year}`);
    const comVal = document.getElementById(`valMaxCommits-${year}`);

    if (actSlider) actSlider.value = cfg.active_day_pct;
    if (comSlider) comSlider.value = cfg.max_commits;
    if (actVal) actVal.textContent = `${cfg.active_day_pct}%`;
    if (comVal) comVal.textContent = `${cfg.max_commits}`;
  });
}

// ==========================================================================
// Simulation & Heatmap Rendering
// ==========================================================================

let simTimeout = null;
function debouncedSimulate() {
  clearTimeout(simTimeout);
  simTimeout = setTimeout(() => {
    runSimulation();
  }, 200);
}

async function runSimulation() {
  try {
    el.heatmapLoading.style.display = "flex";
    const payload = {
      preset: state.currentPreset,
      weekend_weight: state.weekendWeight,
      start_year: state.startYear,
      end_date: state.endDate,
      years: state.yearConfigs
    };

    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error("Simulation calculation failed");
    const data = await res.json();
    state.simulation = data;

    renderStats(data);
    renderHeatmaps(data);
  } catch (err) {
    console.error("Simulation error:", err);
  } finally {
    el.heatmapLoading.style.display = "none";
  }
}

function renderStats(sim) {
  el.statTotalCommits.textContent = sim.total_commits.toLocaleString();
  const avgYear = Math.round(sim.total_commits / 8);
  el.statYearlyAvg.textContent = `~${avgYear.toLocaleString()} commits/year avg`;

  el.statActiveRate.textContent = `${sim.activity_percentage}%`;
  el.statActiveDays.textContent = `${sim.total_active_days.toLocaleString()} / ${sim.total_days.toLocaleString()} active days`;

  el.statMaxStreak.textContent = sim.max_streak;
  el.statBusiestCount.textContent = sim.busiest_day.commits;
  el.statBusiestDate.textContent = `on ${sim.busiest_day.date}`;

  // Update mini badges in the yearly matrix
  if (sim.year_stats) {
    Object.entries(sim.year_stats).forEach(([y, s]) => {
      const badge = document.getElementById(`yearBadge-${y}`);
      if (badge) {
        badge.textContent = `${s.total_commits.toLocaleString()} commits`;
      }
    });
  }
}

function renderHeatmaps(sim) {
  el.heatmapsContainer.innerHTML = "";
  const filter = state.activeYearFilter;

  // Group calendar days by year
  const daysByYear = {};
  sim.calendar.forEach(day => {
    if (!daysByYear[day.year]) daysByYear[day.year] = [];
    daysByYear[day.year].push(day);
  });

  const yearsToRender = filter === "all"
    ? Object.keys(daysByYear).map(Number).sort((a, b) => a - b)
    : [parseInt(filter)];

  yearsToRender.forEach(year => {
    const days = daysByYear[year] || [];
    const yearStat = sim.year_stats ? sim.year_stats[year] : null;
    const yearBlock = createYearHeatmapElement(year, days, yearStat);
    el.heatmapsContainer.appendChild(yearBlock);
  });
}

function createYearHeatmapElement(year, days, stat) {
  const container = document.createElement("div");
  container.className = "year-heatmap-block";

  const totalC = stat ? stat.total_commits.toLocaleString() : "0";
  const activeD = stat ? stat.active_days : "0";
  const totalD = stat ? stat.total_days : days.length;

  container.innerHTML = `
    <div class="year-heatmap-header">
      <span class="year-title">${year} Contribution Calendar</span>
      <span class="year-summary-badge">${totalC} commits • ${activeD}/${totalD} days active</span>
    </div>
    <div class="gh-graph-layout">
      <div class="gh-weekdays-col">
        <span></span>
        <span>Mon</span>
        <span></span>
        <span>Wed</span>
        <span></span>
        <span>Fri</span>
        <span></span>
      </div>
      <div class="gh-graph-scroll">
        <div class="gh-grid" id="grid-${year}"></div>
      </div>
    </div>
  `;

  const grid = container.querySelector(`#grid-${year}`);

  // Determine starting day of week for Jan 1
  if (days.length > 0) {
    const firstDate = new Date(days[0].date + "T00:00:00");
    // Standard Sunday=0, Monday=1, ... Saturday=6
    const firstDayOfWeek = firstDate.getDay(); 

    // Add empty placeholders before day 1 so columns align with Sunday
    for (let i = 0; i < firstDayOfWeek; i++) {
      const emptyCell = document.createElement("div");
      emptyCell.className = "gh-cell level-0";
      emptyCell.style.opacity = "0.2";
      emptyCell.style.pointerEvents = "none";
      grid.appendChild(emptyCell);
    }

    // Add actual days
    days.forEach(day => {
      const cell = document.createElement("div");
      cell.className = `gh-cell level-${day.level}`;
      cell.dataset.date = day.date;
      cell.dataset.commits = day.commits;
      cell.dataset.weekday = WEEKDAY_NAMES[day.weekday];

      cell.addEventListener("mouseenter", showTooltip);
      cell.addEventListener("mouseleave", hideTooltip);

      grid.appendChild(cell);
    });
  }

  return container;
}

// Tooltip Handlers
function showTooltip(e) {
  const cell = e.currentTarget;
  const dateStr = cell.dataset.date;
  const commits = cell.dataset.commits;
  const weekday = cell.dataset.weekday;

  const commitsText = commits === "1" ? "1 contribution" : `${commits} contributions`;
  el.graphTooltip.innerHTML = `<strong>${commitsText}</strong> on ${weekday}, ${dateStr}`;
  el.graphTooltip.style.display = "block";

  const rect = cell.getBoundingClientRect();
  el.graphTooltip.style.left = `${rect.left + rect.width / 2}px`;
  el.graphTooltip.style.top = `${rect.top - 6}px`;
}

function hideTooltip() {
  el.graphTooltip.style.display = "none";
}

// ==========================================================================
// Git Actions & Execution
// ==========================================================================

async function handleGenerate() {
  if (state.isGenerating) return;

  const authorName = el.authorNameInput.value.trim();
  const authorEmail = el.authorEmailInput.value.trim();
  const cleanSlate = el.modeClean.checked;
  const bypassHooks = el.bypassHooksCheckbox.checked;
  const branch = el.targetBranchInput.value.trim() || "main";

  if (!authorEmail) {
    alert("Please enter a valid Git author email address.");
    el.authorEmailInput.focus();
    return;
  }

  const promptMsg = cleanSlate
    ? `⚠️ CLEAN SLATE MODE:\nThis will create a safety backup tag and reset branch '${branch}' to generate ${state.simulation.total_commits.toLocaleString()} historical commits from 2019 to 2026.\n\nProceed?`
    : `APPEND MODE:\nThis will append ${state.simulation.total_commits.toLocaleString()} backdated commits to branch '${branch}'.\n\nProceed?`;

  if (!confirm(promptMsg)) return;

  try {
    state.isGenerating = true;
    updateExecStatus("running", "Generating backdated commits in background...");
    el.generateCommitsBtn.disabled = true;
    el.generateCommitsBtn.style.opacity = "0.6";

    const payload = {
      simulation: state.simulation,
      author_name: authorName,
      author_email: authorEmail,
      branch: branch,
      clean_slate: cleanSlate,
      bypass_hooks: bypassHooks
    };

    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || "Failed to start generation");
    }

    startProgressPolling();
  } catch (err) {
    console.error("Generate error:", err);
    updateExecStatus("error", err.message);
    state.isGenerating = false;
    el.generateCommitsBtn.disabled = false;
    el.generateCommitsBtn.style.opacity = "1";
  }
}

function startProgressPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);

  state.pollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/progress");
      if (!res.ok) return;
      const data = await res.json();

      // Update progress bar
      const pct = data.progress || 0;
      el.progressFill.style.width = `${pct}%`;
      el.progressText.textContent = `${pct.toFixed(1)}% Complete (Current: ${data.current_date || "Preparing..."})`;
      el.progressStats.textContent = `${data.commits_made.toLocaleString()} / ${data.total_commits.toLocaleString()} commits (${data.elapsed_sec || 0}s)`;

      // Update terminal logs
      if (data.logs && data.logs.length > 0) {
        el.terminalLogs.innerHTML = data.logs.map(line => `<div>${escapeHtml(line)}</div>`).join("");
        el.terminalLogs.scrollTop = el.terminalLogs.scrollHeight;
      }

      if (data.status === "completed") {
        clearInterval(state.pollTimer);
        state.isGenerating = false;
        el.generateCommitsBtn.disabled = false;
        el.generateCommitsBtn.style.opacity = "1";
        updateExecStatus("completed", `Generated ${data.result.commits_generated.toLocaleString()} commits in ${data.result.elapsed_seconds}s!`);
        fetchGitStatus();
      } else if (data.status === "error") {
        clearInterval(state.pollTimer);
        state.isGenerating = false;
        el.generateCommitsBtn.disabled = false;
        el.generateCommitsBtn.style.opacity = "1";
        updateExecStatus("error", `Error: ${data.error}`);
      }
    } catch (err) {
      console.error("Progress poll error:", err);
    }
  }, 400);
}

function updateExecStatus(status, desc) {
  el.execStatusChip.className = `status-chip ${status}`;
  el.execStatusChip.textContent = status.toUpperCase();
  el.execStatusDesc.textContent = desc;
}

// Modal & Force Push
function openPushModal() {
  el.modalRemote.textContent = el.targetRemoteInput.value.trim() || "origin";
  el.modalRemoteUrl.textContent = state.gitInfo.remote_url || "Remote URL";
  el.modalBranch.textContent = el.targetBranchInput.value.trim() || "main";
  el.pushModal.style.display = "flex";
}

function closePushModal() {
  el.pushModal.style.display = "none";
}

async function handleConfirmPush() {
  closePushModal();
  const remote = el.targetRemoteInput.value.trim() || "origin";
  const branch = el.targetBranchInput.value.trim() || "main";
  const bypassHooks = el.bypassHooksCheckbox.checked;

  try {
    updateExecStatus("running", `Pushing branch '${branch}' to remote '${remote}'...`);
    appendLog(`[Push] Initiating git push --force --no-verify ${remote} ${branch}...`);

    const res = await fetch("/api/push", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remote, branch, force: true, bypass_hooks: bypassHooks })
    });

    const data = await res.json();
    if (data.success) {
      updateExecStatus("completed", "Successfully pushed to GitHub!");
      appendLog(`[Push Success] Repository updated on remote. GitHub will calculate contributions within minutes.`);
      alert("Push successful! Check your GitHub profile contribution graph.");
    } else {
      updateExecStatus("error", "Push failed");
      appendLog(`[Push Error] ${data.stderr || data.stdout}`);
      alert(`Push failed:\n${data.stderr || data.stdout}`);
    }
  } catch (err) {
    updateExecStatus("error", err.message);
    appendLog(`[Push Error] ${err.message}`);
  }
}

async function handleSaveAuthor() {
  const name = el.authorNameInput.value.trim();
  const email = el.authorEmailInput.value.trim();
  if (!name || !email) return alert("Please provide both name and email.");

  try {
    const res = await fetch("/api/author", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email })
    });
    if (res.ok) {
      appendLog(`[Config] Saved git user.name="${name}" and user.email="${email}"`);
      alert("Author details saved to local Git configuration.");
      fetchGitStatus();
    }
  } catch (err) {
    alert("Error saving author details: " + err.message);
  }
}

function appendLog(msg) {
  const time = new Date().toTimeString().split(" ")[0];
  const line = document.createElement("div");
  line.textContent = `[${time}] ${msg}`;
  el.terminalLogs.appendChild(line);
  el.terminalLogs.scrollTop = el.terminalLogs.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ==========================================================================
// Event Listeners
// ==========================================================================

function setupEventListeners() {
  // Year Filter Tabs
  el.yearFilterTabs.addEventListener("click", (e) => {
    if (e.target.classList.contains("year-tab")) {
      document.querySelectorAll(".year-tab").forEach(t => t.classList.remove("active"));
      e.target.classList.add("active");
      state.activeYearFilter = e.target.dataset.year;
      if (state.simulation) renderHeatmaps(state.simulation);
    }
  });

  // Preset Buttons
  el.presetButtons.addEventListener("click", (e) => {
    const btn = e.target.closest(".preset-btn");
    if (!btn) return;
    document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    const presetKey = btn.dataset.preset;
    state.currentPreset = presetKey;
    const presetData = state.presets[presetKey];
    if (presetData) {
      state.yearConfigs = JSON.parse(JSON.stringify(presetData.years));
      state.weekendWeight = presetData.weekend_weight || 0.35;
      el.weekendWeightSlider.value = state.weekendWeight;
      el.weekendWeightVal.textContent = `${state.weekendWeight}x`;
      updateMatrixInputsFromState();
      runSimulation();
    }
  });

  // Weekend Weight Slider
  el.weekendWeightSlider.addEventListener("input", (e) => {
    const val = parseFloat(e.target.value);
    state.weekendWeight = val;
    el.weekendWeightVal.textContent = `${val}x`;
    debouncedSimulate();
  });

  // Buttons
  el.previewSimBtn.addEventListener("click", () => runSimulation());
  el.generateCommitsBtn.addEventListener("click", handleGenerate);
  el.pushRemoteBtn.addEventListener("click", openPushModal);
  el.saveAuthorBtn.addEventListener("click", handleSaveAuthor);
  el.cancelPushBtn.addEventListener("click", closePushModal);
  el.confirmPushBtn.addEventListener("click", handleConfirmPush);

  el.clearLogsBtn.addEventListener("click", () => {
    el.terminalLogs.innerHTML = '<div class="log-line text-muted">[Terminal cleared]</div>';
  });
}

// Launch
document.addEventListener("DOMContentLoaded", init);
