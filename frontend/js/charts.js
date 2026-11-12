// Chart.js visualizations for BillTrax ServiceLog Intelligence Hub
// Exact Brand Palette Extracted From BillTrax Platform:
// Primary Orange (#FF9C1D), Deep Navy (#091E3E), Royal Blue (#00468E), Slate Blue (#597A9D), Emerald (#10B981), Crimson (#DC2626)

let statusChartInstance = null;
let serviceVolumeChartInstance = null;
let errorCausesChartInstance = null;
let timelineChartInstance = null;

const BT_FONT_FAMILY = "'Montserrat', 'Rubik', sans-serif";
const BT_TICK_COLOR = '#64748B';
const BT_GRID_COLOR = '#F1F5F9';

const BT_TOOLTIP_CONFIG = {
    backgroundColor: '#091E3E',
    titleColor: '#FFFFFF',
    titleFont: { family: BT_FONT_FAMILY, size: 12, weight: 'bold' },
    bodyColor: '#F8FAFC',
    bodyFont: { family: BT_FONT_FAMILY, size: 11 },
    borderColor: '#FF9C1D',
    borderWidth: 1.5,
    padding: 12,
    cornerRadius: 10,
    boxPadding: 6,
    usePointStyle: true,
};

function initCharts(overview, services, errorCauses, timeline, selectedService = 'ALL') {
    if (overview) initStatusChart(overview, selectedService);
    if (services && Array.isArray(services)) initServiceVolumeChart(services, selectedService);
    if (errorCauses) initErrorCausesChart(errorCauses, selectedService);
    if (timeline && Array.isArray(timeline)) initTimelineChart(timeline, selectedService);
}

function initStatusChart(overview, selectedService = 'ALL') {
    const ctx = document.getElementById('statusDistributionChart');
    if (!ctx || !overview) return;

    if (statusChartInstance) {
        statusChartInstance.destroy();
    }

    let success = overview.successful_records || 0;
    let failed = overview.failed_records > 0 ? overview.failed_records : (overview.total_error_logs || 0);

    // If a service has 0 processed records (e.g. daily report), display clean status
    if (success === 0 && failed === 0) {
        success = 1; // display 100% healthy
    }

    statusChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Successful Records', 'Errors / Failed Records'],
            datasets: [{
                data: [success, failed],
                backgroundColor: ['#10B981', '#DC2626'],
                hoverBackgroundColor: ['#059669', '#B91C1C'],
                borderColor: '#FFFFFF',
                borderWidth: 3,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: BT_TICK_COLOR,
                        font: { family: BT_FONT_FAMILY, size: 11, weight: 600 },
                        padding: 12,
                        usePointStyle: true,
                        boxWidth: 8
                    }
                },
                tooltip: {
                    ...BT_TOOLTIP_CONFIG,
                    callbacks: {
                        label: function(context) {
                            const val = context.raw || 0;
                            const total = success + failed;
                            const pct = total > 0 ? ((val / total) * 100).toFixed(1) : '100.0';
                            return ` ${context.label}: ${val.toLocaleString()} (${pct}%)`;
                        }
                    }
                }
            },
            cutout: '74%'
        }
    });

    // Update center badge
    const badge = document.getElementById('successRateCenterBadge');
    if (badge) {
        badge.innerText = `${overview.success_rate_percent}%`;
    }
}

function formatChartServiceName(name) {
    if (!name) return '';
    return name
        .replace(/([a-z])([A-Z])/g, '$1 $2')
        .replace(/[-_]/g, ' ')
        .trim();
}

function initServiceVolumeChart(services, selectedService = 'ALL') {
    const ctx = document.getElementById('serviceVolumeChart');
    if (!ctx || !services || !Array.isArray(services)) return;

    if (serviceVolumeChartInstance) {
        serviceVolumeChartInstance.destroy();
    }

    if (selectedService === 'ALL') {
        // Multi-service comparison view - dynamically formatted labels
        const labels = services.map(s => formatChartServiceName(s.name));

        const processedData = services.map(s => s.records_processed);
        const successData = services.map(s => s.successful_records);
        const failedData = services.map(s => s.failed_records > 0 ? s.failed_records : s.errors_count);

        serviceVolumeChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Processed',
                        data: processedData,
                        backgroundColor: '#00468E',
                        borderRadius: 6,
                        borderSkipped: false
                    },
                    {
                        label: 'Successful',
                        data: successData,
                        backgroundColor: '#10B981',
                        borderRadius: 6,
                        borderSkipped: false
                    },
                    {
                        label: 'Failed / Errors',
                        data: failedData,
                        backgroundColor: '#DC2626',
                        borderRadius: 6,
                        borderSkipped: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 10.5, weight: 600 } }
                    },
                    y: {
                        grid: { color: BT_GRID_COLOR },
                        ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 10.5 } }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 11, weight: 600 }, usePointStyle: true, boxWidth: 8, padding: 10 }
                    },
                    tooltip: BT_TOOLTIP_CONFIG
                }
            }
        });
    } else {
        // Single focused service throughput breakdown
        const svc = services.find(s => s.name === selectedService) || {
            name: selectedService,
            records_processed: 0,
            successful_records: 0,
            failed_records: 0,
            errors_count: 0
        };

        const failedVal = svc.failed_records > 0 ? svc.failed_records : svc.errors_count;

        serviceVolumeChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Processed', 'Successful', 'Failed / Errors'],
                datasets: [{
                    label: `${svc.name} Metrics`,
                    data: [svc.records_processed, svc.successful_records, failedVal],
                    backgroundColor: ['#00468E', '#10B981', '#DC2626'],
                    borderRadius: 6,
                    borderSkipped: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 11, weight: 600 } }
                    },
                    y: {
                        grid: { color: BT_GRID_COLOR },
                        ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 10.5 } }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: BT_TOOLTIP_CONFIG
                }
            }
        });
    }
}

function initErrorCausesChart(causes, selectedService = 'ALL') {
    const ctx = document.getElementById('errorCausesChart');
    if (!ctx) return;

    if (errorCausesChartInstance) {
        errorCausesChartInstance.destroy();
    }

    const causesList = Array.isArray(causes) ? causes : [];
    const filteredCauses = (selectedService === 'ALL') 
        ? causesList 
        : causesList.filter(c => c.service === selectedService);

    let labels = [];
    let counts = [];
    let bgColors = [];

    if (filteredCauses.length === 0) {
        labels = ['0 Recorded Errors (Healthy)'];
        counts = [0];
        bgColors = ['#10B981'];
    } else {
        const palette = ['#DC2626', '#FF9C1D', '#00468E', '#6B7280', '#06A3DA', '#8B5CF6'];
        labels = filteredCauses.map(c => {
            const shortTitle = c.title ? c.title.split(' in ')[0].split(' (')[0].trim() : (c.error_type || c.cause_id);
            return shortTitle.length > 25 ? shortTitle.substring(0, 25) + '...' : shortTitle;
        });
        counts = filteredCauses.map(c => c.count);
        bgColors = filteredCauses.map((c, idx) => palette[idx % palette.length]);
    }

    errorCausesChartInstance = new Chart(ctx, {
        type: 'bar',
        indexAxis: 'y',
        data: {
            labels: labels,
            datasets: [{
                label: 'Occurrences',
                data: counts,
                backgroundColor: bgColors,
                borderRadius: 6,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: BT_GRID_COLOR },
                    ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 10.5 } }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 11, weight: 600 } }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: BT_TOOLTIP_CONFIG
            }
        }
    });
}

function initTimelineChart(timeline, selectedService = 'ALL') {
    const ctx = document.getElementById('timelineChart');
    if (!ctx || !timeline || !Array.isArray(timeline)) return;

    if (timelineChartInstance) {
        timelineChartInstance.destroy();
    }

    const labels = timeline.map(t => {
        const parts = t.time_bucket.split(' ');
        const d = parts[0] ? parts[0].substring(5) : '';
        const h = parts[1] ? parts[1].split(':')[0] + 'h' : '';
        return `${d} ${h}`;
    });

    const totalLogs = timeline.map(t => t.total);
    const errors = timeline.map(t => t.errors);

    const activityLabel = selectedService === 'ALL' ? 'Total Activity' : `${selectedService} Activity`;

    let gradientActivity = 'rgba(0, 70, 142, 0.08)';
    let gradientErrors = 'rgba(220, 38, 38, 0.12)';
    try {
        const c2d = ctx.getContext('2d');
        const g1 = c2d.createLinearGradient(0, 0, 0, 140);
        g1.addColorStop(0, 'rgba(0, 70, 142, 0.25)');
        g1.addColorStop(1, 'rgba(0, 70, 142, 0.01)');
        gradientActivity = g1;

        const g2 = c2d.createLinearGradient(0, 0, 0, 140);
        g2.addColorStop(0, 'rgba(220, 38, 38, 0.25)');
        g2.addColorStop(1, 'rgba(220, 38, 38, 0.01)');
        gradientErrors = g2;
    } catch (e) {
        // Fallback to static rgba
    }

    timelineChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: activityLabel,
                    data: totalLogs,
                    borderColor: '#00468E',
                    backgroundColor: gradientActivity,
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: 3,
                    pointBackgroundColor: '#00468E',
                    pointHoverRadius: 6,
                    pointHoverBackgroundColor: '#FF9C1D'
                },
                {
                    label: 'Errors Recorded',
                    data: errors,
                    borderColor: '#DC2626',
                    backgroundColor: gradientErrors,
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: 4,
                    pointBackgroundColor: '#DC2626',
                    pointHoverRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 10.5 }, maxRotation: 45 }
                },
                y: {
                    grid: { color: BT_GRID_COLOR },
                    ticks: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 10.5 } }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: BT_TICK_COLOR, font: { family: BT_FONT_FAMILY, size: 11, weight: 600 }, usePointStyle: true, boxWidth: 8, padding: 10 }
                },
                tooltip: BT_TOOLTIP_CONFIG
            }
        }
    });
}

// Global exports for charts
window.initCharts = initCharts;
window.initStatusChart = initStatusChart;
window.initServiceVolumeChart = initServiceVolumeChart;
window.initErrorCausesChart = initErrorCausesChart;
window.initTimelineChart = initTimelineChart;

