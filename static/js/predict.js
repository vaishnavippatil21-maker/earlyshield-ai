/**
 * predict.js
 * Handles the prediction form submit, talks to /api/predict, and renders
 * the risk gauge, contributing factors, and recommended actions inline
 * without a full page reload.
 */

(function () {
    const form = document.getElementById("predictForm");
    if (!form) return;

    const loadingOverlay = document.getElementById("loadingOverlay");
    const emptyState = document.getElementById("emptyResultState");
    const resultPanel = document.getElementById("predictionResult");
    const predictBtn = document.getElementById("predictBtn");

    let gaugeChartInstance = null;

    form.addEventListener("submit", async function (event) {
        event.preventDefault();

        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());

        emptyState.style.display = "none";
        resultPanel.classList.remove("visible");
        loadingOverlay.classList.add("visible");
        predictBtn.disabled = true;
        predictBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Scoring...';

        try {
            const response = await fetch("/api/predict", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Prediction failed.");
            }

            renderResult(data);
        } catch (err) {
            emptyState.style.display = "block";
            emptyState.innerHTML = `<i class="bi bi-exclamation-triangle"></i>${err.message}`;
        } finally {
            loadingOverlay.classList.remove("visible");
            predictBtn.disabled = false;
            predictBtn.innerHTML = '<i class="bi bi-cpu me-1"></i>Predict Risk';
        }
    });

    function renderResult(data) {
        document.getElementById("resultProbability").textContent = data.risk_probability + "%";
        document.getElementById("resultConfidence").textContent = data.confidence_score + "%";

        const badge = document.getElementById("resultBadge");
        badge.textContent = data.risk_category + " Risk";
        badge.className = "risk-badge mt-2 risk-" + data.risk_category.toLowerCase();

        if (gaugeChartInstance) {
            gaugeChartInstance.destroy();
        }
        const gaugeCtx = document.getElementById("resultGauge");
        gaugeChartInstance = new Chart(gaugeCtx, {
            type: "doughnut",
            data: {
                datasets: [{
                    data: [data.risk_probability, 100 - data.risk_probability],
                    backgroundColor: [gaugeColorForCategory(data.risk_category), "#E4E8F0"],
                    borderWidth: 0,
                }],
            },
            options: {
                rotation: -90,
                circumference: 180,
                cutout: "75%",
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                animation: { animateRotate: true, duration: 700 },
            },
        });

        const factorsList = document.getElementById("factorsList");
        factorsList.innerHTML = data.contributing_factors.map(function (factor) {
            const icon = factor.severity === "high" ? "bi-exclamation-triangle-fill"
                : factor.severity === "medium" ? "bi-dash-circle-fill" : "bi-check-circle-fill";
            return `
                <div class="factor-row">
                    <div class="factor-icon ${factor.severity}"><i class="bi ${icon}"></i></div>
                    <div>
                        <h4>${factor.label}</h4>
                        <p>${factor.detail}</p>
                    </div>
                </div>`;
        }).join("");

        const actionsList = document.getElementById("actionsList");
        actionsList.innerHTML = data.recommended_actions.map(function (action) {
            return `
                <div class="action-item">
                    <div>
                        <h4>${action.action}</h4>
                        <p>${action.reason}</p>
                    </div>
                    <span class="action-priority">${action.priority}</span>
                </div>`;
        }).join("");

        document.getElementById("downloadReportBtn").href = `/history/${data.prediction_id}/report`;

        resultPanel.classList.add("visible");
    }

    function gaugeColorForCategory(category) {
    if (category === "High") return "#C23A3A";
    if (category === "Medium") return "#B8790A";
    return "#12876B";
    }
})();
