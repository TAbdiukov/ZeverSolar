"use strict";

const $ = (id) => document.getElementById(id);
const form = $("filters");
const views = {hourly: 3, daily: 30, weekly: 182, monthly: 730, annual: 3650};
const fmt = (n, digits = 1) => Number(n).toLocaleString("en-GB", {maximumFractionDigits: digits});

function localDate(daysAgo) {
  const day = new Date();
  day.setHours(12, 0, 0, 0);
  day.setDate(day.getDate() - daysAgo);
  const pad = (value) => String(value).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth()+1)}-${pad(day.getDate())}`;
}

function setDates(view) {
  $("to").value = localDate(0);
  $("from").value = localDate(views[view] - 1);
}

function setHours() {
  for (let hour = 0; hour <= 24; hour++) {
    const label = `${String(hour).padStart(2, "0")}:00`;
    if (hour < 24) $("hour_from").add(new Option(label, String(hour)));
    if (hour > 0) $("hour_to").add(new Option(label, String(hour)));
  }
  $("hour_from").value = "0";
  $("hour_to").value = "24";
}

function svgNode(tag, attributes, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes || {})) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

function drawChart(periods) {
  const area = $("chart");
  area.replaceChildren();
  if (!periods.length || periods.every((p) => p.kwh === null)) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = periods.length ? "No readings for these filters. Try a different period." : "No eligible periods in this date range.";
    area.append(empty);
    return;
  }
  const scroll = $("chart-scroll");
  const width = Math.max(scroll.clientWidth - 24, periods.length * 19 + 86, 650);
  const height = 320, top = 30, bottom = 266, left = 56, right = width - 23;
  const usable = right - left;
  const step = usable / periods.length;
  const maximum = Math.max(...periods.map((period) => period.kwh || 0), 0.001);
  const axisMax = maximum * 1.13;
  const svg = svgNode("svg", {viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": "Energy by period, showing recorded, partial and missing observations"});
  for (let index = 0; index <= 4; index++) {
    const value = axisMax * index / 4;
    const y = bottom - (bottom - top) * index / 4;
    svg.append(svgNode("line", {x1: left, x2: right, y1: y, y2: y, class: "grid"}));
    svg.append(svgNode("text", {x: left - 11, y: y + 4, "text-anchor": "end", class: "axis-label"}, fmt(value)));
  }
  const tickEvery = Math.max(1, Math.ceil(periods.length / Math.max(5, Math.floor(width / 110))));
  for (let i = 0; i < periods.length; i++) {
    const period = periods[i];
    const centre = left + (i + .5) * step;
    const barWidth = Math.max(3, Math.min(26, step - 5));
    const tooltip = `${period.label}: ${period.kwh === null ? "No reading" : fmt(period.kwh, 3) + " kWh"} · ${period.recorded}/${period.expected} inverter-periods recorded`;
    if (period.kwh !== null) {
      const barHeight = Math.max(1.5, period.kwh / axisMax * (bottom - top));
      const rect = svgNode("rect", {x: centre - barWidth / 2, y: bottom - barHeight, width: barWidth, height: barHeight, rx: 2,
        fill: period.status === "partial" ? "#cc9d55" : "#397a65", class: "bar"});
      rect.append(svgNode("title", {}, tooltip));
      svg.append(rect);
    } else {
      const mark = svgNode("line", {x1: centre - barWidth / 2, x2: centre + barWidth / 2, y1: bottom - 2, y2: bottom - 2, class: "missing-line"});
      mark.append(svgNode("title", {}, tooltip));
      svg.append(mark);
    }
    if (i % tickEvery === 0 || i === periods.length - 1) {
      let shortLabel = period.label.replace(/^w\/c /, "");
      if (shortLabel.match(/^\d{2} \w{3} 20\d{2}$/)) shortLabel = shortLabel.slice(0, 6);
      if (shortLabel.match(/^\d{2} \w{3} \d{2}:\d{2}$/)) shortLabel = shortLabel.slice(0, 6) + " " + shortLabel.slice(7);
      svg.append(svgNode("text", {x: centre, y: bottom + 23, class: "axis-label", "text-anchor": "middle"}, shortLabel));
    }
  }
  area.append(svg);
  scroll.scrollLeft = scroll.scrollWidth;
}

function renderTable(periods) {
  const body = $("readings-table");
  body.replaceChildren();
  for (const row of periods) {
    const tr = document.createElement("tr");
    const status = row.status === "recorded" ? "Recorded" : row.status === "partial" ? "Partial" : "No reading";
    const cells = [row.label, row.kwh === null ? "—" : fmt(row.kwh, 3), `${row.recorded} / ${row.expected}`, status];
    for (let index = 0; index < cells.length; index++) {
      const td = document.createElement("td");
      if (index !== 0) td.classList.add("text-end");
      if (index === 1) td.classList.add("energy-cell");
      if (index === 3) {
        const badge = document.createElement("span");
        badge.className = `status-label status-${row.status}`;
        badge.textContent = cells[index];
        td.append(badge);
      } else td.textContent = cells[index];
      tr.append(td);
    }
    body.append(tr);
  }
  if (!periods.length) {
    const tr = document.createElement("tr"), td = document.createElement("td");
    td.colSpan = 4; td.className = "text-center py-5"; td.textContent = "No eligible periods for these filters";
    tr.append(td); body.append(tr);
  }
  $("table-count").textContent = `${fmt(periods.length, 0)} periods`;
}

function updateInverters(serials) {
  const select = $("inverter");
  const previous = select.value;
  select.replaceChildren(new Option("All inverters · combined", "all"));
  serials.forEach((serial) => select.add(new Option(serial, serial)));
  select.value = serials.includes(previous) ? previous : "all";
}

function render(data) {
  updateInverters(data.serials);
  const stats = data.summary;
  $("stat-kwh").textContent = `${fmt(stats.kwh)} kWh`;
  $("stat-kwh-sub").textContent = data.basis === "daily meter maxima" ? "Sum of recorded daily meter totals" : "Sum of observed short intervals";
  $("stat-recorded").textContent = `${fmt(stats.with_data, 0)} / ${fmt(stats.total, 0)}`;
  $("stat-missing").textContent = fmt(stats.missing, 0);
  $("stat-missing-sub").textContent = `${stats.partial} additional partially recorded period${stats.partial === 1 ? "" : "s"}`;
  const latest = stats.latest_power;
  $("stat-power").textContent = latest.watts === null ? "—" : `${fmt(latest.watts, 0)} W`;
  $("stat-power-sub").textContent = latest.last_seen ? `Last sample: ${latest.last_seen.slice(0, 16)}` : "No inverter sample available";
  const titleMap = {hourly: "Hourly energy production", daily: "Daily energy production", weekly: "Weekly energy production", monthly: "Monthly energy production", annual: "Annual energy production"};
  $("chart-title").textContent = titleMap[data.granularity];
  $("chart-subtitle").textContent = `${data.from} to ${data.to} · ${data.selected.length} inverter${data.selected.length === 1 ? "" : "s"}`;
  $("basis").textContent = data.basis.toUpperCase();
  $("coverage-note").textContent = data.basis === "daily meter maxima" ?
    "Missing days stay visible. Recorded means at least one valid reading, not a complete day." :
    "Only consecutive readings ≤ 5 minutes apart are counted. Unmeasured generation is excluded.";
  drawChart(data.periods);
  renderTable(data.periods);
}

async function loadReadings() {
  const submit = $("apply"), error = $("error");
  error.classList.add("d-none");
  submit.disabled = true;
  submit.firstChild.textContent = "Loading view ";
  try {
    const query = new URLSearchParams(new FormData(form));
    const response = await fetch(`/api/readings?${query.toString()}`, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Unable to load readings");
    render(data);
  } catch (reason) {
    error.textContent = reason.message || "The dashboard could not load readings";
    error.classList.remove("d-none");
  } finally {
    submit.disabled = false;
    submit.firstChild.textContent = "Update view ";
  }
}

form.addEventListener("submit", (event) => {event.preventDefault(); loadReadings();});
$("granularity").addEventListener("change", () => {setDates($("granularity").value); loadReadings();});
$("reset").addEventListener("click", () => {
  form.reset(); setDates("daily"); $("hour_from").value = "0"; $("hour_to").value = "24"; loadReadings();
});
setHours();
setDates("daily");
loadReadings();
