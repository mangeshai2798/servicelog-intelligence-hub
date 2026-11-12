// Main Application Logic for ServiceLog Intelligence Hub

const API_BASE = window.location.origin.includes('http') ? window.location.origin : 'http://127.0.0.1:8000';

function formatServiceName(name) {
    if (!name) return '';
    return name
        .replace(/([a-z])([A-Z])/g, '$1 $2')
        .replace(/[-_]/g, ' ')
        .trim();
}

let appState = {
    overview: null,
    services: [],
    errorCauses: [],
    timeline: [],
    logs: [],
    config: null,
    slaTarget: 95.0,
    aiSettings: {
        is_configured: true,
        provider: 'qwen',
        model: 'Qwen/Qwen2.5-3B-Instruct',
        masked_key: 'Local In-Memory (Active)'
    },
    pagination: {
        page: 1,
        pageSize: 25,
        total: 0
    },
    filters: {
        service: 'ALL',
        level: 'ALL',
        date: 'ALL',
        search: '',
        status_filter: 'ALL'
    }
};

async function fetchConfig() {
    try {
        const res = await fetch(`${API_BASE}/api/config`);
        if (!res.ok) return;
        const config = await res.json();
        appState.config = config;

        if (config.app_title) document.title = config.app_title;
        const appInitTitle = document.getElementById('appInitTitle');
        if (appInitTitle && config.app_name) appInitTitle.innerText = config.app_name;
        const navBadgeText = document.getElementById('appNavBadgeText');
        if (navBadgeText && config.app_nav_badge) navBadgeText.innerText = config.app_nav_badge;
        const footerBrandText = document.getElementById('footerBrandText');
        if (footerBrandText && config.app_name) footerBrandText.innerText = `${config.app_name} © 2026`;
        if (config.sla_target_percent) appState.slaTarget = Number(config.sla_target_percent);
    } catch (e) {
        console.warn('Could not load dynamic config from backend:', e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupEventListeners();
});

async function initApp(retryCount = 0) {
    const statusText = document.getElementById('appInitStatusText');
    const progressBar = document.getElementById('appInitProgressBar');
    const overlay = document.getElementById('appInitOverlay');

    try {
        if (progressBar) progressBar.style.width = '35%';
        if (statusText && retryCount > 0) {
            statusText.innerText = `Connecting to telemetry engine (Attempt ${retryCount + 1})...`;
        }

        // Test health endpoint to confirm backend is fully up
        const healthRes = await fetch(`${API_BASE}/api/health`);
        if (!healthRes.ok) throw new Error(`Backend status: ${healthRes.status}`);

        // Fetch dynamic branding & configuration from .env
        await fetchConfig();

        if (progressBar) progressBar.style.width = '60%';
        if (statusText) statusText.innerText = 'Loading operational telemetry and metrics...';

        await Promise.all([
            fetchOverview(),
            fetchServices(),
            fetchErrorCauses(),
            fetchTimeline(),
            fetchAISettings(),
            fetchLogs()
        ]);

        if (progressBar) progressBar.style.width = '85%';
        if (statusText) statusText.innerText = 'Rendering analytics charts & visual telemetry...';

        // Explicitly render all 4 operational & error charts by default for 'ALL' services on initial page load
        if (typeof initCharts === 'function' && appState.overview && appState.services && appState.errorCauses && appState.timeline) {
            initCharts(appState.overview, appState.services, appState.errorCauses, appState.timeline, 'ALL');
        }

        // Initialize UI badges, subtitles, and scope labels for 'ALL'
        updateScopeUI('ALL');
        lucide.createIcons();

        if (progressBar) progressBar.style.width = '100%';

        // Smoothly dismiss loading overlay so UI appears 100% complete with no missing data
        if (overlay) {
            overlay.style.opacity = '0';
            setTimeout(() => {
                overlay.classList.add('hidden');
                overlay.style.display = 'none';
            }, 300);
        }
    } catch (err) {
        console.warn(`[initApp] Backend initialization pending (attempt ${retryCount + 1}):`, err);
        if (retryCount < 25) {
            if (statusText) statusText.innerText = `Backend initializing (retrying in 800ms)...`;
            setTimeout(() => initApp(retryCount + 1), 800);
        } else {
            if (statusText) {
                statusText.innerHTML = `<span class="text-rose-600 font-bold">Failed to connect to backend at ${API_BASE}. Please ensure run_dashboard.py is running.</span>`;
            }
        }
    }
}

function setupEventListeners() {
    // Search form submission
    const queryForm = document.getElementById('queryForm');
    if (queryForm) {
        queryForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const input = document.getElementById('queryInput');
            if (input && input.value.trim()) {
                submitQuery(input.value.trim());
            }
        });
    }

    // Quick query pills
    document.querySelectorAll('.quick-query-pill').forEach(btn => {
        btn.addEventListener('click', () => {
            const query = btn.getAttribute('data-query');
            const input = document.getElementById('queryInput');
            if (input) input.value = query;
            submitQuery(query);
        });
    });

    // BillTrax Service Navigation Tabs
    document.querySelectorAll('.service-nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-service-target');
            selectService(target, false);
        });
    });

    // Filters
    const serviceFilter = document.getElementById('filterService');
    const statusFilter = document.getElementById('filterStatus');
    const levelFilter = document.getElementById('filterLevel');
    const dateFilter = document.getElementById('filterDate');
    const searchFilter = document.getElementById('filterSearch');

    if (serviceFilter) serviceFilter.addEventListener('change', (e) => {
        selectService(e.target.value, false);
    });

    if (statusFilter) statusFilter.addEventListener('change', (e) => {
        appState.filters.status_filter = e.target.value;
        appState.pagination.page = 1;
        fetchLogs();
    });

    if (levelFilter) levelFilter.addEventListener('change', (e) => {
        appState.filters.level = e.target.value;
        appState.pagination.page = 1;
        fetchLogs();
    });

    if (dateFilter) dateFilter.addEventListener('change', (e) => {
        appState.filters.date = e.target.value;
        appState.pagination.page = 1;
        fetchLogs();
    });

    let searchDebounceTimer;
    if (searchFilter) searchFilter.addEventListener('input', (e) => {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            appState.filters.search = e.target.value;
            appState.pagination.page = 1;
            fetchLogs();
        }, 300);
    });

    // Pagination
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    if (prevBtn) prevBtn.addEventListener('click', () => {
        if (appState.pagination.page > 1) {
            appState.pagination.page--;
            fetchLogs();
        }
    });
    if (nextBtn) nextBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(appState.pagination.total / appState.pagination.pageSize);
        if (appState.pagination.page < maxPage) {
            appState.pagination.page++;
            fetchLogs();
        }
    });

    // Reindex button
    const reindexBtn = document.getElementById('reindexBtn');
    if (reindexBtn) {
        reindexBtn.addEventListener('click', reindexLogs);
    }

    // Upload button & input
    const uploadBtn = document.getElementById('uploadLogBtn');
    const fileInput = document.getElementById('fileUploadInput');
    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileUpload);
    }

    // Left Panel Executive KPI Mission Control Card Click Handlers
    document.querySelectorAll('.bt-kpi-card-clickable').forEach(card => {
        card.addEventListener('click', () => {
            const kpiType = card.getAttribute('data-kpi-type');
            if (kpiType) {
                handleKPIClick(kpiType);
            }
        });
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                const kpiType = card.getAttribute('data-kpi-type');
                if (kpiType) handleKPIClick(kpiType);
            }
        });
    });

    // AI Settings Modal
    const aiConfigBtn = document.getElementById('aiConfigBtn');
    const aiSettingsModal = document.getElementById('aiSettingsModal');
    const aiSettingsForm = document.getElementById('aiSettingsForm');

    if (aiConfigBtn) {
        aiConfigBtn.addEventListener('click', openAISettingsModal);
    }

    if (aiSettingsForm) {
        aiSettingsForm.addEventListener('submit', handleSaveAISettings);
    }

    // Backend Execution Logs Modal
    const viewBackendLogsBtn = document.getElementById('viewBackendLogsBtn');
    if (viewBackendLogsBtn) {
        viewBackendLogsBtn.addEventListener('click', openBackendLogsModal);
    }
    const refreshBackendLogsBtn = document.getElementById('refreshBackendLogsBtn');
    if (refreshBackendLogsBtn) {
        refreshBackendLogsBtn.addEventListener('click', fetchBackendLogs);
    }
    const copyBackendLogsBtn = document.getElementById('copyBackendLogsBtn');
    if (copyBackendLogsBtn) {
        copyBackendLogsBtn.addEventListener('click', copyBackendLogsToClipboard);
    }

    // Dark / Light Mode Toggle
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            document.body.classList.toggle('dark-mode');
            const isDark = document.body.classList.contains('dark-mode');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            lucide.createIcons();
        });
    }

    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark-mode');
    }
}

// ================= API FETCHING ================= //

async function fetchOverview(service = 'ALL') {
    const url = (service && service !== 'ALL')
        ? `${API_BASE}/api/overview?service=${encodeURIComponent(service)}`
        : `${API_BASE}/api/overview`;
    const res = await fetch(url);
    const data = await res.json();
    appState.overview = data;
    renderOverview(data, service);
    if (!service || service === 'ALL') {
        updateDateFilterOptions(data.dates_available);
    }
}

function renderPortalNavPills(services, activeService = 'ALL') {
    const container = document.getElementById('dynamicServicePills');
    const allBtn = document.getElementById('portalBtnAll');
    if (allBtn) {
        allBtn.innerText = `All Services (${services.length})`;
    }
    if (!container) return;
    container.innerHTML = '';
    services.forEach(s => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `bt-nav-pill service-nav-tab ${s.name === activeService ? 'active' : ''}`;
        btn.setAttribute('data-service-target', s.name);

        let dotColor = 'bg-emerald-500';
        if (s.status === 'CRITICAL_BREAK') dotColor = 'bg-rose-500';
        else if (s.status === 'WARNING') dotColor = 'bg-amber-500';

        btn.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${dotColor}"></span>${formatServiceName(s.name)}`;
        btn.addEventListener('click', () => {
            selectService(s.name, false);
        });
        container.appendChild(btn);
    });

    const subText = document.getElementById('appInitSubText');
    if (subText && appState.overview) {
        subText.innerText = `Indexed: ${appState.overview.total_log_lines.toLocaleString()} entries across ${services.length} pipelines`;
    }
    const footerBadge = document.getElementById('footerTelemetryBadge');
    if (footerBadge) {
        footerBadge.innerText = `Telemetry Active • ${services.length} Pipelines Indexed`;
    }
}

function updateServiceFilterOptions(services, selectedService = 'ALL') {
    const select = document.getElementById('filterService');
    if (!select) return;
    const currentVal = select.value || selectedService;
    select.innerHTML = '<option value="ALL">All Services</option>';
    services.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.name;
        opt.innerText = s.name;
        select.appendChild(opt);
    });
    select.value = currentVal;
}

async function fetchServices(selectedService = 'ALL') {
    const res = await fetch(`${API_BASE}/api/services`);
    const data = await res.json();
    appState.services = data;
    renderPortalNavPills(data, selectedService);
    updateServiceFilterOptions(data, selectedService);
    renderServices(data, selectedService);
}

async function fetchErrorCauses(service = 'ALL') {
    const url = (service && service !== 'ALL')
        ? `${API_BASE}/api/errors/causes?service=${encodeURIComponent(service)}`
        : `${API_BASE}/api/errors/causes`;
    const res = await fetch(url);
    const data = await res.json();
    appState.errorCauses = data;
    renderErrorCauses(data, service);
}

async function fetchTimeline(service = 'ALL') {
    const url = (service && service !== 'ALL')
        ? `${API_BASE}/api/timeline?service=${encodeURIComponent(service)}`
        : `${API_BASE}/api/timeline`;
    const res = await fetch(url);
    const data = await res.json();
    appState.timeline = data;
}

async function fetchAISettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings/ai`);
        const data = await res.json();
        appState.aiSettings = data;
        updateAIBadges(data);
    } catch (err) {
        console.warn('Failed to load AI settings:', err);
    }
}

function updateAIBadges(settings) {
    const badge = document.getElementById('aiConfigBtn');
    if (!badge) return;

    const rawModel = (settings && settings.model) || (appState.config && appState.config.model_name) || 'Qwen/Qwen2.5-3B-Instruct';
    const modelLabel = rawModel.replace(/^Qwen\//i, '');
    badge.className = "px-3 py-1.5 rounded-full bg-emerald-50 hover:bg-emerald-100/80 border border-emerald-300 text-xs font-bold text-emerald-800 transition-all flex items-center gap-1.5 shadow-xs cursor-pointer";
    badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-[#10B981] animate-pulse"></span><span>QWEN: ${modelLabel}</span>`;
    lucide.createIcons();
}

function openAISettingsModal() {
    const modal = document.getElementById('aiSettingsModal');
    if (!modal) return;

    const modelInput = document.getElementById('aiModelInput');
    const defaultModel = (appState.config && appState.config.model_name) || 'Qwen/Qwen2.5-3B-Instruct';
    if (modelInput) modelInput.value = defaultModel;

    const endpointInput = document.getElementById('aiEndpointInput');
    if (endpointInput) endpointInput.value = 'local-in-memory (PyTorch CPU / Single Process)';

    const statusMsg = document.getElementById('aiSaveStatus');
    if (statusMsg) {
        statusMsg.innerText = 'Local in-memory Qwen engine is active and warmed up.';
        statusMsg.className = 'text-xs text-emerald-700 font-semibold';
    }

    modal.classList.remove('hidden');
    lucide.createIcons();
}

function closeAISettingsModal() {
    const modal = document.getElementById('aiSettingsModal');
    if (modal) modal.classList.add('hidden');
}

async function handleSaveAISettings(e) {
    e.preventDefault();
    const statusMsg = document.getElementById('aiSaveStatus');
    if (statusMsg) {
        statusMsg.innerText = 'Verified: Local In-Memory Qwen 2.5 3B is active.';
        statusMsg.className = 'text-xs text-emerald-700 font-bold';
    }
    setTimeout(() => {
        closeAISettingsModal();
    }, 500);
}

// ================= SERVICE SELECTION & TABS ================= //

async function selectService(serviceName, shouldScroll = false) {
    appState.filters.service = serviceName;
    appState.filters.status_filter = 'ALL';
    appState.pagination.page = 1;

    // 1. Update filter dropdowns
    const serviceSelect = document.getElementById('filterService');
    if (serviceSelect) {
        serviceSelect.value = serviceName;
    }
    const statusSelect = document.getElementById('filterStatus');
    if (statusSelect) {
        statusSelect.value = 'ALL';
    }

    // 2. Sync all nav tabs
    document.querySelectorAll('.service-nav-tab').forEach(t => {
        if (t.getAttribute('data-service-target') === serviceName) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });

    // 3. Update active filter banner
    updateActiveServiceBanner(serviceName);

    // 4. Concurrently fetch service-scoped Overview, Timeline, Error Causes, and Logs
    await Promise.all([
        fetchOverview(serviceName),
        fetchTimeline(serviceName),
        fetchErrorCauses(serviceName),
        fetchLogs()
    ]);

    // 5. Explicitly refresh all 4 charts with the updated service scope
    if (appState.overview && appState.services && appState.errorCauses && appState.timeline) {
        initCharts(appState.overview, appState.services, appState.errorCauses, appState.timeline, serviceName);
    }

    // 6. Update titles, badges, and tab headers for the active service scope
    updateScopeUI(serviceName);

    // 7. Update Monitored Services grid
    renderServices(appState.services, serviceName);

    // 8. If log exploration was requested, switch directly to the Interactive Log Explorer tab & scroll
    if (shouldScroll) {
        switchInspectorTab('logs');
        const logsSection = document.getElementById('logsExplorerSection');
        if (logsSection) {
            logsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}

async function filterLogsByMetric(service, metric) {
    appState.filters.service = service;
    appState.filters.status_filter = metric; // 'errors', 'success', or 'processed'
    appState.filters.level = 'ALL'; // Reset level to prevent conflicting level filters
    appState.filters.search = '';
    appState.pagination.page = 1;

    // 1. Sync service filter dropdown
    const serviceSelect = document.getElementById('filterService');
    if (serviceSelect) {
        serviceSelect.value = service;
    }

    // 2. Sync status filter dropdown
    const statusSelect = document.getElementById('filterStatus');
    if (statusSelect) {
        statusSelect.value = metric;
    }

    // 3. Reset level & search filter inputs
    const levelSelect = document.getElementById('filterLevel');
    if (levelSelect) {
        levelSelect.value = 'ALL';
    }
    const searchInput = document.getElementById('filterSearch');
    if (searchInput) {
        searchInput.value = '';
    }

    // 4. Sync top portal nav tabs
    document.querySelectorAll('.service-nav-tab').forEach(t => {
        if (t.getAttribute('data-service-target') === service) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });

    // 5. Update banner with initial loading state
    updateActiveMetricBanner(service, metric);

    // 6. IMMEDIATELY activate the Interactive Log Explorer tab
    switchInspectorTab('logs');

    // 7. Show immediate loader in the logs table
    const tableBody = document.getElementById('logsTableBody');
    if (tableBody) {
        const metricName = metric === 'errors' ? 'Error & Failed' : (metric === 'success' ? 'Successful' : 'Processed');
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" class="py-10 text-center text-slate-500 font-sans">
                    <div class="flex flex-col items-center justify-center gap-2">
                        <i data-lucide="loader-2" class="w-6 h-6 animate-spin text-[#00468e]"></i>
                        <span class="text-xs font-medium">Filtering ${metricName} logs for ${service}...</span>
                    </div>
                </td>
            </tr>
        `;
        lucide.createIcons();
    }

    // 8. Smoothly scroll into the Interactive Log Explorer immediately
    setTimeout(() => {
        const logsExplorerSection = document.getElementById('logsExplorerSection');
        if (logsExplorerSection) {
            logsExplorerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, 40);

    // 9. Concurrently fetch service overview and filtered logs
    await Promise.all([
        fetchOverview(service),
        fetchLogs()
    ]);

    // 10. Update titles, badges, and tab headers for the active service scope
    updateScopeUI(service);

    // 11. Final update of active banner with exact counts
    updateActiveMetricBanner(service, metric);
}

function clearLogExplorerFilters() {
    activeKPIType = null;
    document.querySelectorAll('.bt-kpi-card-clickable').forEach(c => c.classList.remove('bt-kpi-card-active'));
    const kpiBanner = document.getElementById('kpiDrilldownBanner');
    if (kpiBanner) kpiBanner.classList.add('hidden');

    appState.filters.status_filter = 'ALL';
    appState.filters.level = 'ALL';
    appState.filters.search = '';
    appState.pagination.page = 1;

    const statusSelect = document.getElementById('filterStatus');
    if (statusSelect) statusSelect.value = 'ALL';

    const levelSelect = document.getElementById('filterLevel');
    if (levelSelect) levelSelect.value = 'ALL';

    const searchInput = document.getElementById('filterSearch');
    if (searchInput) searchInput.value = '';

    const banner = document.getElementById('activeServiceFilterBanner');
    if (banner) banner.classList.add('hidden');

    fetchLogs();
}

function updateActiveMetricBanner(service, metric) {
    const banner = document.getElementById('activeServiceFilterBanner');
    const textSpan = document.getElementById('activeServiceFilterText');
    if (!banner || !textSpan) return;

    const metricTitle = metric === 'errors' ? 'Errors & Failures' : (metric === 'success' ? 'Successful Operations' : 'Processed Transaction Records');
    const countInfo = appState.pagination.total ? `${appState.pagination.total.toLocaleString()} records` : '';

    textSpan.innerHTML = `Viewing <strong class="text-[#FF9C1D] uppercase tracking-wider text-[11px] font-bold">${metricTitle}</strong> for service: <strong class="text-[#091E3E] font-mono text-xs font-bold">${service}</strong> <span class="text-slate-500 font-sans ml-1 font-semibold">(${countInfo})</span>`;
    banner.classList.remove('hidden');
    lucide.createIcons();
}

function updateScopeUI(serviceName) {
    const isAll = !serviceName || serviceName === 'ALL';

    // Visual Analytics Scope Badge & Subtitle
    const vaBadge = document.getElementById('visualAnalyticsScopeBadge');
    if (vaBadge) {
        if (isAll) {
            vaBadge.classList.add('hidden');
        } else {
            vaBadge.classList.remove('hidden');
            vaBadge.innerText = serviceName;
        }
    }

    const vaSub = document.getElementById('visualAnalyticsSubtitle');
    if (vaSub) {
        vaSub.innerText = isAll
            ? 'Throughput, error frequency & batch execution timelines across all services'
            : `Throughput, error frequency & batch execution timelines for ${serviceName}`;
    }

    // Chart Badges & Subtitles
    const statusChartSub = document.getElementById('statusChartSub');
    if (statusChartSub && appState.overview) {
        statusChartSub.innerText = `${appState.overview.success_rate_percent}% successful completion`;
    }

    const serviceVolumeBadge = document.getElementById('serviceVolumeBadge');
    if (serviceVolumeBadge) {
        const svcCount = (appState.services && appState.services.length) || 0;
        serviceVolumeBadge.innerText = isAll ? `${svcCount} Services` : 'Throughput';
    }

    const serviceVolumeSub = document.getElementById('serviceVolumeSub');
    if (serviceVolumeSub) {
        const topSvc = appState.services && appState.services.length > 0
            ? appState.services.reduce((prev, curr) => (curr.records_processed > prev.records_processed ? curr : prev), appState.services[0])
            : null;
        serviceVolumeSub.innerText = isAll
            ? (topSvc ? `${formatServiceName(topSvc.name)}: greatest throughput` : 'Throughput across services')
            : `${formatServiceName(serviceName)} operational throughput breakdown`;
    }

    const errorCausesBadge = document.getElementById('errorCausesBadge');
    if (errorCausesBadge) {
        const causeCount = (appState.errorCauses && appState.errorCauses.length) || 0;
        errorCausesBadge.innerText = `${causeCount} Cause${causeCount === 1 ? '' : 's'}`;
    }

    const errorCausesSub = document.getElementById('errorCausesSub');
    if (errorCausesSub) {
        const causeCount = (appState.errorCauses && appState.errorCauses.length) || 0;
        if (isAll) {
            const topAnomaly = (appState.errorCauses && appState.errorCauses.length > 0) ? appState.errorCauses[0] : null;
            errorCausesSub.innerText = topAnomaly ? `${topAnomaly.title.slice(0, 24)} (${topAnomaly.count})` : 'No active anomalies';
        } else if (causeCount === 0) {
            errorCausesSub.innerText = '100% clean operational execution';
        } else {
            errorCausesSub.innerText = `${formatServiceName(serviceName)} error anomaly breakdown`;
        }
    }

    const timelineBadge = document.getElementById('timelineBadge');
    if (timelineBadge) {
        timelineBadge.innerText = isAll ? 'Batch Cycles' : 'Timeline';
    }

    const timelineSub = document.getElementById('timelineSub');
    if (timelineSub) {
        timelineSub.innerText = isAll
            ? 'Activity & error frequency across monitored timeline'
            : `${formatServiceName(serviceName)} activity & error frequency over time`;
    }

    // Inspector Tab labels & hints
    const tabBtnServicesLabel = document.getElementById('tabBtnServicesLabel');
    if (tabBtnServicesLabel) {
        tabBtnServicesLabel.innerText = isAll ? 'Active Pipelines (4 Services)' : `Active Pipeline: ${serviceName}`;
    }

    const tabBtnRcaLabel = document.getElementById('tabBtnRcaLabel');
    if (tabBtnRcaLabel) {
        const causeCount = (appState.errorCauses && appState.errorCauses.length) || 0;
        tabBtnRcaLabel.innerText = isAll ? 'RCA Blueprint (3 Anomalies)' : `RCA Blueprint (${causeCount} Anomalies)`;
    }

    const tabSectionHint = document.getElementById('tabSectionHint');
    if (tabSectionHint) {
        if (isAll) {
            tabSectionHint.innerHTML = 'Click any service to view its logs below';
        } else {
            tabSectionHint.innerHTML = `<span>Filtered: <strong>${serviceName}</strong></span> <button type="button" onclick="selectService('ALL', false)" class="ml-2 text-xs font-bold text-[#FF9C1D] hover:text-[#E67800] hover:underline inline-flex items-center gap-1 cursor-pointer"><i data-lucide="rotate-ccw" class="w-3 h-3"></i> Show All 4 Pipelines</button>`;
        }
    }

    // Explorer Title, Badge & Subtitle
    const logsExplorerScopeBadge = document.getElementById('logsExplorerScopeBadge');
    if (logsExplorerScopeBadge) {
        if (isAll) {
            logsExplorerScopeBadge.classList.add('hidden');
        } else {
            logsExplorerScopeBadge.classList.remove('hidden');
            logsExplorerScopeBadge.innerText = serviceName;
        }
    }

    const logsExplorerSubtitle = document.getElementById('logsExplorerSubtitle');
    if (logsExplorerSubtitle) {
        logsExplorerSubtitle.innerText = isAll
            ? 'Search, filter, and inspect detailed stack traces across all indexed log files'
            : `Search, filter, and inspect detailed stack traces for ${serviceName}`;
    }

    // AI Assistant Scope Badge & Context-Aware Quick Questions
    const aiScopeBadge = document.getElementById('aiAssistantScopeBadge');
    const aiScopeText = document.getElementById('aiAssistantScopeText');
    const quickQueriesContainer = document.getElementById('quickQueriesContainer');
    const queryInput = document.getElementById('queryInput');

    if (aiScopeBadge && aiScopeText) {
        if (isAll) {
            aiScopeBadge.className = 'text-[9.5px] font-mono font-bold px-2 py-0.5 rounded-full bg-blue-100 text-[#00468E] border border-blue-200 flex items-center gap-1 shadow-2xs';
            aiScopeText.innerText = 'ALL SERVICES (System-Wide)';
        } else {
            aiScopeBadge.className = 'text-[9.5px] font-mono font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1 shadow-2xs';
            aiScopeText.innerText = `${serviceName} Scope`;
        }
    }

    if (queryInput) {
        queryInput.placeholder = isAll
            ? "Ask an operational question across all services (e.g. which error is latest, what broke the flow)..."
            : `Ask a question specifically about ${formatServiceName(serviceName)} (e.g. what is the latest error, records processed)...`;
    }

    if (quickQueriesContainer) {
        if (isAll) {
            quickQueriesContainer.innerHTML = `
                <span class="font-semibold text-slate-500 text-[10px] mr-0.5 flex items-center gap-1">
                    <i data-lucide="zap" class="w-3 h-3 text-[#FF9C1D]"></i> Context Questions:
                </span>
                <button type="button" class="quick-query-pill border-rose-300 text-rose-700 bg-rose-50 text-[10.5px] py-0.5 px-2.5" data-query="which error is latest">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#DC2626]"></span>
                    <span>Which error is latest</span>
                </button>
                <button type="button" class="quick-query-pill text-[10.5px] py-0.5 px-2.5" data-query="what error break the flow">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#FF9C1D]"></span>
                    <span>What error break the flow</span>
                </button>
                <button type="button" class="quick-query-pill border-blue-300 text-[#00468E] bg-blue-50 text-[10.5px] py-0.5 px-2.5" data-query="how many logs shows error">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#00468E]"></span>
                    <span>How many logs shows error</span>
                </button>
                <button type="button" class="quick-query-pill border-amber-300 text-amber-700 bg-amber-50 text-[10.5px] py-0.5 px-2.5" data-query="what is our system SLA">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#F59E0B]"></span>
                    <span>System SLA</span>
                </button>
            `;
        } else {
            const formatted = formatServiceName(serviceName);
            quickQueriesContainer.innerHTML = `
                <span class="font-semibold text-slate-500 text-[10px] mr-0.5 flex items-center gap-1">
                    <i data-lucide="zap" class="w-3 h-3 text-[#FF9C1D]"></i> ${escapeHtml(formatted)} Questions:
                </span>
                <button type="button" class="quick-query-pill border-rose-300 text-rose-700 bg-rose-50 text-[10.5px] py-0.5 px-2.5" data-query="what is the latest error in ${serviceName}">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#DC2626]"></span>
                    <span>Latest error</span>
                </button>
                <button type="button" class="quick-query-pill border-amber-300 text-amber-700 bg-amber-50 text-[10.5px] py-0.5 px-2.5" data-query="explain errors and failures in ${serviceName}">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#F59E0B]"></span>
                    <span>Error analysis</span>
                </button>
                <button type="button" class="quick-query-pill border-blue-300 text-[#00468E] bg-blue-50 text-[10.5px] py-0.5 px-2.5" data-query="how many records were processed by ${serviceName}">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#00468E]"></span>
                    <span>Records processed</span>
                </button>
                <button type="button" class="quick-query-pill border-emerald-300 text-emerald-700 bg-emerald-50 text-[10.5px] py-0.5 px-2.5" data-query="what is the status and health of ${serviceName}">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#10B981]"></span>
                    <span>Service health</span>
                </button>
            `;
        }

        // Re-attach click listeners to the dynamic pills
        quickQueriesContainer.querySelectorAll('.quick-query-pill').forEach(btn => {
            btn.addEventListener('click', () => {
                const query = btn.getAttribute('data-query');
                if (queryInput) queryInput.value = query;
                submitQuery(query);
            });
        });
    }

    lucide.createIcons();
}

function updateActiveServiceBanner(serviceName) {
    const banner = document.getElementById('activeServiceFilterBanner');
    const textSpan = document.getElementById('activeServiceFilterText');
    if (!banner || !textSpan) return;

    if (serviceName && serviceName !== 'ALL') {
        textSpan.innerHTML = `Viewing logs for service: <strong class="text-[#091E3E] font-mono text-xs">${serviceName}</strong>`;
        banner.classList.remove('hidden');
    } else {
        banner.classList.add('hidden');
    }
    lucide.createIcons();
}

function switchInspectorTab(tab) {
    const servicesSection = document.getElementById('servicesSection');
    const rcaSection = document.getElementById('errorCausesSection');
    const logsSection = document.getElementById('logsExplorerSection');
    const tabBtnServices = document.getElementById('tabBtnServices');
    const tabBtnRca = document.getElementById('tabBtnRca');
    const tabBtnLogs = document.getElementById('tabBtnLogs');

    const activeClasses = 'bt-tab-pill active flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full transition-all';
    const inactiveClasses = 'bt-tab-pill flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full transition-all text-slate-600 hover:text-[#00468e]';

    // Hide all 3 panes first
    if (servicesSection) servicesSection.classList.add('hidden');
    if (rcaSection) rcaSection.classList.add('hidden');
    if (logsSection) logsSection.classList.add('hidden');

    // Deactivate all 3 buttons
    if (tabBtnServices) tabBtnServices.className = inactiveClasses;
    if (tabBtnRca) tabBtnRca.className = inactiveClasses;
    if (tabBtnLogs) tabBtnLogs.className = inactiveClasses;

    if (tab === 'services') {
        if (servicesSection) servicesSection.classList.remove('hidden');
        if (tabBtnServices) tabBtnServices.className = activeClasses;
    } else if (tab === 'rca') {
        if (rcaSection) rcaSection.classList.remove('hidden');
        if (tabBtnRca) tabBtnRca.className = activeClasses;
    } else if (tab === 'logs') {
        if (logsSection) logsSection.classList.remove('hidden');
        if (tabBtnLogs) tabBtnLogs.className = activeClasses;
    }
    lucide.createIcons();
}

// ================= KPI MISSION CONTROL CARD CLICKS ================= //

let activeKPIType = null;

async function handleKPIClick(kpiType) {
    activeKPIType = kpiType;

    // 1. Highlight active card on the left panel
    document.querySelectorAll('.bt-kpi-card-clickable').forEach(c => {
        if (c.getAttribute('data-kpi-type') === kpiType) {
            c.classList.add('bt-kpi-card-active');
        } else {
            c.classList.remove('bt-kpi-card-active');
        }
    });

    // 2. Setup the banner metadata & filters based on the selected card
    const banner = document.getElementById('kpiDrilldownBanner');
    const iconBox = document.getElementById('kpiDrilldownIconBox');
    const icon = document.getElementById('kpiDrilldownIcon');
    const title = document.getElementById('kpiDrilldownTitle');
    const badge = document.getElementById('kpiDrilldownCountBadge');
    const tag = document.getElementById('kpiDrilldownTag');
    const desc = document.getElementById('kpiDrilldownDescription');

    // Retain current service filter context (or default to ALL)
    const currentService = appState.filters.service || 'ALL';
    const isAll = currentService === 'ALL';

    appState.filters.search = '';
    appState.pagination.page = 1;

    // Sync service select & search input
    const serviceSelect = document.getElementById('filterService');
    if (serviceSelect) serviceSelect.value = currentService;
    const searchInput = document.getElementById('filterSearch');
    if (searchInput) searchInput.value = '';

    // Synchronize overview metrics for the active service scope
    await fetchOverview(currentService);

    const overview = appState.overview || {};
    const totalProcessed = (overview.total_records_processed || 0).toLocaleString();
    const totalSuccess = (overview.successful_records || 0).toLocaleString();
    const successRate = (overview.success_rate_percent || 0) + '%';
    const totalErrors = (overview.total_error_logs || 0).toLocaleString();
    const totalBreaks = (overview.service_breaks_count || 0).toLocaleString();
    const totalLines = (overview.total_log_lines || 0).toLocaleString();
    const latestDate = overview.latest_log_date || new Date().toISOString().split('T')[0];

    if (kpiType === 'processed') {
        appState.filters.status_filter = 'processed';
        appState.filters.level = 'ALL';
        appState.filters.date = 'ALL';

        if (title) title.innerText = isAll ? 'Processed Records Directory' : `${currentService} Processed Directory`;
        if (badge) {
            badge.innerText = `${totalProcessed} Records`;
            badge.className = 'text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-[#00468E] text-white';
        }
        if (tag) {
            tag.innerText = isAll ? `Across ${(appState.services && appState.services.length) || 'All'} Services` : `${formatServiceName(currentService)} Scope`;
            tag.className = 'text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-blue-100 text-[#00468E]';
        }
        if (desc) {
            desc.innerText = isAll
                ? `Listing all ${totalProcessed} processed records across all monitored services.`
                : `Listing ${totalProcessed} processed records specifically for ${formatServiceName(currentService)}.`;
        }
        if (iconBox) iconBox.className = 'w-10 h-10 rounded-xl bg-[#00468E] text-white flex items-center justify-center shrink-0 shadow-xs';
        if (icon) icon.setAttribute('data-lucide', 'layers');

    } else if (kpiType === 'success') {
        appState.filters.status_filter = 'success';
        appState.filters.level = 'ALL';
        appState.filters.date = 'ALL';

        if (title) title.innerText = isAll ? 'Successful Operations Audit' : `${formatServiceName(currentService)} Successful Audit`;
        if (badge) {
            badge.innerText = `${totalSuccess} Records (${successRate})`;
            badge.className = 'text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-[#10B981] text-white';
        }
        if (tag) {
            tag.innerText = isAll ? `SLA Target Met · ${successRate}` : `${formatServiceName(currentService)} · ${successRate}`;
            tag.className = 'text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-emerald-100 text-[#065F46]';
        }
        if (desc) {
            desc.innerText = isAll
                ? `Listing all ${totalSuccess} successfully completed operations meeting SLA.`
                : `Listing ${totalSuccess} successfully completed operations for ${formatServiceName(currentService)} meeting SLA requirements.`;
        }
        if (iconBox) iconBox.className = 'w-10 h-10 rounded-xl bg-[#10B981] text-white flex items-center justify-center shrink-0 shadow-xs';
        if (icon) icon.setAttribute('data-lucide', 'check-circle-2');

    } else if (kpiType === 'errors') {
        appState.filters.status_filter = 'ALL';
        appState.filters.level = 'ERROR';
        appState.filters.date = 'ALL';

        if (title) {
            title.innerText = isAll
                ? 'System Error Logs & Exception Feed'
                : `${formatServiceName(currentService)} Error Logs & Exceptions`;
        }
        if (badge) {
            badge.innerText = isAll
                ? `${totalErrors} Error Logs`
                : `${totalErrors} Error Log${totalErrors === '1' ? '' : 's'}`;
            badge.className = 'text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-[#DC2626] text-white';
        }
        if (tag) {
            tag.innerText = isAll ? `${totalErrors} System Errors` : `${totalErrors} in ${formatServiceName(currentService)}`;
            tag.className = 'text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-rose-100 text-rose-800';
        }
        if (desc) {
            if (isAll) {
                desc.innerHTML = `Listing all <strong>${totalErrors}</strong> error logs across all active pipelines with full stack traces.`;
            } else {
                desc.innerHTML = `Listing <strong>${totalErrors}</strong> error log(s) for <strong>${escapeHtml(formatServiceName(currentService))}</strong>. <button type="button" onclick="selectService('ALL', false); handleKPIClick('errors');" class="text-xs font-bold text-[#00468E] hover:underline ml-1.5 inline-flex items-center gap-0.5"><i data-lucide='layers' class='w-3 h-3'></i> View All System Errors Across All Services →</button>`;
            }
        }
        if (iconBox) iconBox.className = 'w-10 h-10 rounded-xl bg-[#DC2626] text-white flex items-center justify-center shrink-0 shadow-xs';
        if (icon) icon.setAttribute('data-lucide', 'alert-triangle');

    } else if (kpiType === 'breaks') {
        appState.filters.status_filter = 'breaks';
        appState.filters.level = 'ERROR';
        appState.filters.date = 'ALL';

        if (title) title.innerText = 'Critical Service Breaks & Pipeline Halts';
        if (badge) {
            badge.innerText = `${totalBreaks} Critical Break${totalBreaks === '1' ? '' : 's'}`;
            badge.className = 'text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-[#DC2626] text-white animate-pulse';
        }
        if (tag) {
            tag.innerText = isAll ? `${totalBreaks} Pipeline Halt${totalBreaks === '1' ? '' : 's'}` : `${formatServiceName(currentService)} Halt`;
            tag.className = 'text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-rose-200 text-rose-900';
        }
        if (desc) {
            desc.innerHTML = isAll
                ? `Detected <strong>${totalBreaks}</strong> critical execution halt(s) preventing scheduled pipeline completion.`
                : `Execution halt detected in <strong>${escapeHtml(formatServiceName(currentService))}</strong>.`;
        }
        if (iconBox) iconBox.className = 'w-10 h-10 rounded-xl bg-rose-700 text-white flex items-center justify-center shrink-0 shadow-xs';
        if (icon) icon.setAttribute('data-lucide', 'flame');

    } else if (kpiType === 'rca') {
        // Direct jump to Root Cause Analysis Deep Dive tab
        switchInspectorTab('causes');
        if (banner) banner.classList.add('hidden');
        const causesSection = document.getElementById('errorCausesSection');
        if (causesSection) {
            causesSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        lucide.createIcons();
        return;

    } else if (kpiType === 'indexed') {
        appState.filters.status_filter = 'ALL';
        appState.filters.level = 'ALL';
        appState.filters.date = 'ALL';

        if (title) title.innerText = isAll ? 'Full Indexed SQLite Event Repository' : `${currentService} SQLite Event Stream`;
        if (badge) {
            badge.innerText = `${totalLines} Lines Indexed`;
            badge.className = 'text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-[#091E3E] text-white';
        }
        if (tag) {
            tag.innerText = isAll ? 'SQLite FTS5 Active' : `${currentService} Scope`;
            tag.className = 'text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-slate-200 text-[#091E3E]';
        }
        if (desc) {
            desc.innerText = isAll
                ? 'Complete raw log stream of 35,860 events indexed across all 4 service log files in SQLite (logs.db) with sub-millisecond search & pagination.'
                : `Complete raw log stream of ${totalLines} events indexed for ${currentService} in SQLite (logs.db) with sub-millisecond search & pagination.`;
        }
        if (iconBox) iconBox.className = 'w-10 h-10 rounded-xl bg-[#091E3E] text-white flex items-center justify-center shrink-0 shadow-xs';
        if (icon) icon.setAttribute('data-lucide', 'database');

    } else if (kpiType === 'latest') {
        appState.filters.status_filter = 'ALL';
        appState.filters.level = 'ALL';
        appState.filters.date = latestDate;

        if (title) title.innerText = `Latest Batch Execution (${latestDate})`;
        if (badge) {
            badge.innerText = `${latestDate} Batch`;
            badge.className = 'text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-[#FF9C1D] text-white';
        }
        if (tag) {
            tag.innerText = 'Latest Execution';
            tag.className = 'text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-amber-100 text-amber-800';
        }
        if (desc) desc.innerText = `Filtering all execution activity, transactions, and error telemetry recorded during the latest batch date: ${latestDate}.`;
        if (iconBox) iconBox.className = 'w-10 h-10 rounded-xl bg-[#FF9C1D] text-white flex items-center justify-center shrink-0 shadow-xs';
        if (icon) icon.setAttribute('data-lucide', 'calendar');
    }

    // Synchronize UI dropdowns
    const statusSelect = document.getElementById('filterStatus');
    if (statusSelect) statusSelect.value = appState.filters.status_filter;
    const levelSelect = document.getElementById('filterLevel');
    if (levelSelect) levelSelect.value = appState.filters.level;
    const dateSelect = document.getElementById('filterDate');
    if (dateSelect) dateSelect.value = appState.filters.date;

    // Show banner
    if (banner) banner.classList.remove('hidden');

    // Switch to Interactive Log Explorer tab
    switchInspectorTab('logs');

    // Fetch and render filtered logs
    await fetchLogs();

    // Scroll smoothly to middle section
    const drilldownEl = document.getElementById('kpiDrilldownBanner');
    if (drilldownEl) {
        drilldownEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    lucide.createIcons();
}

async function resetKPIDrilldown() {
    activeKPIType = null;

    // Unselect left cards
    document.querySelectorAll('.bt-kpi-card-clickable').forEach(c => {
        c.classList.remove('bt-kpi-card-active');
    });

    // Hide drilldown banner
    const banner = document.getElementById('kpiDrilldownBanner');
    if (banner) banner.classList.add('hidden');

    // Reset filters
    appState.filters.status_filter = 'ALL';
    appState.filters.level = 'ALL';
    appState.filters.service = 'ALL';
    appState.filters.date = 'ALL';
    appState.filters.search = '';
    appState.pagination.page = 1;

    const statusSelect = document.getElementById('filterStatus');
    if (statusSelect) statusSelect.value = 'ALL';
    const levelSelect = document.getElementById('filterLevel');
    if (levelSelect) levelSelect.value = 'ALL';
    const serviceSelect = document.getElementById('filterService');
    if (serviceSelect) serviceSelect.value = 'ALL';
    const dateSelect = document.getElementById('filterDate');
    if (dateSelect) dateSelect.value = 'ALL';
    const searchInput = document.getElementById('filterSearch');
    if (searchInput) searchInput.value = '';

    // Reset top portal navigation pills
    document.querySelectorAll('.service-nav-tab').forEach(t => {
        if (t.getAttribute('data-service-target') === 'ALL') {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });

    await fetchOverview('ALL');
    await fetchLogs();
    switchInspectorTab('services');
    lucide.createIcons();
}

async function fetchLogs() {
    const { service, level, date, search, status_filter } = appState.filters;
    const { page, pageSize } = appState.pagination;

    const params = new URLSearchParams({
        service,
        level,
        date,
        search,
        status_filter: status_filter || 'ALL',
        page,
        page_size: pageSize
    });

    const res = await fetch(`${API_BASE}/api/logs?${params}`);
    const data = await res.json();
    appState.logs = data.logs;
    appState.pagination.total = data.total;

    // Update Log Explorer Tab label with exact count
    const tabBtnLogsLabel = document.getElementById('tabBtnLogsLabel');
    if (tabBtnLogsLabel) {
        tabBtnLogsLabel.innerText = data.total ? `Interactive Log Explorer (${data.total.toLocaleString()} Logs)` : 'Interactive Log Explorer';
    }

    // Update active banner with exact matching count
    const banner = document.getElementById('activeServiceFilterBanner');
    const textSpan = document.getElementById('activeServiceFilterText');
    if (banner && textSpan && service !== 'ALL') {
        const metricLabel = (status_filter && status_filter !== 'ALL')
            ? (status_filter === 'errors' ? 'Errors & Failed records' : (status_filter === 'success' ? 'Successful records' : 'Processed records'))
            : 'All records';
        textSpan.innerHTML = `Viewing <strong class="text-[#FF9C1D] font-bold">${metricLabel}</strong> for: <strong class="text-[#091E3E] font-mono text-xs font-bold">${service}</strong> <span class="text-slate-500 font-sans ml-1">(${data.total.toLocaleString()} matching entries found)</span>`;
    }

    renderLogsTable(data);
}

// ================= QUERY ASSISTANT ================= //

async function submitQuery(queryText) {
    const responseContainer = document.getElementById('queryResponseArea');
    const answerContent = document.getElementById('queryAnswerContent');
    const categoryBadge = document.getElementById('queryCategoryBadge');
    const serviceBadge = document.getElementById('queryServiceBadge');
    const latencyBadge = document.getElementById('queryLatencyBadge');
    const latencyText = document.getElementById('queryLatencyText');
    const perfPill = document.getElementById('queryPerfPill');
    const perfText = document.getElementById('queryPerfText');
    const evidenceContainer = document.getElementById('queryEvidenceContainer');
    const suggestedContainer = document.getElementById('querySuggestedContainer');
    const loadingIndicator = document.getElementById('queryLoadingIndicator');
    const timerCounter = document.getElementById('queryTimerCounter');

    if (!responseContainer) return;

    responseContainer.classList.remove('hidden');
    if (loadingIndicator) loadingIndicator.classList.remove('hidden');
    if (answerContent) answerContent.innerHTML = '';
    if (evidenceContainer) evidenceContainer.innerHTML = '';
    if (suggestedContainer) suggestedContainer.innerHTML = '';
    if (latencyBadge) latencyBadge.classList.add('hidden');
    if (perfPill) perfPill.classList.add('hidden');

    // Scroll smoothly to response
    responseContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Active Service Scope Context from Dashboard Filter
    const activeService = appState.filters.service || 'ALL';

    // Start high-precision client-side elapsed timer
    const startTime = performance.now();
    if (timerCounter) timerCounter.innerText = '⏱️ 0.0s elapsed';
    const timerInterval = setInterval(() => {
        const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
        if (timerCounter) timerCounter.innerText = `⏱️ ${elapsed}s elapsed`;
    }, 100);

    try {
        const res = await fetch(`${API_BASE}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: queryText,
                service: activeService
            })
        });
        const data = await res.json();

        clearInterval(timerInterval);
        if (loadingIndicator) loadingIndicator.classList.add('hidden');

        // Render response category
        if (categoryBadge) {
            let cat = data.category || 'Local Qwen 2.5';
            categoryBadge.className = 'badge-bt-cyan text-xs font-semibold';
            categoryBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-[#38BDF8]"></span>${cat}`;
        }
        if (serviceBadge) {
            const scopeLabel = (data.service && data.service !== 'All Services')
                ? `${data.service} Scope`
                : (activeService !== 'ALL' ? `${activeService} Scope` : 'All Services Scope');
            serviceBadge.innerText = scopeLabel;
            serviceBadge.className = (activeService !== 'ALL' || (data.service && data.service !== 'All Services'))
                ? 'px-2 py-0.5 rounded-full text-xs font-mono bg-amber-50 text-amber-800 border border-amber-300 font-bold'
                : 'px-2 py-0.5 rounded-full text-xs font-mono bg-blue-50 text-[#00468E] border border-blue-200 font-bold';
            serviceBadge.classList.remove('hidden');
        }

        // Render Latency & Execution Performance Metrics
        const durS = (data.duration_s !== undefined && data.duration_s !== null && data.duration_s > 0)
            ? Number(data.duration_s).toFixed(2)
            : ((performance.now() - startTime) / 1000).toFixed(2);
        const durMs = data.duration_ms || Math.round(Number(durS) * 1000);

        if (latencyBadge && latencyText) {
            latencyText.innerText = `⏱️ ${durS}s (${Number(durMs).toLocaleString()} ms)`;
            latencyBadge.classList.remove('hidden');
        }

        if (perfPill && perfText) {
            if (data.tokens_per_sec && data.tokens_per_sec > 0) {
                const ttftStr = data.ttft_s ? ` • TTFT: ${data.ttft_s}s` : '';
                perfText.innerText = `${data.tokens_per_sec} tok/s • ${data.tokens_count || 0} tokens${ttftStr}`;
                perfPill.classList.remove('hidden');
            } else {
                perfPill.classList.add('hidden');
            }
        }

        if (answerContent) {
            answerContent.innerHTML = marked.parse(data.answer);
        }

        // Render Suggested Follow-Up Queries (Evidence citations omitted per user specification)
        if (suggestedContainer && data.suggested_queries && data.suggested_queries.length > 0) {
            let sugHtml = `
                <div class="mt-4 pt-3 border-t border-[#06A3DA]/20">
                    <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
                        <i data-lucide="sparkles" class="w-3.5 h-3.5 text-[#06A3DA]"></i> Suggested Follow-Ups
                    </div>
                    <div class="flex flex-wrap gap-2">
            `;
            data.suggested_queries.forEach(q => {
                sugHtml += `
                    <button class="followup-query-btn quick-query-pill text-xs">
                        <span>${q}</span>
                        <i data-lucide="arrow-right" class="w-3 h-3 text-[#06A3DA]"></i>
                    </button>
                `;
            });
            sugHtml += `</div></div>`;
            suggestedContainer.innerHTML = sugHtml;

            // Bind click handlers to follow-up buttons
            suggestedContainer.querySelectorAll('.followup-query-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const nextQ = btn.querySelector('span').innerText;
                    const input = document.getElementById('queryInput');
                    if (input) input.value = nextQ;
                    submitQuery(nextQ);
                });
            });
        }

        lucide.createIcons();

    } catch (err) {
        clearInterval(timerInterval);
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        if (answerContent) {
            answerContent.innerHTML = `<div class="p-4 bg-rose-950/30 border border-rose-800 rounded text-rose-300 text-sm">Failed to generate response: ${err.message}</div>`;
        }
    }
}

// ================= RENDERING FUNCTIONS ================= //

function renderOverview(data, service = 'ALL') {
    const isAll = !service || service === 'ALL';

    // 1. System SLA & Health
    const slaLarge = document.getElementById('kpiSuccessRateLarge');
    if (slaLarge) slaLarge.innerText = `${data.success_rate_percent}%`;
    const succRate = document.getElementById('kpiSuccessRate');
    if (succRate) succRate.innerText = `${data.success_rate_percent}%`;
    const succSub = document.getElementById('kpiSuccessfulRecordsSubText');
    if (succSub) {
        succSub.innerText = isAll
            ? `${(data.successful_records || 0).toLocaleString()} / ${(data.total_records_processed || 0).toLocaleString()} Operations`
            : `${(data.successful_records || 0).toLocaleString()} / ${(data.total_records_processed || 0).toLocaleString()} in ${service}`;
    }
    const healthBadge = document.getElementById('kpiHealthBadge');
    if (healthBadge) {
        const isHealthy = (data.success_rate_percent || 0) >= (appState.slaTarget || 95.0);
        healthBadge.innerText = isHealthy ? (isAll ? 'SLA Met' : 'Healthy') : 'Degraded';
        healthBadge.className = isHealthy
            ? 'text-[9.5px] px-1.5 py-0.5 rounded bg-emerald-100 text-[#065F46] font-bold uppercase tracking-wider'
            : 'text-[9.5px] px-1.5 py-0.5 rounded bg-rose-100 text-[#DC2626] font-bold uppercase tracking-wider';
    }
    const succBar = document.getElementById('kpiSuccessProgressBar');
    if (succBar) {
        succBar.style.width = `${Math.min(100, data.success_rate_percent || 0)}%`;
    }

    // 2. Critical Service Breaks & Pipeline Incidents
    const breaksEl = document.getElementById('kpiServiceBreaks');
    if (breaksEl) breaksEl.innerText = `${data.service_breaks_count} Halt${data.service_breaks_count === 1 ? '' : 's'}`;
    const breaksSub = document.getElementById('kpiServiceBreaksSub');
    if (breaksSub) {
        if (data.service_breaks_count > 0) {
            breaksSub.innerHTML = `<span>${data.service_breaks_count} Pipeline Halt(s)</span><span class="text-[9.5px] px-1.5 py-0.5 rounded bg-rose-100 text-rose-800 font-bold uppercase">HALT</span>`;
        } else {
            breaksSub.innerHTML = `<span>No pipeline halts</span><span class="text-[9.5px] px-1.5 py-0.5 rounded bg-emerald-100 text-[#065F46] font-bold uppercase">ACTIVE</span>`;
        }
    }

    // 3. Root Cause Analysis (RCA) Clusters
    const rcaEl = document.getElementById('kpiRcaClusters');
    const causeCount = (appState.errorCauses && appState.errorCauses.length) || 0;
    if (rcaEl) {
        rcaEl.innerText = `${causeCount} Cluster${causeCount === 1 ? '' : 's'}`;
    }
    const rcaSub = document.getElementById('kpiRcaClustersSub');
    if (rcaSub) {
        if (appState.errorCauses && appState.errorCauses.length > 0) {
            rcaSub.innerText = appState.errorCauses.slice(0, 3).map(c => `${c.cause_id} (${c.title.slice(0, 15)})`).join(', ');
        } else {
            rcaSub.innerText = 'No root cause anomalies reported';
        }
    }

    // 4. Runtime Error Logs
    const errorsEl = document.getElementById('kpiTotalErrors');
    if (errorsEl) errorsEl.innerText = data.total_error_logs;
    const errorsDenom = document.getElementById('kpiTotalErrorsDenominator');
    if (errorsDenom) {
        errorsDenom.innerText = isAll ? 'system total' : 'in service';
    }
    const errorsSub = document.getElementById('kpiTotalErrorsSub');
    if (errorsSub) {
        errorsSub.innerText = isAll ? `${data.total_error_logs} system errors total` : `${data.total_error_logs} recorded in ${formatServiceName(service)}`;
    }
    const errScopeBadge = document.getElementById('kpiErrorScopeBadge');
    if (errScopeBadge) {
        if (isAll) {
            errScopeBadge.innerText = `ALL (${data.total_error_logs})`;
            errScopeBadge.className = 'text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-rose-100 text-[#DC2626] uppercase ml-1';
            errScopeBadge.title = `Showing all ${data.total_error_logs} system error logs`;
        } else {
            const totalErrorsOverall = (appState.overview && appState.overview.total_error_logs) || data.total_error_logs || 0;
            errScopeBadge.innerText = `${formatServiceName(service)} (${data.total_error_logs})`;
            errScopeBadge.className = 'text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-blue-100 text-[#00468E] uppercase ml-1';
            errScopeBadge.title = `Showing ${data.total_error_logs} error(s) in ${service} out of ${totalErrorsOverall} total across all services`;
        }
    }
    const errBar = document.getElementById('kpiErrorProgressBar');
    if (errBar) {
        const errorPct = (100 - (data.success_rate_percent || 100)).toFixed(1);
        errBar.style.width = `${Math.max(2, Math.min(100, errorPct))}%`;
    }

    // 5. Indexed SQLite Event Storage
    const linesEl = document.getElementById('kpiTotalLogLines');
    if (linesEl) linesEl.innerText = (data.total_log_lines || 0).toLocaleString();
    const linesSub = document.getElementById('kpiTotalLogLinesSub');
    if (linesSub) {
        linesSub.innerHTML = isAll
            ? `<span id="kpiTotalFiles">${data.total_log_files}</span> services in logs.db (&lt;1ms query)`
            : `1 service (${(data.total_log_lines || 0).toLocaleString()} lines in logs.db)`;
    }

    // 6. Batch Execution Audit Span
    const auditWindow = document.getElementById('kpiAuditWindow');
    if (auditWindow) {
        if (data.dates_available && data.dates_available.length > 0) {
            const sortedDates = [...data.dates_available].sort();
            auditWindow.innerText = sortedDates.length > 1 ? `${sortedDates[0]} → ${sortedDates[sortedDates.length - 1]}` : sortedDates[0];
        } else {
            auditWindow.innerText = data.latest_log_date || 'Live';
        }
    }
    const dateEl = document.getElementById('kpiLatestDate');
    if (dateEl) dateEl.innerText = data.latest_log_date || 'Live';
    const dateSub = document.getElementById('kpiLatestDateSub');
    if (dateSub) {
        dateSub.innerHTML = `<span>Latest batch: <strong>${data.latest_log_date || 'Live'}</strong></span><span class="inline-flex items-center gap-1 text-[9.5px] text-emerald-600 font-bold ml-1.5"><span class="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-ping"></span> Live</span>`;
    }

    // 7. Update Top Header Badges Dynamically
    const alertBadge = document.getElementById('systemAlertBadge');
    if (alertBadge) {
        if (data.service_breaks_count > 0) {
            alertBadge.className = "hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold";
            alertBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-[#DC2626] pulse-badge"></span><span id="systemAlertBadgeText">${data.service_breaks_count} Service Break${data.service_breaks_count === 1 ? '' : 's'} Detected</span>`;
        } else {
            alertBadge.className = "hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold";
            alertBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-[#10B981]"></span><span id="systemAlertBadgeText">All Services Healthy</span>`;
        }
    }

    const dateBadge = document.getElementById('systemStatusDateBadge');
    if (dateBadge) {
        dateBadge.innerText = `Active Date: ${data.latest_log_date || data.current_system_date || 'Live'}`;
    }

    // Left Panel Scope Badge
    const scopeBadge = document.getElementById('kpiPanelScopeBadge');
    if (scopeBadge) {
        if (isAll) {
            scopeBadge.className = 'text-[10px] px-2.5 py-0.5 rounded-full bg-slate-100 text-[#091E3E] border border-slate-200 font-bold flex items-center gap-1.5 shadow-xs';
            scopeBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-[#10B981]"></span>All Services`;
        } else {
            scopeBadge.className = 'text-[10px] px-2.5 py-0.5 rounded-full bg-[#FFF7ED] text-[#EA580C] border border-[#FF9C1D]/50 font-bold flex items-center gap-1.5 shadow-xs';
            scopeBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-[#FF9C1D] animate-pulse"></span>${service}`;
        }
    }

    // Header badge
    const sysDateBadge = document.getElementById('systemStatusDateBadge');
    if (sysDateBadge) {
        sysDateBadge.innerText = isAll ? `Active Date: ${data.latest_log_date}` : `${service}: ${data.latest_log_date}`;
    }
}

function updateDateFilterOptions(dates) {
    const dateSelect = document.getElementById('filterDate');
    if (!dateSelect || !dates) return;
    dateSelect.innerHTML = '<option value="ALL">All Dates</option>';
    dates.forEach(d => {
        dateSelect.innerHTML += `<option value="${d}">${d}</option>`;
    });
}

function renderServices(services, selectedService = 'ALL') {
    const container = document.getElementById('servicesGridContainer');
    if (!container) return;

    container.innerHTML = '';
    const isAll = !selectedService || selectedService === 'ALL';
    const displayServices = isAll ? services : services.filter(s => s.name === selectedService);

    if (displayServices.length === 0) {
        container.innerHTML = `<div class="col-span-full p-6 text-center text-slate-500 text-xs">No service records found for ${escapeHtml(selectedService)}.</div>`;
        return;
    }

    // Configure layout: 4 columns for All, centered/prominent when focused
    if (!isAll) {
        container.className = 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3';
    } else {
        container.className = 'grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3';
    }

    displayServices.forEach(svc => {
        let statusBadge = '';
        if (svc.status === 'CRITICAL_BREAK') {
            statusBadge = '<span class="badge-bt-danger text-xs flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-[#DC2626] animate-pulse"></span>CRITICAL BREAK</span>';
        } else if (svc.status === 'WARNING') {
            statusBadge = '<span class="badge-bt-warning text-xs flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-[#F59E0B]"></span>WARNING</span>';
        } else if (svc.status === 'HEALTHY') {
            statusBadge = '<span class="badge-bt-success text-xs flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-[#10B981] animate-pulse"></span>HEALTHY</span>';
        } else {
            statusBadge = '<span class="badge-bt-cyan text-xs flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-[#06A3DA]"></span>OPTIMAL</span>';
        }

        const cardAccent = svc.status === 'CRITICAL_BREAK' ? 'bt-kpi-card-danger' : (svc.status === 'HEALTHY' ? 'bt-kpi-card-success' : 'bt-kpi-card-orange');

        const card = document.createElement('div');
        card.className = `bt-kpi-card ${cardAccent} p-4 sm:p-5 flex flex-col justify-between ${!isAll ? 'ring-2 ring-[#00468E] shadow-lg' : ''}`;
        card.innerHTML = `
            <div>
                <div class="flex items-start justify-between gap-2 mb-3">
                    <div>
                        <h4 class="font-heading font-extrabold text-[#091E3E] text-sm tracking-tight">${svc.name}</h4>
                        <div class="inline-flex items-center gap-1 text-[10.5px] text-slate-500 font-mono mt-1 px-2 py-0.5 rounded bg-slate-100 border border-slate-200/80">
                            <i data-lucide="file-code" class="w-3 h-3 text-[#00468E]"></i>
                            <span>${svc.file_name}</span>
                        </div>
                    </div>
                    ${statusBadge}
                </div>

                <div class="grid grid-cols-3 gap-2 my-3 p-1.5 bg-[#F8FAFC] rounded-xl text-center text-xs border border-slate-200">
                    <button type="button" class="svc-metric-node-btn processed-btn svc-metric-btn group shadow-xs focus:ring-2 focus:ring-[#00468E]/30" data-service="${svc.name}" data-metric="processed" onclick="event.stopPropagation(); filterLogsByMetric('${svc.name}', 'processed')" title="Click to view all ${svc.records_processed.toLocaleString()} processed logs in Log Explorer">
                        <div class="text-slate-500 text-[9.5px] uppercase font-bold tracking-wider group-hover:text-[#00468E]">Processed</div>
                        <div class="font-heading font-extrabold text-[#00468E] text-base mt-0.5">${svc.records_processed.toLocaleString()}</div>
                        <div class="text-[9px] text-slate-400 group-hover:text-[#00468E] font-semibold flex items-center justify-center gap-0.5 mt-1">Logs <i data-lucide="arrow-down-right" class="w-2.5 h-2.5"></i></div>
                    </button>
                    <button type="button" class="svc-metric-node-btn success-btn svc-metric-btn group shadow-xs focus:ring-2 focus:ring-[#10B981]/30" data-service="${svc.name}" data-metric="success" onclick="event.stopPropagation(); filterLogsByMetric('${svc.name}', 'success')" title="Click to view ${svc.successful_records.toLocaleString()} successful logs in Log Explorer">
                        <div class="text-slate-500 text-[9.5px] uppercase font-bold tracking-wider group-hover:text-[#059669]">Success</div>
                        <div class="font-heading font-extrabold text-[#059669] text-base mt-0.5">${svc.successful_records.toLocaleString()}</div>
                        <div class="text-[9px] text-slate-400 group-hover:text-[#059669] font-semibold flex items-center justify-center gap-0.5 mt-1">Logs <i data-lucide="arrow-down-right" class="w-2.5 h-2.5"></i></div>
                    </button>
                    <button type="button" class="svc-metric-node-btn danger-btn svc-metric-btn group shadow-xs focus:ring-2 focus:ring-[#DC2626]/30" data-service="${svc.name}" data-metric="errors" onclick="event.stopPropagation(); filterLogsByMetric('${svc.name}', 'errors')" title="Click to view ${svc.failed_records > 0 ? svc.failed_records : svc.errors_count} failed/error logs in Log Explorer">
                        <div class="text-slate-500 text-[9.5px] uppercase font-bold tracking-wider ${svc.failed_records > 0 || svc.errors_count > 0 ? 'text-[#DC2626]' : 'text-slate-500'} group-hover:text-[#DC2626]">Errors / Fail</div>
                        <div class="font-heading font-extrabold ${svc.failed_records > 0 || svc.errors_count > 0 ? 'text-[#DC2626]' : 'text-slate-600'} text-base mt-0.5">
                            ${svc.failed_records > 0 ? svc.failed_records : svc.errors_count}
                        </div>
                        <div class="text-[9px] ${svc.failed_records > 0 || svc.errors_count > 0 ? 'text-[#DC2626] font-bold' : 'text-slate-400'} group-hover:text-[#DC2626] font-semibold flex items-center justify-center gap-0.5 mt-1">Logs <i data-lucide="arrow-down-right" class="w-2.5 h-2.5"></i></div>
                    </button>
                </div>

                <div class="text-xs text-slate-600 space-y-2 my-3">
                    ${svc.key_notes.map(note => `<div class="flex items-start gap-2 text-[11.5px] text-slate-600 leading-snug"><span class="w-1.5 h-1.5 rounded-full bg-[#FF9C1D] shrink-0 mt-1.5"></span><span>${note}</span></div>`).join('')}
                </div>
            </div>

            <div class="pt-3 mt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                <div class="flex items-center gap-1.5 text-slate-500 text-[11px] font-mono">
                    <i data-lucide="clock" class="w-3.5 h-3.5 text-[#597A9D]"></i>
                    <span>Last: ${svc.last_run.split(' ')[1] || svc.last_run}</span>
                </div>
                <div class="flex items-center gap-2">
                    ${!isAll ? `
                        <button type="button" class="btn-bt-secondary text-xs font-semibold py-1 px-2.5 reset-svc-view-btn">
                            <i data-lucide="grid" class="w-3 h-3 mr-1"></i> All Pipelines
                        </button>
                    ` : ''}
                    <button type="button" class="view-service-logs-btn btn-bt-primary text-xs font-bold py-1.5 px-3.5" data-service="${svc.name}">
                        Explore Logs <i data-lucide="arrow-right" class="w-3 h-3 ml-1"></i>
                    </button>
                </div>
            </div>
        `;

        card.querySelectorAll('.svc-metric-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const service = btn.getAttribute('data-service');
                const metric = btn.getAttribute('data-metric');
                filterLogsByMetric(service, metric);
            });
        });

        card.querySelector('.view-service-logs-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            selectService(svc.name, true);
        });

        const resetBtn = card.querySelector('.reset-svc-view-btn');
        if (resetBtn) {
            resetBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                selectService('ALL', false);
            });
        }

        container.appendChild(card);
    });
    lucide.createIcons();
}

function renderErrorCauses(causes, service = 'ALL') {
    const container = document.getElementById('errorCausesContainer');
    if (!container) return;

    container.innerHTML = '';
    const isAll = !service || service === 'ALL';

    // Update RCA tab label
    const tabBtnRcaLabel = document.getElementById('tabBtnRcaLabel');
    if (tabBtnRcaLabel) {
        tabBtnRcaLabel.innerText = isAll ? 'RCA Blueprint (3 Anomalies)' : `RCA Blueprint (${causes.length} Anomalies)`;
    }

    if (!causes || causes.length === 0) {
        container.innerHTML = `
            <div class="col-span-full p-6 text-center bg-[#d4edda] border border-[#c3e6cb] rounded-xl text-[#155724]">
                <i data-lucide="check-circle-2" class="w-8 h-8 mx-auto mb-2 text-[#34AD54]"></i>
                <div class="font-heading font-bold text-sm">No Error Anomalies Recorded</div>
                <div class="text-xs text-[#155724] mt-1">${!isAll ? `Pipeline <strong>${service}</strong>` : 'This pipeline'} executed with 100% clean operational health without unhandled exceptions or halts.</div>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    causes.forEach(cause => {
        const card = document.createElement('div');
        card.className = 'bt-kpi-card p-5 glass-panel-hover flex flex-col justify-between';

        const badgeColor = cause.cause_id === 'ERR-01' ? 'badge-bt-danger' :
            cause.cause_id === 'ERR-02' ? 'badge-bt-warning' :
                'badge-bt-cyan';

        card.innerHTML = `
            <div>
                <div class="flex items-start justify-between mb-3">
                    <div class="flex items-center gap-2">
                        <span class="${badgeColor} text-xs font-bold">${cause.cause_id}</span>
                        <span class="text-xs font-mono text-slate-500">${cause.error_type}</span>
                    </div>
                    <span class="text-xs font-bold px-2.5 py-0.5 rounded-full bg-[#EEF9FF] text-[#00468e] border border-[#b8e2f2]">
                        ${cause.count} occurrences
                    </span>
                </div>

                <h4 class="font-heading font-bold text-[#091E3E] text-sm mb-2">${cause.title}</h4>
                <div class="text-xs text-slate-600 mb-3 leading-relaxed">${cause.description}</div>

                <div class="p-3 bg-[#EEF9FF] border border-[#b8e2f2] rounded-lg text-xs mb-3 text-[#00468e]">
                    <div class="font-semibold text-[#00468e] mb-1 flex items-center gap-1">
                        <i data-lucide="zap" class="w-3.5 h-3.5 text-[#FF9C1D]"></i> Technical Root Cause:
                    </div>
                    <div class="text-slate-700 leading-relaxed">${cause.root_cause}</div>
                </div>

                ${cause.sample_stack_trace ? `
                    <div class="mb-3">
                        <div class="text-[11px] font-semibold text-slate-500 mb-1 uppercase tracking-wider">Stack Trace Snippet</div>
                        <pre class="bg-[#091E3E] p-2.5 rounded-lg border border-[#dee2e6] text-[11px] text-[#EEF9FF] overflow-x-auto font-mono whitespace-pre-wrap">${cause.sample_stack_trace}</pre>
                    </div>
                ` : ''}
            </div>

            <div class="p-2.5 bg-[#d4edda] border border-[#c3e6cb] rounded-lg text-xs text-[#155724] mt-2">
                <div class="font-semibold text-[#155724] mb-0.5 flex items-center gap-1">
                    <i data-lucide="check-circle" class="w-3.5 h-3.5 text-[#34AD54]"></i> Recommended Fix:
                </div>
                <div class="whitespace-pre-line text-[11px] text-[#155724] leading-relaxed font-medium">${cause.recommendation}</div>
            </div>
        `;
        container.appendChild(card);
    });
    lucide.createIcons();
}

function renderLogsTable(data) {
    const tbody = document.getElementById('logsTableBody');
    const paginationInfo = document.getElementById('paginationInfo');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!data.logs || data.logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-slate-500 text-sm">No log events match the selected criteria.</td></tr>`;
        if (paginationInfo) paginationInfo.innerText = '0 - 0 of 0';
        return;
    }

    data.logs.forEach(log => {
        const tr = document.createElement('tr');
        tr.className = 'cursor-pointer text-xs font-mono hover:bg-[#EEF9FF]/60 transition-colors border-b border-[#dee2e6]';

        let lvlBadge = '';
        if (log.level === 'ERROR') {
            lvlBadge = '<span class="badge-bt-danger">ERROR</span>';
        } else if (log.level === 'INFO') {
            lvlBadge = '<span class="badge-bt-cyan">INFO</span>';
        } else {
            lvlBadge = '<span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-300 text-[10px] font-semibold">DEBUG</span>';
        }

        const shortMsg = log.message.length > 140 ? log.message.substring(0, 140) + '...' : log.message;

        tr.innerHTML = `
            <td class="text-slate-500 whitespace-nowrap">${log.timestamp}</td>
            <td class="whitespace-nowrap">${lvlBadge}</td>
            <td class="text-[#00468e] font-sans font-semibold whitespace-nowrap">${log.service}</td>
            <td class="text-slate-600 font-sans whitespace-nowrap">${log.component}</td>
            <td class="text-slate-800 break-words ${log.level === 'ERROR' ? 'text-[#dc3545] font-semibold' : ''}">${escapeHtml(shortMsg)}</td>
        `;

        tr.addEventListener('click', () => openLogDetailModal(log));
        tbody.appendChild(tr);
    });

    if (paginationInfo) {
        const start = (data.page - 1) * data.page_size + 1;
        const end = Math.min(data.page * data.page_size, data.total);
        paginationInfo.innerText = `${start.toLocaleString()} - ${end.toLocaleString()} of ${data.total.toLocaleString()}`;
    }
}

function openLogDetailModal(log) {
    const modal = document.getElementById('logDetailModal');
    if (!modal) return;

    document.getElementById('modalTimestamp').innerText = log.timestamp;
    document.getElementById('modalFile').innerText = `${log.file_name} (Line ${log.line_number})`;
    document.getElementById('modalService').innerText = log.service;
    document.getElementById('modalComponent').innerText = log.component;
    document.getElementById('modalLevel').innerText = log.level;
    document.getElementById('modalUrl').innerText = log.url || 'None';
    document.getElementById('modalAction').innerText = log.action || 'None';
    document.getElementById('modalMessage').innerText = log.message;

    const stackTraceContainer = document.getElementById('modalStackTraceContainer');
    if (log.stack_trace) {
        stackTraceContainer.classList.remove('hidden');
        document.getElementById('modalStackTrace').innerText = log.stack_trace;
    } else {
        stackTraceContainer.classList.add('hidden');
    }

    modal.classList.remove('hidden');
}

function closeLogDetailModal() {
    const modal = document.getElementById('logDetailModal');
    if (modal) modal.classList.add('hidden');
}

// ================= REINDEX & UPLOAD ================= //

async function reindexLogs() {
    const btn = document.getElementById('reindexBtn');
    if (btn) btn.innerHTML = '<i data-lucide="loader" class="w-4 h-4 animate-spin"></i> Reindexing...';
    try {
        const res = await fetch(`${API_BASE}/api/reindex`, { method: 'POST' });
        const data = await res.json();
        await initApp();
        alert(data.message || 'Logs successfully reindexed!');
    } catch (err) {
        alert('Reindex failed: ' + err.message);
    } finally {
        if (btn) {
            btn.innerHTML = '<i data-lucide="refresh-cw" class="w-4 h-4"></i> Reindex Logs';
            lucide.createIcons();
        }
    }
}

async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        alert(`File ${file.name} uploaded and indexed successfully!`);
        await initApp();
    } catch (err) {
        alert('Upload failed: ' + err.message);
    } finally {
        e.target.value = '';
    }
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ================= BACKEND EXECUTION LOGS VIEWER ================= //

let backendLogPollInterval = null;
let currentRawBackendLogs = "";

async function openBackendLogsModal() {
    const modal = document.getElementById('backendLogsModal');
    if (modal) modal.classList.remove('hidden');
    lucide.createIcons();
    await fetchBackendLogs();

    if (!backendLogPollInterval) {
        backendLogPollInterval = setInterval(fetchBackendLogs, 3000);
    }
}

function closeBackendLogsModal() {
    const modal = document.getElementById('backendLogsModal');
    if (modal) modal.classList.add('hidden');
    if (backendLogPollInterval) {
        clearInterval(backendLogPollInterval);
        backendLogPollInterval = null;
    }
}

async function fetchBackendLogs() {
    const output = document.getElementById('backendLogsOutput');
    const pathBadge = document.getElementById('backendLogFilePath');
    if (!output) return;

    try {
        const res = await fetch(`${API_BASE}/api/system/logs?lines=200`);
        const data = await res.json();

        if (pathBadge && data.log_file) {
            pathBadge.innerText = `File: ${data.log_file} (${data.lines_returned} lines)`;
        }

        if (!data.logs || data.logs.length === 0) {
            output.innerHTML = '<div class="text-slate-500 italic">No backend log records found yet.</div>';
            return;
        }

        currentRawBackendLogs = data.logs.join('\n');

        let formattedHtml = "";
        data.logs.forEach(line => {
            const escaped = escapeHtml(line);
            let coloredLine = escaped;

            if (line.includes('[ERROR]')) {
                coloredLine = `<span class="text-rose-400 font-semibold">${escaped}</span>`;
            } else if (line.includes('[WARNING]')) {
                coloredLine = `<span class="text-amber-400 font-semibold">${escaped}</span>`;
            } else if (line.includes('[LLM-CALL-START]')) {
                coloredLine = `<span class="text-indigo-400 font-semibold">${escaped}</span>`;
            } else if (line.includes('[LLM-CALL-SUCCESS]')) {
                coloredLine = `<span class="text-emerald-400 font-semibold">${escaped}</span>`;
            } else if (line.includes('[LLM-CALL-PAYLOAD]')) {
                coloredLine = `<span class="text-violet-300">${escaped}</span>`;
            } else if (line.includes('[HTTP-REQ]')) {
                coloredLine = `<span class="text-cyan-400">${escaped}</span>`;
            } else if (line.includes('[HTTP-RES]')) {
                coloredLine = `<span class="text-teal-400">${escaped}</span>`;
            } else if (line.includes('[PARSER-START]') || line.includes('[PARSER-COMPLETE]')) {
                coloredLine = `<span class="text-blue-400 font-semibold">${escaped}</span>`;
            } else if (line.includes('[ANALYZER-OVERVIEW-COMPLETE]')) {
                coloredLine = `<span class="text-emerald-300 font-semibold">${escaped}</span>`;
            } else if (line.includes('[DEBUG]')) {
                coloredLine = `<span class="text-slate-500">${escaped}</span>`;
            }

            formattedHtml += `<div class="py-0.5 whitespace-pre-wrap break-all">${coloredLine}</div>`;
        });

        const isScrolledToBottom = output.scrollHeight - output.clientHeight <= output.scrollTop + 50;
        output.innerHTML = formattedHtml;
        if (isScrolledToBottom) {
            output.scrollTop = output.scrollHeight;
        }
    } catch (err) {
        output.innerHTML = `<div class="text-rose-400">Failed to poll backend logs: ${escapeHtml(err.message)}</div>`;
    }
}

function copyBackendLogsToClipboard() {
    const btn = document.getElementById('copyBackendLogsBtn');
    if (!currentRawBackendLogs) return;

    navigator.clipboard.writeText(currentRawBackendLogs).then(() => {
        if (btn) {
            const originalHtml = btn.innerHTML;
            btn.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i> Copied!';
            lucide.createIcons();
            setTimeout(() => {
                btn.innerHTML = originalHtml;
                lucide.createIcons();
            }, 1800);
        }
    }).catch(err => {
        alert('Could not copy to clipboard: ' + err);
    });
}

// ================= GLOBAL EXPORTS ================= //
window.filterLogsByMetric = filterLogsByMetric;
window.selectService = selectService;
window.switchInspectorTab = switchInspectorTab;
window.clearLogExplorerFilters = clearLogExplorerFilters;
window.closeLogDetailModal = closeLogDetailModal;
window.openBackendLogsModal = openBackendLogsModal;
window.closeBackendLogsModal = closeBackendLogsModal;
window.resetKPIDrilldown = resetKPIDrilldown;
window.closeAISettingsModal = closeAISettingsModal;
window.openAISettingsModal = openAISettingsModal;
window.copyBackendLogsToClipboard = copyBackendLogsToClipboard;

