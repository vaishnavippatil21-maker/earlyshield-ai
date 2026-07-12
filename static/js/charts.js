/**
 * charts.js
 * Chart.js renderers for the dashboard, prediction result gauge, and
 * analytics page. Kept separate from app.js since not every page needs it.
 */

const RISK_COLORS = {
    low: "#12876B",
    medium: "#B8790A",
    high: "#C23A3A",
};

function getCssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function renderDashboardCharts(stats) {
    const pieCtx = document.getElementById("riskPieChart");
    if (pieCtx) {
        new Chart(pieCtx, {
            type: "doughnut",
            data: {
                labels: ["Low Risk", "Medium Risk", "High Risk"],
                datasets: [{
                    data: [stats.low, stats.medium, stats.high],
                    backgroundColor: [RISK_COLORS.low, RISK_COLORS.medium, RISK_COLORS.high],
                    borderWidth: 0,
                }],
            },
            options: {
                cutout: "68%",
                plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } } },
            },
        });
    }

    const barCtx = document.getElementById("riskBarChart");
    if (barCtx) {
        new Chart(barCtx, {
            type: "bar",
            data: {
                labels: ["Low", "Medium", "High"],
                datasets: [{
                    data: [stats.low, stats.medium, stats.high],
                    backgroundColor: [RISK_COLORS.low, RISK_COLORS.medium, RISK_COLORS.high],
                    borderRadius: 8,
                    maxBarThickness: 46,
                }],
            },
            options: {
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.05)" } },
                    x: { grid: { display: false } },
                },
            },
        });
    }

    const gaugeCtx = document.getElementById("avgRiskGauge");
    if (gaugeCtx) {
        renderGauge(gaugeCtx, stats.avgRisk);
    }
}

/** Half-donut gauge - the signature visual reused on the result panel + PDF context. */
function renderGauge(ctx, value) {
    const clamped = Math.max(0, Math.min(100, value));
    new Chart(ctx, {
        type: "doughnut",
        data: {
            datasets: [{
                data: [clamped, 100 - clamped],
                backgroundColor: [gaugeColorForValue(clamped), "#E4E8F0"],
                borderWidth: 0,
            }],
        },
        options: {
            rotation: -90,
            circumference: 180,
            cutout: "75%",
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
        },
    });
}

function gaugeColorForValue(value) {
    if (value >= 65) return RISK_COLORS.high;
    if (value >= 35) return RISK_COLORS.medium;
    return RISK_COLORS.low;
}

function renderAnalyticsCharts(data) {
    const pieCtx = document.getElementById("analyticsRiskPie");
    if (pieCtx) {
        new Chart(pieCtx, {
            type: "pie",
            data: {
                labels: ["Low", "Medium", "High"],
                datasets: [{
                    data: [data.risk_distribution.Low, data.risk_distribution.Medium, data.risk_distribution.High],
                    backgroundColor: [RISK_COLORS.low, RISK_COLORS.medium, RISK_COLORS.high],
                    borderWidth: 0,
                }],
            },
            options: { plugins: { legend: { position: "bottom" } } },
        });
    }

    const monthlyCtx = document.getElementById("monthlyPredictionsChart");
    if (monthlyCtx) {
        new Chart(monthlyCtx, {
            type: "line",
            data: {
                labels: data.monthly_predictions.map((m) => m.month),
                datasets: [{
                    label: "Predictions",
                    data: data.monthly_predictions.map((m) => m.count),
                    borderColor: "#1F6FEB",
                    backgroundColor: "rgba(31,111,235,0.12)",
                    fill: true,
                    tension: 0.35,
                    pointRadius: 3,
                }],
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }
}
