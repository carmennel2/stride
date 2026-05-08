// Stride client-side script.
// Initialises Chart.js charts and the browser-notification flow.
// Each helper looks up its data from a JSON <script> tag in the page —
// templates render the data with |tojson into those tags and we read it
// here, which keeps the JS portable and the data well-escaped.

(function () {
    'use strict';

    function readJson(elementId) {
        var el = document.getElementById(elementId);
        if (!el) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    }

    function initSubjectPie() {
        var canvas = document.getElementById('subjectChart');
        var data = readJson('subject-chart-data');
        if (!canvas || !data || !data.labels.length) return;
        new Chart(canvas, {
            type: 'pie',
            data: {
                labels: data.labels,
                datasets: [{ data: data.hours, backgroundColor: data.colors }],
            },
            options: {
                responsive: true,
                plugins: { legend: { position: 'bottom' } },
            },
        });
    }

    function initWeekdayBar() {
        var canvas = document.getElementById('weekdayChart');
        var data = readJson('weekday-chart-data');
        if (!canvas || !data) return;
        var total = data.hours.reduce(function (a, b) { return a + b; }, 0);
        if (total <= 0) return;
        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Hours',
                    data: data.hours,
                    backgroundColor: '#10b981',
                }],
            },
            options: {
                responsive: true,
                scales: {
                    y: { beginAtZero: true,
                         title: { display: true, text: 'Hours' } },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    function initScatter() {
        var canvas = document.getElementById('scatterChart');
        var data = readJson('scatter-chart-data');
        if (!canvas || !data || !data.points.length) return;
        var diagonal = [{ x: 0, y: 0 }, { x: data.maxAxis, y: data.maxAxis }];
        new Chart(canvas, {
            data: {
                datasets: [
                    { type: 'scatter', label: 'Tasks', data: data.points,
                      backgroundColor: '#10b981' },
                    { type: 'line', label: 'predicted = actual', data: diagonal,
                      borderColor: 'rgba(0,0,0,0.25)', borderDash: [4, 4],
                      pointRadius: 0, fill: false },
                ],
            },
            options: {
                responsive: true,
                scales: {
                    x: { title: { display: true, text: 'Predicted (min)' },
                         beginAtZero: true },
                    y: { title: { display: true, text: 'Actual (min)' },
                         beginAtZero: true },
                },
                plugins: { legend: { position: 'bottom' } },
            },
        });
    }

    function initDrift() {
        var canvas = document.getElementById('driftChart');
        var data = readJson('drift-chart-data');
        if (!canvas || !data || !data.series.length) return;
        new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.series.map(function (d) { return d.x; }),
                datasets: [{
                    label: 'Delta (actual − predicted)',
                    data: data.series.map(function (d) { return d.y; }),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16,185,129,0.1)',
                    tension: 0.2,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                scales: {
                    y: { title: { display: true, text: 'Minutes off' } },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    // Browser notifications for tasks due today / tomorrow.
    // In-tab only — Web Push (service worker + VAPID) would also fire when
    // the page is closed, but it's out of scope here.
    function initNotifications() {
        if (!('Notification' in window)) return;
        var btn = document.getElementById('notifyBtn');
        var label = document.getElementById('notifyBtnLabel');
        var targets = readJson('notify-targets-data') || [];
        if (!btn || !label) return;

        function refreshButton() {
            btn.classList.remove('d-none');
            if (Notification.permission === 'granted') {
                label.textContent = 'Reminders enabled';
                btn.disabled = true;
            } else if (Notification.permission === 'denied') {
                label.textContent = 'Reminders blocked by your browser';
                btn.disabled = true;
            } else {
                label.textContent = 'Enable due-task reminders';
                btn.disabled = false;
            }
        }

        // One notification per task per day, deduplicated via localStorage.
        function fireFor(items) {
            var today = new Date().toISOString().slice(0, 10);
            var seen = JSON.parse(localStorage.getItem('stride.notified') || '{}');
            for (var i = 0; i < items.length; i++) {
                var t = items[i];
                var key = today + ':' + t.id;
                if (seen[key]) continue;
                new Notification('Due ' + t.due_label + ': ' + t.title, {
                    body: t.subject,
                    tag: 'stride-task-' + t.id,
                });
                seen[key] = 1;
            }
            localStorage.setItem('stride.notified', JSON.stringify(seen));
        }

        btn.addEventListener('click', function () {
            Notification.requestPermission().then(function (perm) {
                refreshButton();
                if (perm === 'granted') fireFor(targets);
            });
        });

        refreshButton();
        if (Notification.permission === 'granted') fireFor(targets);
    }

    document.addEventListener('DOMContentLoaded', function () {
        initSubjectPie();
        initWeekdayBar();
        initScatter();
        initDrift();
        initNotifications();
    });
})();
