/**
 * Website Crawler Dashboard Client JS
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  let currentJobId = null;
  let currentPreset = "quick";
  let currentPage = 1;
  let currentLimit = 25;
  let totalPages = 1;
  let logEventSource = null;
  let autoRefreshInterval = null;

  // DOM Elements
  const statTotalJobs = document.getElementById("stat-total-jobs");
  const statActiveJobs = document.getElementById("stat-active-jobs");
  const statTotalPages = document.getElementById("stat-total-pages");
  const statTotalLinks = document.getElementById("stat-total-links");
  const activeJobsIcon = document.getElementById("active-jobs-icon");
  const activeJobsIdleIcon = document.getElementById("active-jobs-idle-icon");

  const jobsListContainer = document.getElementById("jobs-list-container");
  const jobsCountTag = document.getElementById("jobs-count-tag");
  const btnRefreshAll = document.getElementById("btn-refresh-all");

  const jobHeaderCard = document.getElementById("job-header-card");
  const currentJobStatus = document.getElementById("current-job-status");
  const currentJobJsPill = document.getElementById("current-job-js-pill");
  const currentJobUrl = document.getElementById("current-job-url");
  const btnStopJob = document.getElementById("btn-stop-job");
  const btnDeleteJob = document.getElementById("btn-delete-job");
  const btnToggleLog = document.getElementById("btn-toggle-log");
  const toastEl = document.getElementById("toast");

  const jobStatPages = document.getElementById("job-stat-pages");
  const jobStatWords = document.getElementById("job-stat-words");
  const jobStatLinks = document.getElementById("job-stat-links");
  const jobStatRequests = document.getElementById("job-stat-requests");

  const consoleDrawer = document.getElementById("console-drawer");
  const consoleOutput = document.getElementById("console-output");
  const btnCloseConsole = document.getElementById("btn-close-console");

  const inputSearch = document.getElementById("input-search");
  const selectStatusFilter = document.getElementById("select-status-filter");
  const btnExportMenu = document.getElementById("btn-export-menu");
  const exportDropdownContent = document.getElementById("export-dropdown-content");
  const exportCsv = document.getElementById("export-csv");
  const exportJson = document.getElementById("export-json");

  const tableBody = document.getElementById("table-body");
  const paginationInfo = document.getElementById("pagination-info");
  const currentPageLabel = document.getElementById("current-page-label");
  const btnPrevPage = document.getElementById("btn-prev-page");
  const btnNextPage = document.getElementById("btn-next-page");

  // Modal Elements
  const crawlModal = document.getElementById("crawl-modal");
  const btnNewCrawlModal = document.getElementById("btn-new-crawl-modal");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnCancelModal = document.getElementById("btn-cancel-modal");
  const formNewCrawl = document.getElementById("form-new-crawl");
  const inputTargetUrl = document.getElementById("input-target-url");
  const inputJobName = document.getElementById("input-job-name");
  const customSettingsPanel = document.getElementById("custom-settings-panel");
  const presetCards = document.querySelectorAll(".preset-card");

  const inputMaxPages = document.getElementById("input-max-pages");
  const inputMaxDepth = document.getElementById("input-max-depth");
  const inputMinutes = document.getElementById("input-minutes");
  const inputDelay = document.getElementById("input-delay");
  const checkSitemap = document.getElementById("check-sitemap");
  const checkRenderJs = document.getElementById("check-render-js");

  // Detail Modal Elements
  const detailModal = document.getElementById("detail-modal");
  const btnCloseDetail = document.getElementById("btn-close-detail");
  const detailTitle = document.getElementById("detail-title");
  const detailUrl = document.getElementById("detail-url");
  const detailFoundOn = document.getElementById("detail-found-on");
  const detailStatus = document.getElementById("detail-status");
  const detailWords = document.getElementById("detail-words");
  const detailLinks = document.getElementById("detail-links");
  const detailDesc = document.getElementById("detail-desc");
  const detailHeadings = document.getElementById("detail-headings");
  const detailText = document.getElementById("detail-text");

  // Delete Confirmation Modal Elements
  const modalConfirmDelete = document.getElementById("modal-confirm-delete");
  const btnCancelDelete = document.getElementById("btn-cancel-delete");
  const btnCancelDeleteX = document.getElementById("btn-cancel-delete-x");
  const btnConfirmDeleteAction = document.getElementById("btn-confirm-delete-action");
  const deleteJobTargetName = document.getElementById("delete-job-target-name");
  let pendingDeleteJobId = null;
  let lastJobsState = "";

  // Crawled titles/URLs are untrusted: escape before putting them in innerHTML.
  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  // --- Toast Notification Helper ---
  let toastTimer = null;
  function showToast(message, type = "info") {
    if (!toastEl) return;
    toastEl.className = `toast-notification ${type}`;
    const iconClass = type === "success" ? "fa-circle-check" : type === "error" ? "fa-circle-xmark" : "fa-circle-info";
    toastEl.innerHTML = `<i class="fa-solid ${iconClass}"></i><span>${esc(message)}</span>`;
    toastEl.style.display = "flex";

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.style.display = "none";
    }, 3000);
  }

  // --- API Functions ---

  async function fetchOverviewStats() {
    try {
      const res = await fetch("/api/stats/overview");
      const data = await res.json();
      statTotalJobs.textContent = data.total_jobs || 0;
      statActiveJobs.textContent = data.active_jobs || 0;
      statTotalPages.textContent = (data.total_pages || 0).toLocaleString();
      statTotalLinks.textContent = (data.total_links || 0).toLocaleString();

      if (data.active_jobs > 0) {
        activeJobsIcon.style.display = "inline-block";
        activeJobsIdleIcon.style.display = "none";
      } else {
        activeJobsIcon.style.display = "none";
        activeJobsIdleIcon.style.display = "inline-block";
      }
    } catch (err) {
      console.error("Failed to fetch overview stats:", err);
    }
  }

  async function fetchJobsList() {
    try {
      const res = await fetch("/api/jobs");
      const data = await res.json();
      renderJobsList(data.jobs || []);
    } catch (err) {
      console.error("Failed to fetch jobs list:", err);
    }
  }

  function renderJobsList(jobs) {
    jobsCountTag.textContent = jobs.length;
    if (jobs.length === 0) {
      lastJobsState = "empty";
      jobsListContainer.innerHTML = `
        <div class="empty-jobs">
          <i class="fa-solid fa-inbox"></i>
          <p>No crawl jobs found.<br>Click "New Crawl" to start!</p>
        </div>`;
      return;
    }

    const stateKey = JSON.stringify(jobs.map((j) => ({ id: j.job_id, s: j.status, p: j.pages_saved, a: j.job_id === currentJobId })));
    if (stateKey === lastJobsState) {
      return; // DOM is already up to date, do not recreate elements
    }
    lastJobsState = stateKey;

    jobsListContainer.innerHTML = jobs
      .map((job) => {
        const isActive = job.job_id === currentJobId ? "active" : "";
        const statusClass = (job.status || "idle").toLowerCase();
        const dateStr = new Date(job.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        const jsBadge = job.render_js ? `<span class="badge-js" title="JavaScript rendering enabled"><i class="fa-brands fa-js"></i> JS</span>` : "";
        return `
        <div class="job-item ${isActive}" data-job-id="${esc(job.job_id)}">
          <div class="job-item-header">
            <span class="job-item-id" title="${esc(job.job_id)}">${esc(job.job_id)}</span>
            <div class="job-item-actions">
              ${jsBadge}
              <span class="status-badge ${esc(statusClass)}">${esc(job.status)}</span>
              <button class="job-item-delete" title="Delete job" data-delete-id="${esc(job.job_id)}">
                <i class="fa-solid fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="job-item-url" title="${esc(job.seed_url)}">${esc(job.seed_url)}</div>
          <div class="job-item-footer">
            <span><i class="fa-solid fa-file"></i> ${job.pages_saved || 0} pages</span>
            <span><i class="fa-regular fa-clock"></i> ${dateStr}</span>
          </div>
        </div>`;
      })
      .join("");
  }

  // Delegated event listener for sidebar jobs - reliable, never drops clicks on re-render
  jobsListContainer.addEventListener("click", (e) => {
    const deleteBtn = e.target.closest(".job-item-delete");
    if (deleteBtn) {
      e.stopPropagation();
      const jId = deleteBtn.getAttribute("data-delete-id");
      openDeleteConfirmModal(jId);
      return;
    }

    const jobItem = e.target.closest(".job-item");
    if (jobItem) {
      const jId = jobItem.getAttribute("data-job-id");
      selectJob(jId);
    }
  });

  async function selectJob(jobId) {
    currentJobId = jobId;
    currentPage = 1;

    // Fast active highlight without triggering network calls
    document.querySelectorAll(".job-item").forEach((el) => {
      if (el.getAttribute("data-job-id") === jobId) {
        el.classList.add("active");
      } else {
        el.classList.remove("active");
      }
    });

    jobHeaderCard.style.display = "flex";
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      const data = await res.json();
      
      currentJobUrl.textContent = data.seed_url || jobId;
      currentJobStatus.textContent = data.status.toUpperCase();
      currentJobStatus.className = `job-status-pill status-badge ${data.status.toLowerCase()}`;
      if (currentJobJsPill) {
        currentJobJsPill.style.display = data.render_js ? "inline-flex" : "none";
      }

      jobStatPages.textContent = data.pages_saved || 0;
      jobStatWords.textContent = (data.total_words || 0).toLocaleString();
      jobStatLinks.textContent = (data.total_links || 0).toLocaleString();
      jobStatRequests.textContent = data.summary?.requests_sent || 0;

      if (data.status === "running") {
        btnStopJob.style.display = "inline-flex";
        startLogStream(jobId);
      } else {
        btnStopJob.style.display = "none";
        if (logEventSource) {
          logEventSource.close();
          logEventSource = null;
        }
        if (data.recent_logs) {
          consoleOutput.textContent = data.recent_logs;
        }
      }

      fetchJobResults();
    } catch (err) {
      console.error("Error selecting job:", err);
    }
  }

  async function fetchJobResults() {
    if (!currentJobId) return;

    const search = inputSearch.value.trim();
    const status = selectStatusFilter.value;
    const url = `/api/jobs/${encodeURIComponent(currentJobId)}/results?page=${currentPage}&limit=${currentLimit}&search=${encodeURIComponent(search)}${status ? '&status_code=' + status : ''}`;

    try {
      const res = await fetch(url);
      const data = await res.json();
      renderResultsTable(data.items || []);

      totalPages = data.total_pages || 1;
      const startCount = data.total > 0 ? (currentPage - 1) * currentLimit + 1 : 0;
      const endCount = Math.min(currentPage * currentLimit, data.total);
      
      paginationInfo.textContent = `Showing ${startCount} - ${endCount} of ${data.total} pages`;
      currentPageLabel.textContent = `Page ${currentPage} of ${totalPages}`;

      btnPrevPage.disabled = currentPage <= 1;
      btnNextPage.disabled = currentPage >= totalPages;
    } catch (err) {
      console.error("Error fetching results:", err);
    }
  }

  function renderResultsTable(items) {
    if (items.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-5">
            <i class="fa-solid fa-circle-exclamation text-muted mb-2"></i><br>
            No results found for this job.
          </td>
        </tr>`;
      return;
    }

    tableBody.innerHTML = items
      .map((item, index) => {
        const status = item.status || 200;
        let statusTagClass = "s200";
        if (status >= 400 && status < 500) statusTagClass = "s404";
        if (status >= 500) statusTagClass = "s500";

        const title = item.title || "Untitled Page";
        const dateStr = item.crawled_at ? new Date(item.crawled_at).toLocaleTimeString() : "N/A";

        return `
        <tr>
          <td><span class="status-tag ${statusTagClass}">${esc(status)}</span></td>
          <td class="font-weight-600" title="${esc(title)}">${esc(title.substring(0, 60))}${title.length > 60 ? '...' : ''}</td>
          <td><a href="${esc(item.url)}" target="_blank" rel="noopener" class="url-link" title="${esc(item.url)}">${esc(item.url)}</a></td>
          <td>${esc(item.word_count || 0)}</td>
          <td>${esc(item.links_found || 0)}</td>
          <td class="text-muted">${dateStr}</td>
          <td>
            <button class="btn btn-outline btn-sm btn-view-detail" data-index="${index}">
              <i class="fa-solid fa-eye"></i> Details
            </button>
          </td>
        </tr>`;
      })
      .join("");

    // Attach click listener for details
    document.querySelectorAll(".btn-view-detail").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.getAttribute("data-index"), 10);
        showPageDetail(items[idx]);
      });
    });
  }

  function showPageDetail(item) {
    detailTitle.textContent = item.title || "Untitled Page";
    detailUrl.textContent = item.url;
    detailUrl.href = item.url;
    detailFoundOn.textContent = item.found_on || "(start page)";
    detailFoundOn.href = item.found_on || "#";
    detailStatus.textContent = item.status || 200;
    detailWords.textContent = item.word_count || 0;
    detailLinks.textContent = item.links_found || 0;
    detailDesc.textContent = item.description || "None specified.";
    detailText.textContent = item.text || "No text content extracted.";

    detailHeadings.innerHTML = "";
    if (item.headings && item.headings.length > 0) {
      item.headings.forEach((h) => {
        const li = document.createElement("li");
        li.textContent = h;
        detailHeadings.appendChild(li);
      });
    } else {
      detailHeadings.innerHTML = "<li class='text-muted'>No H1/H2 headings found.</li>";
    }

    detailModal.style.display = "flex";
  }

  function startLogStream(jobId) {
    if (logEventSource) {
      logEventSource.close();
    }
    consoleOutput.textContent = "Connecting to live log stream...\n";
    logEventSource = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/logs`);

    logEventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.line) {
          consoleOutput.textContent += data.line + "\n";
          consoleOutput.scrollTop = consoleOutput.scrollHeight;
        }
        if (data.done) {
          logEventSource.close();
          logEventSource = null;
        }
      } catch (err) {}
    };

    logEventSource.onerror = () => {
      if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
      }
    };
  }

  // --- Event Listeners & Preset Handling ---

  presetCards.forEach((card) => {
    card.addEventListener("click", () => {
      presetCards.forEach((c) => c.classList.remove("active"));
      card.classList.add("active");
      currentPreset = card.getAttribute("data-preset");

      if (currentPreset === "quick") {
        customSettingsPanel.style.display = "none";
        inputMaxPages.value = 100;
        inputMaxDepth.value = 3;
        inputMinutes.value = 5;
        inputDelay.value = 1.0;
      } else if (currentPreset === "deep") {
        customSettingsPanel.style.display = "none";
        inputMaxPages.value = 1000;
        inputMaxDepth.value = 8;
        inputMinutes.value = 60;
        inputDelay.value = 1.0;
      } else {
        customSettingsPanel.style.display = "block";
      }
    });
  });

  btnNewCrawlModal.addEventListener("click", () => {
    crawlModal.style.display = "flex";
  });

  const closeModal = () => (crawlModal.style.display = "none");
  btnCloseModal.addEventListener("click", closeModal);
  btnCancelModal.addEventListener("click", closeModal);

  btnCloseDetail.addEventListener("click", () => (detailModal.style.display = "none"));

  formNewCrawl.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = inputTargetUrl.value.trim();
    if (!url) return;

    const payload = {
      url: url,
      job_name: inputJobName.value.trim() || null,
      preset: currentPreset,
      max_pages: parseInt(inputMaxPages.value, 10),
      max_depth: parseInt(inputMaxDepth.value, 10),
      minutes: parseFloat(inputMinutes.value),
      delay: parseFloat(inputDelay.value),
      concurrency: 1,
      use_sitemap: checkSitemap.checked,
      render_js: checkRenderJs ? checkRenderJs.checked : false,
    };

    try {
      const res = await fetch("/api/jobs/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (res.ok) {
        closeModal();
        inputTargetUrl.value = "";
        inputJobName.value = "";
        if (checkRenderJs) checkRenderJs.checked = false;
        fetchOverviewStats();
        selectJob(data.job_id);
      } else {
        alert("Error starting crawl: " + (data.detail || "Unknown error"));
      }
    } catch (err) {
      alert("Failed to connect to server: " + err.message);
    }
  });

  btnStopJob.addEventListener("click", async () => {
    if (!currentJobId) return;
    if (confirm(`Stop crawl job '${currentJobId}'?`)) {
      try {
        await fetch(`/api/jobs/${encodeURIComponent(currentJobId)}/stop`, { method: "POST" });
        showToast(`Job '${currentJobId}' stopped.`, "info");
        selectJob(currentJobId);
        fetchOverviewStats();
      } catch (err) {
        showToast("Error stopping job: " + err.message, "error");
      }
    }
  });

  // Live Console Drawer Toggle
  if (btnToggleLog) {
    btnToggleLog.addEventListener("click", () => {
      if (!consoleDrawer) return;
      const isHidden = consoleDrawer.style.display === "none" || !consoleDrawer.style.display;
      if (isHidden) {
        consoleDrawer.style.display = "flex";
        if (currentJobId) {
          startLogStream(currentJobId);
        } else {
          consoleOutput.textContent = "Select a crawl job to view live logs.";
        }
      } else {
        consoleDrawer.style.display = "none";
      }
    });
  }

  if (btnCloseConsole) {
    btnCloseConsole.addEventListener("click", () => {
      if (consoleDrawer) consoleDrawer.style.display = "none";
    });
  }

  // Export Dropdown
  if (btnExportMenu) {
    btnExportMenu.addEventListener("click", (e) => {
      e.stopPropagation();
      const parent = btnExportMenu.closest(".export-dropdown") || (exportDropdownContent ? exportDropdownContent.parentElement : null);
      if (parent) parent.classList.toggle("show");
    });
  }

  document.addEventListener("click", () => {
    const parent = exportDropdownContent ? exportDropdownContent.parentElement : null;
    if (parent) parent.classList.remove("show");
  });

  if (exportCsv) {
    exportCsv.addEventListener("click", (e) => {
      e.preventDefault();
      if (!currentJobId) return showToast("Select a crawl job first!", "error");
      window.location.href = `/api/jobs/${encodeURIComponent(currentJobId)}/export?format=csv`;
    });
  }

  if (exportJson) {
    exportJson.addEventListener("click", (e) => {
      e.preventDefault();
      if (!currentJobId) return showToast("Select a crawl job first!", "error");
      window.location.href = `/api/jobs/${encodeURIComponent(currentJobId)}/export?format=json`;
    });
  }

  // Table Filters & Pagination
  if (inputSearch) {
    inputSearch.addEventListener("input", () => {
      currentPage = 1;
      fetchJobResults();
    });
  }

  if (selectStatusFilter) {
    selectStatusFilter.addEventListener("change", () => {
      currentPage = 1;
      fetchJobResults();
    });
  }

  if (btnPrevPage) {
    btnPrevPage.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        fetchJobResults();
      }
    });
  }

  if (btnNextPage) {
    btnNextPage.addEventListener("click", () => {
      if (currentPage < totalPages) {
        currentPage++;
        fetchJobResults();
      }
    });
  }

  // Delete Confirmation Modal Handling
  function openDeleteConfirmModal(jobId) {
    if (!jobId) return;
    pendingDeleteJobId = jobId;
    if (deleteJobTargetName) deleteJobTargetName.textContent = jobId;
    if (modalConfirmDelete) modalConfirmDelete.style.display = "flex";
  }

  function closeDeleteConfirmModal() {
    if (modalConfirmDelete) modalConfirmDelete.style.display = "none";
    pendingDeleteJobId = null;
    if (btnConfirmDeleteAction) {
      btnConfirmDeleteAction.disabled = false;
      btnConfirmDeleteAction.innerHTML = '<i class="fa-solid fa-trash"></i> Delete Permanently';
    }
  }

  if (btnCancelDelete) btnCancelDelete.addEventListener("click", closeDeleteConfirmModal);
  if (btnCancelDeleteX) btnCancelDeleteX.addEventListener("click", closeDeleteConfirmModal);

  if (btnConfirmDeleteAction) {
    btnConfirmDeleteAction.addEventListener("click", async () => {
      if (!pendingDeleteJobId) return;
      const jobId = pendingDeleteJobId;

      btnConfirmDeleteAction.disabled = true;
      btnConfirmDeleteAction.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Deleting...';

      // 1. Immediately terminate SSE log stream to release file locks on Windows
      if (currentJobId === jobId && logEventSource) {
        logEventSource.close();
        logEventSource = null;
      }

      try {
        const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
          method: "DELETE",
        });
        const data = await res.json();

        if (res.ok) {
          closeDeleteConfirmModal();
          showToast(data.message || `Job '${jobId}' deleted.`, "success");

          if (currentJobId === jobId) {
            currentJobId = null;
            jobHeaderCard.style.display = "none";
            consoleDrawer.style.display = "none";
            tableBody.innerHTML = `
              <tr>
                <td colspan="7" class="text-center py-5">Select a crawl job from the left sidebar to explore extracted web data.</td>
              </tr>`;
            paginationInfo.textContent = "Showing 0 - 0 of 0 pages";
            currentPageLabel.textContent = "Page 1 of 1";
            btnPrevPage.disabled = true;
            btnNextPage.disabled = true;
          }

          lastJobsState = ""; // Reset cache to force immediate redraw
          await fetchJobsList();
          await fetchOverviewStats();
        } else {
          btnConfirmDeleteAction.disabled = false;
          btnConfirmDeleteAction.innerHTML = '<i class="fa-solid fa-trash"></i> Delete Permanently';
          showToast("Failed to delete: " + (data.detail || "Server error"), "error");
        }
      } catch (err) {
        btnConfirmDeleteAction.disabled = false;
        btnConfirmDeleteAction.innerHTML = '<i class="fa-solid fa-trash"></i> Delete Permanently';
        showToast("Network error deleting job: " + err.message, "error");
      }
    });
  }

  if (btnDeleteJob) {
    btnDeleteJob.addEventListener("click", () => {
      if (currentJobId) openDeleteConfirmModal(currentJobId);
    });
  }

  btnRefreshAll.addEventListener("click", async () => {
    const icon = btnRefreshAll.querySelector("i");
    if (icon) icon.classList.add("fa-spin");
    btnRefreshAll.disabled = true;

    try {
      await fetchOverviewStats();
      await fetchJobsList();
      if (currentJobId) {
        await selectJob(currentJobId);
        await fetchJobResults();
      }
      showToast("Dashboard refreshed successfully!", "success");
    } catch (err) {
      showToast("Failed to refresh: " + err.message, "error");
    } finally {
      setTimeout(() => {
        if (icon) icon.classList.remove("fa-spin");
        btnRefreshAll.disabled = false;
      }, 400);
    }
  });

  // --- Version & Updates ---
  const appVersion = document.getElementById("app-version");
  const btnCheckUpdate = document.getElementById("btn-check-update");
  let runningVersion = null;

  fetch("/api/version")
    .then((res) => res.json())
    .then((data) => {
      runningVersion = data.version;
      appVersion.textContent = `v${data.version}`;
    })
    .catch(() => {});

  // After an install the server restarts; reload once the new version answers.
  function reloadWhenUpdated() {
    setInterval(async () => {
      try {
        const data = await (await fetch("/api/version")).json();
        if (data.version !== runningVersion) location.reload();
      } catch (err) {} // server is down mid-update
    }, 2000);
  }

  btnCheckUpdate.addEventListener("click", async () => {
    const original = btnCheckUpdate.innerHTML;
    let installing = false;
    btnCheckUpdate.disabled = true;
    btnCheckUpdate.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking...';
    try {
      const res = await fetch("/api/update/check");
      const data = await res.json();
      if (!res.ok) return showToast("Update check failed: " + (data.detail || "Server error"), "error");
      if (!data.update_available) return showToast(`You're on the latest version (v${data.current_version}).`, "success");

      const question = `Version ${data.latest_version} is available (you have ${data.current_version}).`;
      if (!data.can_self_update || !data.download_url) {
        if (confirm(`${question}\n\nOpen the download page?`)) window.open(data.release_url, "_blank", "noopener");
        return;
      }
      if (!confirm(`${question}\n\nDownload and install it now? The dashboard will restart.`)) return;

      btnCheckUpdate.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Installing...';
      const install = await fetch("/api/update/install", { method: "POST" });
      const result = await install.json();
      if (!install.ok) return showToast("Update failed: " + (result.detail || "Server error"), "error");
      installing = true; // keep the button disabled until the page reloads
      showToast(result.message, "info");
      reloadWhenUpdated();
    } catch (err) {
      showToast("Update check failed: " + err.message, "error");
    } finally {
      if (!installing) {
        btnCheckUpdate.disabled = false;
        btnCheckUpdate.innerHTML = original;
      }
    }
  });

  // Initial Load & Auto-polling
  fetchOverviewStats();
  fetchJobsList();

  autoRefreshInterval = setInterval(() => {
    fetchOverviewStats();
    fetchJobsList();
    if (currentJobId) {
      // Lightly refresh job detail
      fetch(`/api/jobs/${currentJobId}`)
        .then((res) => res.json())
        .then((data) => {
          currentJobStatus.textContent = data.status.toUpperCase();
          currentJobStatus.className = `job-status-pill status-badge ${data.status.toLowerCase()}`;
          jobStatPages.textContent = data.pages_saved || 0;
          jobStatWords.textContent = (data.total_words || 0).toLocaleString();
          jobStatLinks.textContent = (data.total_links || 0).toLocaleString();

          if (data.status !== "running" && btnStopJob.style.display !== "none") {
            btnStopJob.style.display = "none";
          }
        });
    }
  }, 4000);
});
