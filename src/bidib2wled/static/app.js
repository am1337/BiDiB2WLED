const $ = (sel) => document.querySelector(sel);
const DEFAULT_COLOR = "FFFFFF";
let cfg = {};
let status = {};
let wizardOpened = false;
const editing = { kind: null, id: null };
let editingWindow = null;

function isEditing() {
  if (!$("#color-picker").classList.contains("hidden")) return true;
  const el = document.activeElement;
  if (!el) return false;
  if (el.closest("[data-address]")) return true;
  if (el.closest("#objects")) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

function showTab(name) {
  document.querySelectorAll("nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  document.querySelectorAll("main > section").forEach((s) => s.classList.add("hidden"));
  $(`#tab-${name}`).classList.remove("hidden");
}

document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    showTab(btn.dataset.tab);
    if (btn.dataset.tab === "config") loadYaml();
    if (btn.dataset.tab === "wizard") syncDiscovery();
  });
});

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    let msg = res.statusText;
    if (typeof detail === "string" && detail) msg = detail;
    else if (Array.isArray(detail)) {
      msg = detail.map((item) => item.msg || String(item)).join("; ");
    }
    throw new Error(msg || "Speichern fehlgeschlagen");
  }
  return data;
}

function notify(message, ok = true) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden", "toast-ok", "toast-bad");
  el.classList.add(ok ? "toast-ok" : "toast-bad");
  clearTimeout(notify._t);
  notify._t = setTimeout(() => el.classList.add("hidden"), 3500);
}

$("#toast").onclick = () => $("#toast").classList.add("hidden");

async function runAction(successMsg, fn) {
  try {
    const result = await fn();
    if (result === false) return;
    notify(successMsg, true);
  } catch (e) {
    notify(e.message || "Speichern fehlgeschlagen", false);
  }
}

function parseHex(value) {
  let s = String(value || "").trim().replace(/^#/, "").toUpperCase();
  if (/^[0-9A-F]{3}$/.test(s)) s = s.split("").map((c) => c + c).join("");
  return /^[0-9A-F]{6}$/.test(s) ? s : null;
}

function durationSeconds(value, fallback = 0) {
  const n = parseFloat(String(value ?? "").replace(/s$/i, "").trim());
  return Number.isFinite(n) ? n : fallback;
}

function durationToken(seconds) {
  return `${seconds}s`;
}

function hexToRgb(hex) {
  return {
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
  };
}

function rgbToHex(r, g, b) {
  const c = (n) => Math.max(0, Math.min(255, Number(n) || 0)).toString(16).padStart(2, "0");
  return (c(r) + c(g) + c(b)).toUpperCase();
}

function rgbToHsv(r, g, b) {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s: max ? d / max : 0, v: max };
}

function hsvToRgb(h, s, v) {
  const f = (n) => {
    const k = (n + h / 60) % 6;
    return v - v * s * Math.max(Math.min(k, 4 - k, 1), 0);
  };
  return {
    r: Math.round(f(5) * 255),
    g: Math.round(f(3) * 255),
    b: Math.round(f(1) * 255),
  };
}

const colorPicker = {
  field: null,
  h: 0,
  s: 0,
  v: 1,
};

function syncSwatch(field, hex) {
  const swatch = field.querySelector(".color-swatch");
  const parsed = parseHex(hex) || parseHex(field.querySelector("input").value) || "000000";
  swatch.style.background = `#${parsed}`;
}

function pickerHex() {
  const { r, g, b } = hsvToRgb(colorPicker.h, colorPicker.s, colorPicker.v);
  return rgbToHex(r, g, b);
}

function renderColorPicker(fromHexInput = false) {
  const hex = pickerHex();
  const rgb = hexToRgb(hex);
  $("#cp-preview").style.background = `#${hex}`;
  $("#cp-sv").style.setProperty("--pure-hue", `hsl(${colorPicker.h}, 100%, 50%)`);
  $("#cp-hue-marker").style.transform = `rotate(${colorPicker.h}deg) translateY(-3.15rem)`;
  $("#cp-sv-marker").style.left = `${colorPicker.s * 100}%`;
  $("#cp-sv-marker").style.top = `${(1 - colorPicker.v) * 100}%`;
  if (!fromHexInput && document.activeElement !== $("#cp-hex")) {
    $("#cp-hex").value = `#${hex}`;
  }
  if (document.activeElement !== $("#cp-r")) $("#cp-r").value = String(rgb.r);
  if (document.activeElement !== $("#cp-g")) $("#cp-g").value = String(rgb.g);
  if (document.activeElement !== $("#cp-b")) $("#cp-b").value = String(rgb.b);
  if (colorPicker.field) {
    colorPicker.field.querySelector("input").value = hex;
    syncSwatch(colorPicker.field, hex);
  }
}

function setPickerFromHex(hex) {
  const parsed = parseHex(hex);
  if (!parsed) return false;
  const rgb = hexToRgb(parsed);
  const hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
  if (hsv.s > 0.001) colorPicker.h = hsv.h;
  colorPicker.s = hsv.s;
  colorPicker.v = hsv.v;
  return true;
}

function openColorPicker(field) {
  colorPicker.field = field;
  setPickerFromHex(field.querySelector("input").value);
  const picker = $("#color-picker");
  const swatch = field.querySelector(".color-swatch");
  const r = swatch.getBoundingClientRect();
  picker.style.top = `${r.bottom + 6}px`;
  picker.style.left = `${r.left}px`;
  picker.classList.remove("hidden");
  renderColorPicker();
  const ph = picker.offsetHeight;
  const pw = picker.offsetWidth;
  picker.style.top = `${Math.min(r.bottom + 6, Math.max(8, window.innerHeight - ph - 8))}px`;
  picker.style.left = `${Math.min(Math.max(8, r.left), Math.max(8, window.innerWidth - pw - 8))}px`;
}

function closeColorPicker() {
  $("#color-picker").classList.add("hidden");
  colorPicker.field = null;
}

function bindDrag(el, handler) {
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    handler(e);
  });
  el.addEventListener("pointermove", (e) => {
    if (!el.hasPointerCapture(e.pointerId)) return;
    handler(e);
  });
}

function hueFromWheel(e) {
  const r = $("#cp-wheel").getBoundingClientRect();
  const dx = e.clientX - (r.left + r.width / 2);
  const dy = e.clientY - (r.top + r.height / 2);
  let deg = (Math.atan2(dx, -dy) * 180) / Math.PI;
  if (deg < 0) deg += 360;
  colorPicker.h = deg;
  renderColorPicker();
}

function svFromPad(e) {
  const r = $("#cp-sv").getBoundingClientRect();
  colorPicker.s = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
  colorPicker.v = Math.min(1, Math.max(0, 1 - (e.clientY - r.top) / r.height));
  renderColorPicker();
}

bindDrag($("#cp-wheel"), hueFromWheel);
bindDrag($("#cp-sv"), svFromPad);

$("#cp-hex").addEventListener("input", () => {
  if (setPickerFromHex($("#cp-hex").value)) renderColorPicker(true);
});

for (const id of ["cp-r", "cp-g", "cp-b"]) {
  document.getElementById(id).addEventListener("input", () => {
    const hex = rgbToHex($("#cp-r").value, $("#cp-g").value, $("#cp-b").value);
    setPickerFromHex(hex);
    renderColorPicker();
  });
}

document.querySelectorAll(".color-field").forEach((field) => {
  const input = field.querySelector("input");
  syncSwatch(field, input.value);
  input.addEventListener("input", () => {
    syncSwatch(field, input.value);
    if (colorPicker.field === field && setPickerFromHex(input.value)) {
      renderColorPicker();
    }
  });
  field.querySelector(".color-swatch").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (colorPicker.field === field && !$("#color-picker").classList.contains("hidden")) {
      closeColorPicker();
      return;
    }
    openColorPicker(field);
  });
});

document.addEventListener("pointerdown", (e) => {
  if ($("#color-picker").classList.contains("hidden")) return;
  if ($("#color-picker").contains(e.target) || e.target.closest(".color-swatch")) return;
  closeColorPicker();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeColorPicker();
});

const LED_GROUPS = [
  { ctrl: "id-ctrl", out: "id-out", led: "id-led" },
  { ctrl: "l-ctrl", out: "l-out", led: "l-leds" },
  { ctrl: "h-ctrl", out: "h-out", led: "h-leds" },
  { ctrl: "sig-ctrl", out: "sig-out", led: "sig-leds" },
  { ctrl: "sp-ctrl", out: "sp-out", led: "sp-leds" },
];

function controllerByName(name) {
  return (status.controllers || []).find((c) => c.name === name) || null;
}

function outputsOf(name) {
  const ctrl = controllerByName(name);
  return (ctrl && ctrl.outputs) || [];
}

function fillOptions(el, options, current) {
  if (!el) return;
  if (!options.length) {
    el.innerHTML = '<option value="">–</option>';
    return;
  }
  el.innerHTML = options
    .map((opt) => {
      const used = opt.used ? " opt-used" : "";
      const title = opt.title ? ` title="${esc(opt.title)}"` : "";
      return `<option value="${esc(opt.value)}" class="${used.trim()}"${title}>${esc(opt.label)}</option>`;
    })
    .join("");
  const values = options.map((opt) => String(opt.value));
  el.value = values.includes(String(current)) ? String(current) : values[0];
}

function ledOwners(ctrlName, globalIndex) {
  const leds = (status.usage && status.usage.leds && status.usage.leds[ctrlName]) || {};
  return leds[String(globalIndex)] || [];
}

function objectOwners(objId) {
  const objects = (status.usage && status.usage.objects) || {};
  return objects[objId] || [];
}

function currentLedExclude() {
  const ids = new Set();
  if (!editing.kind || !editing.id) return ids;
  if (editing.kind === "lampe" || editing.kind === "spezial" || editing.kind === "signal") {
    ids.add(editing.id);
    return ids;
  }
  if (editing.kind === "haus") {
    ids.add(editing.id);
    const house = (cfg.haeuser || {})[editing.id];
    if (house) {
      for (const windowId of Object.keys(house.fenster || {})) {
        ids.add(`${editing.id}.${windowId}`);
      }
    }
  }
  return ids;
}

function usedMark(owners, exclude) {
  const other = (owners || []).filter((id) => !exclude.has(id));
  if (!other.length) return { used: false, suffix: "", title: "" };
  return {
    used: true,
    suffix: "  · in Verwendung",
    title: `Bereits verwendet von: ${other.join(", ")}`,
  };
}

function fillOutputSelect(outId, ctrlName) {
  const el = document.getElementById(outId);
  const outs = outputsOf(ctrlName);
  fillOptions(
    el,
    outs.map((out) => ({ value: out.id, label: out.label })),
    el && el.value
  );
}

function fillLedSelect(ledId, ctrlName, outId) {
  const el = document.getElementById(ledId);
  if (!el) return;
  const outs = outputsOf(ctrlName);
  const out = outs.find((item) => String(item.id) === String(outId)) || outs[0];
  const selected = new Set([...el.selectedOptions].map((opt) => opt.value));
  if (!out || !out.len) {
    el.innerHTML = '<option value="">Keine LEDs</option>';
    return;
  }
  const exclude = currentLedExclude();
  el.innerHTML = Array.from({ length: out.len }, (_, i) => {
    const global = out.start + i;
    const mark = usedMark(ledOwners(ctrlName, global), exclude);
    const cls = mark.used ? ' class="opt-used"' : "";
    const title = mark.title ? ` title="${esc(mark.title)}"` : "";
    return `<option value="${i}"${cls}${title}>LED ${i + 1} (Nr. ${global})${mark.suffix}</option>`;
  }).join("");
  if (el.multiple) {
    [...el.options].forEach((opt) => {
      opt.selected = selected.has(opt.value);
    });
  } else if (selected.size && [...el.options].some((opt) => selected.has(opt.value))) {
    el.value = [...selected][0];
  }
}

function selectedLocals(ledId) {
  const el = document.getElementById(ledId);
  return [...el.selectedOptions].map((opt) => Number(opt.value)).filter((n) => Number.isFinite(n));
}

function toGlobals(ctrlName, outId, locals) {
  const out = outputsOf(ctrlName).find((item) => String(item.id) === String(outId));
  const start = out ? out.start : 0;
  return locals.map((i) => start + i);
}

function syncLedDropdowns() {
  for (const group of LED_GROUPS) {
    const ctrl = document.getElementById(group.ctrl);
    const out = document.getElementById(group.out);
    if (!ctrl) continue;
    fillOutputSelect(group.out, ctrl.value);
    fillLedSelect(group.led, ctrl.value, out && out.value);
  }
}

function fillCtrlSelects() {
  const names = (cfg.controller || []).map((c) => c.name).filter(Boolean);
  for (const id of ["id-ctrl", "l-ctrl", "h-ctrl", "sig-ctrl", "sp-ctrl"]) {
    const el = document.getElementById(id);
    if (!el) continue;
    const current = el.value;
    if (!names.length) {
      el.innerHTML = '<option value="">Kein Controller übernommen</option>';
      continue;
    }
    el.innerHTML = names.map((n) => `<option value="${n}">${n}</option>`).join("");
    el.value = names.includes(current) ? current : names[0];
  }
  syncLedDropdowns();
  fillSpecialFx($("#sp-ctrl") && $("#sp-ctrl").value);
}

function fillNamedSelect(el, names, current, emptyLabel) {
  if (!el) return;
  if (!names.length) {
    el.innerHTML = `<option value="">${esc(emptyLabel)}</option>`;
    return;
  }
  fillOptions(
    el,
    names.map((name, i) => ({ value: i, label: `${i}: ${name}` })),
    current
  );
}

function fillSpecialFx(ctrlName) {
  const ctrl = controllerByName(ctrlName);
  const reachable = ctrl && ctrl.reachable;
  fillNamedSelect(
    $("#sp-fx"),
    (ctrl && ctrl.effects) || [],
    $("#sp-fx") && $("#sp-fx").value,
    reachable ? "Keine Effekte gemeldet" : "Effekte nicht geladen"
  );
  fillNamedSelect(
    $("#sp-pal"),
    (ctrl && ctrl.palettes) || [],
    $("#sp-pal") && $("#sp-pal").value,
    reachable ? "Keine Paletten gemeldet" : "Paletten nicht geladen"
  );
}

function groupMemberSections(excludeId) {
  const sections = [];
  const add = (label, ids) => {
    const items = ids.filter((id) => id && id !== excludeId);
    if (items.length) sections.push({ label, items });
  };
  add("Lampen", Object.keys(cfg.lampen || {}));
  add("Häuser", Object.keys(cfg.haeuser || {}));
  const windows = [];
  for (const [houseId, house] of Object.entries(cfg.haeuser || {})) {
    for (const windowId of Object.keys(house.fenster || {})) {
      windows.push(`${houseId}.${windowId}`);
    }
  }
  add("Fenster", windows);
  add("Signale", Object.keys(cfg.signale || {}));
  add("Spezial", Object.keys(cfg.spezial || {}));
  add("Gruppen", Object.keys(cfg.gruppen || {}));
  add("Sequenzen", Object.keys(cfg.sequenzen || {}));
  return sections;
}

function fillGroupMemberSelect(selected) {
  const el = $("#g-mem");
  if (!el) return;
  const keep = selected
    ? new Set(selected.map(String))
    : new Set([...el.selectedOptions].map((opt) => opt.value));
  const exclude = editing.kind === "gruppe" && editing.id ? editing.id : null;
  const sections = groupMemberSections(exclude);
  if (!sections.length) {
    el.innerHTML = '<option value="">Keine Objekte angelegt</option>';
    el.disabled = true;
    return;
  }
  el.disabled = false;
  const usedExclude = new Set(exclude ? [exclude] : []);
  el.innerHTML = sections
    .map(
      (section) =>
        `<optgroup label="${esc(section.label)}">${section.items
          .map((id) => {
            const mark = usedMark(objectOwners(id), usedExclude);
            const cls = mark.used ? ' class="opt-used"' : "";
            const title = mark.title ? ` title="${esc(mark.title)}"` : "";
            return `<option value="${esc(id)}"${cls}${title}>${esc(id)}${mark.suffix}</option>`;
          })
          .join("")}</optgroup>`
    )
    .join("");
  [...el.options].forEach((opt) => {
    opt.selected = keep.has(opt.value);
  });
}

function fillMultiSelect(el, items, selected, emptyLabel, excludeIds) {
  if (!el) return;
  const keep = selected
    ? new Set(selected.map(String))
    : new Set([...el.selectedOptions].map((opt) => opt.value));
  if (!items.length) {
    el.innerHTML = `<option value="">${esc(emptyLabel)}</option>`;
    el.disabled = true;
    return;
  }
  el.disabled = false;
  const usedExclude = new Set(excludeIds || []);
  el.innerHTML = items
    .map((id) => {
      const mark = usedMark(objectOwners(id), usedExclude);
      const cls = mark.used ? ' class="opt-used"' : "";
      const title = mark.title ? ` title="${esc(mark.title)}"` : "";
      return `<option value="${esc(id)}"${cls}${title}>${esc(id)}${mark.suffix}</option>`;
    })
    .join("");
  [...el.options].forEach((opt) => {
    opt.selected = keep.has(opt.value);
  });
}

function fillSequenceGroupSelect(selected) {
  const exclude = editing.kind === "sequenz" && editing.id ? [editing.id] : [];
  fillMultiSelect($("#s-grp"), Object.keys(cfg.gruppen || {}), selected, "Keine Gruppen angelegt", exclude);
}

function selectedMembers(selectId) {
  const el = document.getElementById(selectId);
  return [...el.selectedOptions].map((opt) => opt.value).filter(Boolean);
}

for (const group of LED_GROUPS) {
  const ctrl = document.getElementById(group.ctrl);
  const out = document.getElementById(group.out);
  if (ctrl) {
    ctrl.addEventListener("change", () => {
      fillOutputSelect(group.out, ctrl.value);
      const next = document.getElementById(group.out);
      fillLedSelect(group.led, ctrl.value, next && next.value);
      if (group.ctrl === "sp-ctrl") fillSpecialFx(ctrl.value);
    });
  }
  if (out) {
    out.addEventListener("change", () => {
      fillLedSelect(group.led, document.getElementById(group.ctrl).value, out.value);
    });
  }
}

function pairingStatus(b) {
  if (b.logged_on) return "verbunden";
  if (b.pairing_open) return "Modus aktiv – warte auf Verbindung";
  if (b.pending) return "Anfrage offen";
  if ((b.sessions || 0) > 0) return "Host verbunden, nicht angemeldet";
  return "–";
}

function renderStatus() {
  const b = status.bidib || {};
  $("#bidib-dl").innerHTML = `
    <dt>Knoten</dt><dd>${b.knotenname || ""}</dd>
    <dt>UID</dt><dd><code>${b.unique_id || ""}</code></dd>
    <dt>Port / Modus</dt><dd>${b.port} / ${b.modus} ${b.aktiv ? "" : "(aus)"}</dd>
    <dt>Angemeldet</dt><dd class="${b.logged_on ? "ok" : "bad"}">${b.logged_on ? "ja" : "nein"} (${b.sessions || 0} Links)</dd>
    <dt>Pairing</dt><dd>${pairingStatus(b)}</dd>
    <dt>Vertraut</dt><dd>${(b.trusted || []).join(", ") || "–"}</dd>
  `;
  const banner = $("#pairing-banner");
  if (b.pending) {
    banner.classList.remove("hidden");
    banner.innerHTML = `Pairing nötig: <strong>${b.pending.user || b.pending.prod || b.pending.uid}</strong> ist verbunden, aber noch nicht vertraut. „Pairing-Modus“ drücken, um den Host zu akzeptieren.`;
  } else if (!b.logged_on && (b.sessions || 0) > 0) {
    banner.classList.remove("hidden");
    banner.innerHTML = `Ein Host ist verbunden, aber noch nicht angemeldet. „Pairing-Modus“ sendet den Handshake erneut.`;
  } else {
    banner.classList.add("hidden");
  }
  $("#controllers").innerHTML = (status.controllers || [])
    .map((c) => {
      const href = c.url || (c.ip ? `http://${c.ip}:${c.port || 80}/` : "");
      const ip = c.ip
        ? `<a href="${href}" target="_blank" rel="noopener">${c.ip}</a>`
        : "keine IP";
      const outs = (c.outputs || []).map((o) => o.label).join(" · ");
      const warns = (c.warnings || [])
        .map((w) => `<li>${esc(w)}</li>`)
        .join("");
      return `<div><strong>${c.name}</strong> ${ip} · ${c.leds || "?"} LEDs ·
      <span class="${c.reachable ? "ok" : "bad"}">${c.reachable ? "erreichbar" : "nicht erreichbar"}</span>
      ${c.mac ? `<span class="chip">${c.mac}</span>` : ""}
      ${outs ? `<div class="sub">${outs}</div>` : ""}
      ${warns ? `<ul class="warn">${warns}</ul>` : ""}</div>`;
    })
    .join("") || "<p>Noch kein Controller übernommen.</p>";
  renderObjects();
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function objectTestControl(o) {
  if (o.states && o.states.length) {
    const opts = o.states
      .map((s) => `<option value="${esc(s.value)}" ${Number(s.value) === Number(o.state) ? "selected" : ""}>${esc(s.name)}</option>`)
      .join("");
    return `<select data-state="${esc(o.id)}" ${o.in_progress ? "disabled" : ""}>${opts}</select>`;
  }
  return `<label class="switch" title="Ein/Aus testen">
    <input type="checkbox" data-switch="${esc(o.id)}" ${o.on ? "checked" : ""} ${o.in_progress ? "disabled" : ""}>
    <span></span>
  </label>`;
}

function objectInfoCell(o) {
  const rows = o.info || [];
  const body = rows.length
    ? rows.map((row) => `<div><strong>${esc(row.program)}:</strong> ${esc(row.text)}</div>`).join("")
    : "Keine Hinweise.";
  return `<span class="obj-help-wrap">
    <button type="button" class="obj-help" aria-label="Info">?</button>
    <div class="obj-help-box" role="tooltip">${body}</div>
  </span>`;
}

let objectSort = { key: "id", dir: 1 };

function sortMark(key) {
  if (objectSort.key !== key) return "";
  return objectSort.dir > 0 ? " ▲" : " ▼";
}

function sortHeader(key, label) {
  const active = objectSort.key === key ? " sort-active" : "";
  return `<th class="sortable${active}" data-sort="${key}" title="Nach ${esc(label)} sortieren">${esc(label)}${sortMark(key)}</th>`;
}

function sortedObjects(list) {
  const dir = objectSort.dir;
  const key = objectSort.key;
  return list.slice().sort((a, b) => {
    let cmp = 0;
    if (key === "address") {
      const aa = a.address == null ? Number.POSITIVE_INFINITY : Number(a.address);
      const bb = b.address == null ? Number.POSITIVE_INFINITY : Number(b.address);
      cmp = aa - bb;
    } else if (key === "kind") {
      cmp = String(a.kind_label || a.kind || "").localeCompare(String(b.kind_label || b.kind || ""), "de");
      if (!cmp) cmp = String(a.id || "").localeCompare(String(b.id || ""), "de");
    } else {
      cmp = String(a.id || "").localeCompare(String(b.id || ""), "de");
    }
    return cmp * dir;
  });
}

function renderObjects() {
  const list = status.objects || [];
  if (!list.length) {
    $("#objects").innerHTML = "<p>Noch keine Objekte angelegt.</p>";
    return;
  }
  $("#objects").innerHTML = `
    <table><thead><tr>${sortHeader("id", "Objekt")}${sortHeader("kind", "Typ")}${sortHeader("address", "Adresse")}<th>Info</th><th>Test</th><th></th></tr></thead><tbody>
    ${sortedObjects(list).map((o) => `
      <tr>
        <td>
          <button type="button" class="obj-link" data-edit="${esc(o.id)}">${esc(o.id)}</button>
          ${o.in_progress ? " …" : ""}
          ${o.error ? ` <span class="bad">${esc(o.error)}</span>` : ""}
        </td>
        <td>${esc(o.kind_label || o.kind || "")}</td>
        <td>
          <input type="number" min="0" max="255" step="1" data-address="${esc(o.id)}"
            value="${o.address != null ? esc(o.address) : ""}"
            placeholder="—"
            title="BiDiB-Accessory-Adresse. Fenster ohne eigene Adresse über das Haus schalten.">
        </td>
        <td class="obj-info">${objectInfoCell(o)}</td>
        <td>${objectTestControl(o)}</td>
        <td>
          <div class="obj-actions">
            <button type="button" class="secondary" data-edit="${esc(o.id)}">Ändern</button>
            <button type="button" class="secondary danger" data-del="${esc(o.id)}">Löschen</button>
          </div>
        </td>
      </tr>`).join("")}
    </tbody></table>`;
}

async function refresh(force = false) {
  if (!force && isEditing()) return;
  status = await api("/api/status");
  cfg = await api("/api/config");
  renderStatus();
  fillCtrlSelects();
  fillGroupMemberSelect();
  fillSequenceGroupSelect();
  if (status.wizard && !wizardOpened) {
    wizardOpened = true;
    showTab("wizard");
  }
  if (!$("#tab-wizard").classList.contains("hidden")) {
    await syncDiscovery();
  }
}

function deviceKey(d) {
  return `${d.ip}:${d.port || 80}`;
}

function suggestedName(d) {
  const raw = (d.mdns || d.name || "").replace(/^wled-?/i, "").replace(/\.local$/i, "").trim();
  if (!raw || /^[0-9a-f]{12}$/i.test(raw) || /^([0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(raw)) {
    return "dorf";
  }
  return raw;
}

function ensureDeviceRow(box, d) {
  const key = deviceKey(d);
  let row = box.querySelector(`[data-device="${key}"]`);
  if (!row) {
    row = document.createElement("div");
    row.className = "row wrap";
    row.dataset.device = key;
    row.style.margin = ".4rem 0";
    row.innerHTML = `
      <span class="dev-label"></span>
      <input class="claim-name" placeholder="Name z. B. dorf">
      <button type="button">Übernehmen</button>`;
    row.querySelector("button").addEventListener("click", () => claim(row.querySelector("button")));
    const empty = box.querySelector("p");
    if (empty) empty.remove();
    box.appendChild(row);
    row.querySelector(".claim-name").value = suggestedName(d);
  }
  const input = row.querySelector(".claim-name");
  input.dataset.mac = d.mac || "";
  input.dataset.ip = d.ip || "";
  input.dataset.port = String(d.port || 80);
  input.dataset.leds = String(d.led_count || 0);
  input.dataset.mdns = d.mdns || "";
  row.querySelector(".dev-label").textContent =
    `${d.name} ${d.ip} · ${d.led_count} LEDs · ${d.mac || "keine MAC"}`;
  return key;
}

async function syncDiscovery() {
  const box = $("#unbound");
  const data = await api("/api/discovery");
  const devices = data.unbound || [];
  if (!devices.length) {
    if (!box.querySelector(".claim-name")) {
      box.innerHTML = "<p>Keine unbekannten WLED-Geräte. mDNS prüfen oder IP von Hand eintragen.</p>";
    }
    return;
  }
  const seen = new Set(devices.map((d) => ensureDeviceRow(box, d)));
  box.querySelectorAll("[data-device]").forEach((row) => {
    if (!seen.has(row.dataset.device) && !row.contains(document.activeElement)) {
      row.remove();
    }
  });
}

window.claim = (btn) => runAction("Controller übernommen", async () => {
  const input = btn.parentElement.querySelector(".claim-name");
  const name = input.value.trim();
  if (!name) throw new Error("Bitte einen logischen Namen vergeben.");
  await api("/api/controllers/claim", {
    method: "POST",
    body: JSON.stringify({
      name,
      mac: input.dataset.mac || null,
      ip: input.dataset.ip,
      port: Number(input.dataset.port || 80),
      leds: Number(input.dataset.leds || 0) || null,
      mdns: input.dataset.mdns || null,
    }),
  });
  await refresh();
  await syncDiscovery();
});

window.doSwitch = async (id, aspect) => {
  try {
    await api("/api/switch", { method: "POST", body: JSON.stringify({ object_id: id, aspect }) });
    await refresh();
  } catch (e) {
    notify(e.message || "Schalten fehlgeschlagen", false);
    await refresh();
  }
};

$("#btn-pair").onclick = () => runAction("Pairing-Modus aktiv", async () => {
  await api("/api/pairing/accept", { method: "POST" });
  await refresh();
  const b = status.bidib || {};
  if (b.logged_on) {
    notify("Pairing akzeptiert – Host ist angemeldet", true);
    return false;
  }
  if (b.pending) {
    notify("Host angenommen – warte auf Anmeldung", true);
    return false;
  }
  notify("Pairing-Modus aktiv – warte auf Verbindung", true);
  return false;
});
$("#btn-reject").onclick = () => runAction("Anfrage abgelehnt", async () => {
  await api("/api/pairing/reject", { method: "POST" });
  await refresh();
});

$("#w-save-adapter").onclick = () => runAction("Adapter gespeichert", async () => {
  const next = await api("/api/config");
  next.adapter = next.adapter || {};
  next.adapter.netbidib = next.adapter.netbidib || {};
  next.adapter.netbidib.aktiv = true;
  next.adapter.netbidib.knotenname = $("#w-name").value;
  next.adapter.netbidib.port = Number($("#w-port").value);
  next.adapter.netbidib.modus = $("#w-mode").value;
  await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
  await refresh();
});

$("#m-add").onclick = () => runAction("Controller hinzugefügt", async () => {
  const name = $("#m-name").value.trim();
  const ip = $("#m-ip").value.trim();
  if (!name) throw new Error("Bitte einen Namen vergeben.");
  if (!ip) throw new Error("Bitte eine IP-Adresse eintragen.");
  await api("/api/controllers/manual", {
    method: "POST",
    body: JSON.stringify({
      name,
      ip,
      leds: Number($("#m-leds").value) || null,
    }),
  });
  await refresh();
});

$("#id-go").onclick = () => runAction("LED blinkt", async () => {
  await api("/api/identify", {
    method: "POST",
    body: JSON.stringify({
      controller: $("#id-ctrl").value,
      output: Number($("#id-out").value),
      index: Number($("#id-led").value),
    }),
  });
});

function parseLeds(text) {
  return text.split(/[,\s]+/).filter(Boolean).map((x) => Number(x));
}

function setColorInput(id, hex) {
  const input = document.getElementById(id);
  if (!input) return;
  input.value = parseHex(hex) || hex || "";
  const field = input.closest(".color-field");
  if (field) syncSwatch(field, input.value);
}

function selectLocals(ledId, locals) {
  const el = document.getElementById(ledId);
  if (!el) return;
  const want = new Set((locals || []).map(String));
  [...el.options].forEach((opt) => {
    opt.selected = want.has(opt.value);
  });
}

function locateLeds(ctrlName, globals) {
  const outs = outputsOf(ctrlName);
  const values = (globals || []).map(Number).filter((n) => Number.isFinite(n));
  for (const out of outs) {
    const locals = values.map((g) => g - out.start);
    if (locals.length && locals.every((i) => i >= 0 && i < out.len)) {
      return { outId: String(out.id), locals };
    }
  }
  const first = values[0];
  const out = outs.find((item) => first >= item.start && first < item.start + item.len) || outs[0];
  if (!out) return { outId: "", locals: [] };
  return {
    outId: String(out.id),
    locals: values.map((g) => g - out.start).filter((i) => i >= 0 && i < out.len),
  };
}

const EDIT_META = {
  lampe: { title: "l-title", create: "Lampe anlegen", edit: "Lampe bearbeiten", art: "art-lampe", cancel: "l-cancel" },
  haus: { title: "h-title", create: "Haus anlegen", edit: "Haus bearbeiten", art: "art-haus", cancel: "h-cancel" },
  gruppe: { title: "g-title", create: "Gruppe anlegen", edit: "Gruppe bearbeiten", art: "art-gruppe", cancel: "g-cancel" },
  sequenz: { title: "s-title", create: "Sequenz anlegen", edit: "Sequenz bearbeiten", art: "art-sequenz", cancel: "s-cancel" },
  signal: { title: "sig-title", create: "Signal anlegen", edit: "Signal bearbeiten", art: "art-signal", cancel: "sig-cancel" },
  spezial: { title: "sp-title", create: "Spezial anlegen", edit: "Spezial bearbeiten", art: "art-spezial", cancel: "sp-cancel" },
};

function setEditing(kind, id) {
  editing.kind = kind || null;
  editing.id = id || null;
  for (const [k, meta] of Object.entries(EDIT_META)) {
    const active = Boolean(kind === k && id);
    const title = document.getElementById(meta.title);
    if (title) title.textContent = active ? meta.edit : meta.create;
    const art = document.getElementById(meta.art);
    if (art) art.classList.toggle("editing", active);
    const cancel = document.getElementById(meta.cancel);
    if (cancel) cancel.classList.toggle("hidden", !active);
  }
}

function rewriteRef(value, oldId, newId) {
  if (value === oldId) return newId;
  if (typeof value === "string" && value.startsWith(`${oldId}.`)) return newId + value.slice(oldId.length);
  return value;
}

function retargetRefs(cfg, oldId, newId) {
  if (!oldId || oldId === newId) return;
  for (const g of Object.values(cfg.gruppen || {})) {
    g.mitglieder = (g.mitglieder || []).map((m) => rewriteRef(m, oldId, newId));
  }
  for (const seq of Object.values(cfg.sequenzen || {})) {
    seq.gruppen = (seq.gruppen || []).map((m) => rewriteRef(m, oldId, newId));
  }
  const acc = cfg.adapter && cfg.adapter.netbidib && cfg.adapter.netbidib.accessories;
  if (acc) {
    for (const [key, value] of Object.entries(acc)) acc[key] = rewriteRef(value, oldId, newId);
  }
}

function dropRefs(cfg, removed) {
  const gone = new Set(removed);
  for (const [gid, g] of Object.entries(cfg.gruppen || {})) {
    g.mitglieder = (g.mitglieder || []).filter((m) => !gone.has(m));
    if (!g.mitglieder.length) {
      delete cfg.gruppen[gid];
      gone.add(gid);
    }
  }
  for (const [sid, seq] of Object.entries(cfg.sequenzen || {})) {
    seq.gruppen = (seq.gruppen || []).filter((g) => !gone.has(g) && (cfg.gruppen || {})[g]);
    if (!seq.gruppen.length) {
      delete cfg.sequenzen[sid];
      gone.add(sid);
    }
  }
  const acc = cfg.adapter && cfg.adapter.netbidib && cfg.adapter.netbidib.accessories;
  if (acc) {
    for (const [key, value] of Object.entries(acc)) {
      if (gone.has(value)) delete acc[key];
    }
  }
}

function removeObjectFromConfig(cfg, id) {
  const removed = [];
  if (cfg.lampen && cfg.lampen[id]) {
    delete cfg.lampen[id];
    removed.push(id);
  } else if (cfg.haeuser && cfg.haeuser[id]) {
    removed.push(id, ...Object.keys(cfg.haeuser[id].fenster || {}).map((w) => `${id}.${w}`));
    delete cfg.haeuser[id];
  } else if (cfg.gruppen && cfg.gruppen[id]) {
    delete cfg.gruppen[id];
    removed.push(id);
  } else if (cfg.sequenzen && cfg.sequenzen[id]) {
    delete cfg.sequenzen[id];
    removed.push(id);
  } else if (cfg.signale && cfg.signale[id]) {
    delete cfg.signale[id];
    removed.push(id);
  } else if (cfg.spezial && cfg.spezial[id]) {
    delete cfg.spezial[id];
    removed.push(id);
  } else if (id.includes(".")) {
    const houseId = id.split(".")[0];
    const win = id.slice(houseId.length + 1);
    const house = cfg.haeuser && cfg.haeuser[houseId];
    if (house && house.fenster && house.fenster[win]) {
      delete house.fenster[win];
      removed.push(id);
    }
  }
  if (!removed.length) return false;
  dropRefs(cfg, removed);
  return true;
}

function replaceKey(map, oldId, newId, value) {
  if (oldId && oldId !== newId && map[oldId]) delete map[oldId];
  map[newId] = value;
}

function fensterToText(fenster) {
  return Object.entries(fenster || {})
    .map(([name, win]) => `${name}:${(win.leds || []).join(",")}:${win.farbe || DEFAULT_COLOR}`)
    .join("\n");
}

function parseFensterLines(text) {
  const lines = [];
  for (const raw of String(text || "").split("\n")) {
    const t = raw.trim();
    if (!t) continue;
    const [name, leds, farbe] = t.split(":");
    if (!name) continue;
    lines.push({ name, leds: leds || "", farbe: (farbe || DEFAULT_COLOR).trim() });
  }
  return lines;
}

function fensterLinesToText(lines) {
  return lines.map((win) => `${win.name}:${win.leds}:${win.farbe}`).join("\n");
}

function begriffeToText(begriffe) {
  return Object.entries(begriffe || {})
    .map(([asp, b]) => {
      const leds = Object.entries(b.leds || {}).map(([idx, col]) => `${idx}=${col}`).join(",");
      return `${asp}:${b.name || asp}:${leds}`;
    })
    .join("\n");
}

function loadLamp(id, lamp) {
  $("#l-id").value = id;
  $("#l-ctrl").value = lamp.controller;
  setEditing("lampe", id);
  fillOutputSelect("l-out", lamp.controller);
  const located = locateLeds(lamp.controller, lamp.leds || []);
  $("#l-out").value = located.outId;
  fillLedSelect("l-leds", lamp.controller, located.outId);
  selectLocals("l-leds", located.locals);
  setColorInput("l-farbe", lamp.farbe || DEFAULT_COLOR);
  $("#art-lampe").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadHouse(id, house, windowId) {
  $("#h-id").value = id;
  $("#h-ctrl").value = house.controller;
  setEditing("haus", id);
  fillOutputSelect("h-out", house.controller);
  $("#h-mode").value = house.einschalten || "zufaellig";
  $("#h-fenster").value = fensterToText(house.fenster);
  $("#h-win-name").value = windowId || "";
  editingWindow = windowId || null;
  const win = windowId && house.fenster ? house.fenster[windowId] : null;
  if (win) {
    const located = locateLeds(house.controller, win.leds || []);
    $("#h-out").value = located.outId;
    fillLedSelect("h-leds", house.controller, located.outId);
    selectLocals("h-leds", located.locals);
    setColorInput("h-win-farbe", win.farbe || DEFAULT_COLOR);
  } else {
    fillLedSelect("h-leds", house.controller, $("#h-out").value);
    setColorInput("h-win-farbe", DEFAULT_COLOR);
  }
  $("#art-haus").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadGroup(id, group) {
  $("#g-id").value = id;
  setEditing("gruppe", id);
  fillGroupMemberSelect(group.mitglieder || []);
  $("#art-gruppe").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadSequence(id, seq) {
  $("#s-id").value = id;
  $("#s-ord").value = typeof seq.reihenfolge === "string" ? seq.reihenfolge : "definiert";
  const delay = seq.verzoegerung;
  if (Array.isArray(delay) && delay.length >= 2) {
    $("#s-d1").value = durationSeconds(delay[0], 2);
    $("#s-d2").value = durationSeconds(delay[1], 8);
  }
  setEditing("sequenz", id);
  fillSequenceGroupSelect(seq.gruppen || []);
  $("#art-sequenz").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadSignal(id, signal) {
  $("#sig-id").value = id;
  $("#sig-ctrl").value = signal.controller;
  setEditing("signal", id);
  fillOutputSelect("sig-out", signal.controller);
  fillLedSelect("sig-leds", signal.controller, $("#sig-out").value);
  $("#sig-asp").value = begriffeToText(signal.begriffe);
  $("#art-signal").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadSpecial(id, spec) {
  $("#sp-id").value = id;
  $("#sp-ctrl").value = spec.controller;
  setEditing("spezial", id);
  fillOutputSelect("sp-out", spec.controller);
  fillSpecialFx(spec.controller);
  const located = locateLeds(spec.controller, spec.leds || []);
  $("#sp-out").value = located.outId;
  fillLedSelect("sp-leds", spec.controller, located.outId);
  selectLocals("sp-leds", located.locals);
  $("#sp-fx").value = String(spec.effekt ?? 0);
  $("#sp-pal").value = String(spec.palette ?? 0);
  $("#sp-sx").value = String(spec.geschwindigkeit ?? 128);
  $("#sp-ix").value = String(spec.intensitaet ?? 128);
  setColorInput("sp-farbe", spec.farbe || DEFAULT_COLOR);
  $("#art-spezial").scrollIntoView({ behavior: "smooth", block: "start" });
}

function startEdit(id) {
  const obj = (status.objects || []).find((item) => item.id === id);
  let kind = obj && obj.kind;
  let windowId = "";
  if (kind === "fenster") {
    const houseId = id.split(".")[0];
    windowId = id.slice(houseId.length + 1);
    id = houseId;
    kind = "haus";
  }
  showTab("objects");
  if (kind === "lampe" && cfg.lampen && cfg.lampen[id]) return loadLamp(id, cfg.lampen[id]);
  if (kind === "haus" && cfg.haeuser && cfg.haeuser[id]) return loadHouse(id, cfg.haeuser[id], windowId);
  if (kind === "gruppe" && cfg.gruppen && cfg.gruppen[id]) return loadGroup(id, cfg.gruppen[id]);
  if (kind === "sequenz" && cfg.sequenzen && cfg.sequenzen[id]) return loadSequence(id, cfg.sequenzen[id]);
  if (kind === "signal" && cfg.signale && cfg.signale[id]) return loadSignal(id, cfg.signale[id]);
  if (kind === "spezial" && cfg.spezial && cfg.spezial[id]) return loadSpecial(id, cfg.spezial[id]);
  notify("Objekt konnte nicht geladen werden.", false);
}

function cancelEdit(kind) {
  if (kind === "lampe") {
    $("#l-id").value = "";
    setColorInput("l-farbe", DEFAULT_COLOR);
  } else if (kind === "haus") {
    $("#h-id").value = "";
    $("#h-win-name").value = "";
    $("#h-fenster").value = "";
    setColorInput("h-win-farbe", DEFAULT_COLOR);
    editingWindow = null;
  } else if (kind === "gruppe") {
    $("#g-id").value = "";
    fillGroupMemberSelect([]);
  } else if (kind === "sequenz") {
    $("#s-id").value = "";
    fillSequenceGroupSelect([]);
    $("#s-d1").value = "2";
    $("#s-d2").value = "8";
  } else if (kind === "signal") {
    $("#sig-id").value = "";
    $("#sig-asp").value = "";
    $("#sig-asp-name").value = "";
    setColorInput("sig-farbe", "FF0000");
    const aspN = $("#sig-asp-n");
    if (aspN) aspN.value = "0";
  } else if (kind === "spezial") {
    $("#sp-id").value = "";
    $("#sp-sx").value = "128";
    $("#sp-ix").value = "128";
    setColorInput("sp-farbe", DEFAULT_COLOR);
    if ($("#sp-fx")) $("#sp-fx").selectedIndex = 0;
    if ($("#sp-pal")) $("#sp-pal").selectedIndex = 0;
  }
  setEditing(null, null);
}

async function afterSave(kind) {
  cancelEdit(kind);
  await refresh(true);
}

async function deleteListedObject(id) {
  if (!window.confirm(`„${id}“ wirklich löschen?`)) return;
  await runAction("Objekt gelöscht", async () => {
    const next = await api("/api/config");
    if (!removeObjectFromConfig(next, id)) throw new Error("Objekt nicht gefunden.");
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    const editingId = editing.id;
    const editingKind = editing.kind;
    await refresh();
    if (editingId === id) {
      cancelEdit(editingKind);
    } else if (editingKind === "haus" && editingId && id.startsWith(`${editingId}.`) && cfg.haeuser && cfg.haeuser[editingId]) {
      loadHouse(editingId, cfg.haeuser[editingId]);
    }
  });
}

$("#objects").addEventListener("click", (e) => {
  const sort = e.target.closest("[data-sort]");
  if (sort) {
    e.preventDefault();
    const key = sort.dataset.sort;
    if (objectSort.key === key) objectSort.dir *= -1;
    else objectSort = { key, dir: 1 };
    renderObjects();
    return;
  }
  const del = e.target.closest("[data-del]");
  if (del) {
    e.preventDefault();
    deleteListedObject(del.dataset.del);
    return;
  }
  const edit = e.target.closest("[data-edit]");
  if (edit) {
    e.preventDefault();
    startEdit(edit.dataset.edit);
  }
});

$("#objects").addEventListener("change", (e) => {
  const addr = e.target.closest("[data-address]");
  if (addr) {
    const value = Number(addr.value);
    const previous = (status.objects || []).find((item) => item.id === addr.dataset.address);
    if (!Number.isInteger(value) || value < 0) {
      addr.value = previous && previous.address != null ? previous.address : "";
      notify("Adresse muss eine Zahl ab 0 sein.", false);
      return;
    }
    runAction("Adresse gespeichert", async () => {
      try {
        const data = await api("/api/address", {
          method: "POST",
          body: JSON.stringify({ object_id: addr.dataset.address, address: value }),
        });
        status = data;
        cfg = await api("/api/config");
        renderStatus();
      } catch (err) {
        addr.value = previous && previous.address != null ? previous.address : "";
        throw err;
      }
    });
    return;
  }
  const sw = e.target.closest("[data-switch]");
  if (sw) {
    doSwitch(sw.dataset.switch, sw.checked ? 1 : 0);
    return;
  }
  const sel = e.target.closest("[data-state]");
  if (sel) doSwitch(sel.dataset.state, Number(sel.value));
});

$("#l-cancel").onclick = () => cancelEdit("lampe");
$("#h-cancel").onclick = () => cancelEdit("haus");
$("#g-cancel").onclick = () => cancelEdit("gruppe");
$("#s-cancel").onclick = () => cancelEdit("sequenz");
$("#sig-cancel").onclick = () => cancelEdit("signal");
$("#sp-cancel").onclick = () => cancelEdit("spezial");

$("#l-add").onclick = () => {
  const updating = editing.kind === "lampe" && editing.id;
  runAction(updating ? "Lampe gespeichert" : "Lampe angelegt", async () => {
    const id = $("#l-id").value.trim();
    const leds = toGlobals($("#l-ctrl").value, $("#l-out").value, selectedLocals("l-leds"));
    if (!id) throw new Error("Bitte eine ID vergeben.");
    if (!leds.length) throw new Error("Bitte mindestens eine LED wählen.");
    const next = await api("/api/config");
    next.lampen = next.lampen || {};
    replaceKey(next.lampen, updating ? editing.id : null, id, {
      controller: $("#l-ctrl").value,
      leds,
      farbe: parseHex($("#l-farbe").value) || DEFAULT_COLOR,
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("lampe");
  });
};

$("#h-win-add").onclick = () => {
  const name = $("#h-win-name").value.trim();
  const leds = toGlobals($("#h-ctrl").value, $("#h-out").value, selectedLocals("h-leds"));
  const farbe = parseHex($("#h-win-farbe").value) || DEFAULT_COLOR;
  if (!name) {
    notify("Bitte einen Fensternamen vergeben.", false);
    return;
  }
  if (!leds.length) {
    notify("Bitte mindestens eine LED wählen.", false);
    return;
  }
  const lines = parseFensterLines($("#h-fenster").value);
  let idx = lines.findIndex((win) => win.name === name);
  if (idx < 0 && editingWindow) idx = lines.findIndex((win) => win.name === editingWindow);
  const existed = idx >= 0;
  runAction(existed ? "Fenster aktualisiert" : "Fenster übernommen", () => {
    const entry = { name, leds: leds.join(","), farbe };
    if (idx >= 0) lines[idx] = entry;
    else lines.push(entry);
    $("#h-fenster").value = fensterLinesToText(lines);
    editingWindow = null;
  });
};

$("#h-add").onclick = () => {
  const updating = editing.kind === "haus" && editing.id;
  runAction(updating ? "Haus gespeichert" : "Haus angelegt", async () => {
    const id = $("#h-id").value.trim();
    if (!id) throw new Error("Bitte eine ID vergeben.");
    const next = await api("/api/config");
    const fenster = {};
    for (const line of $("#h-fenster").value.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      const [name, leds, farbe] = t.split(":");
      fenster[name] = { leds: parseLeds(leds || ""), farbe: (farbe || DEFAULT_COLOR).trim() };
    }
    if (!Object.keys(fenster).length) throw new Error("Bitte mindestens ein Fenster übernehmen.");
    next.haeuser = next.haeuser || {};
    replaceKey(next.haeuser, updating ? editing.id : null, id, {
      controller: $("#h-ctrl").value,
      einschalten: $("#h-mode").value,
      fenster,
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("haus");
  });
};

$("#g-add").onclick = () => {
  const updating = editing.kind === "gruppe" && editing.id;
  runAction(updating ? "Gruppe gespeichert" : "Gruppe angelegt", async () => {
    const id = $("#g-id").value.trim();
    if (!id) throw new Error("Bitte eine ID vergeben.");
    const mitglieder = selectedMembers("g-mem");
    if (!mitglieder.length) throw new Error("Bitte mindestens ein Objekt wählen.");
    const next = await api("/api/config");
    next.gruppen = next.gruppen || {};
    replaceKey(next.gruppen, updating ? editing.id : null, id, { mitglieder });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("gruppe");
  });
};

$("#s-add").onclick = () => {
  const updating = editing.kind === "sequenz" && editing.id;
  runAction(updating ? "Sequenz gespeichert" : "Sequenz angelegt", async () => {
    const id = $("#s-id").value.trim();
    if (!id) throw new Error("Bitte eine ID vergeben.");
    const gruppen = selectedMembers("s-grp");
    if (!gruppen.length) throw new Error("Bitte mindestens eine Gruppe wählen.");
    const minS = durationSeconds($("#s-d1").value, NaN);
    const maxS = durationSeconds($("#s-d2").value, NaN);
    if (!Number.isFinite(minS) || !Number.isFinite(maxS) || minS < 0 || maxS < 0) {
      throw new Error("Pausen müssen Zahlen ab 0 Sekunden sein.");
    }
    const next = await api("/api/config");
    next.sequenzen = next.sequenzen || {};
    replaceKey(next.sequenzen, updating ? editing.id : null, id, {
      gruppen,
      reihenfolge: $("#s-ord").value,
      verzoegerung: [durationToken(minS), durationToken(maxS)],
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("sequenz");
  });
};

$("#sig-asp-add").onclick = () => runAction("Begriff übernommen", () => {
  const asp = $("#sig-asp-n").value;
  const name = $("#sig-asp-name").value.trim() || String(asp);
  const farbe = parseHex($("#sig-farbe").value) || "FF0000";
  const leds = toGlobals($("#sig-ctrl").value, $("#sig-out").value, selectedLocals("sig-leds"));
  if (!leds.length) throw new Error("Bitte mindestens eine LED wählen.");
  const line = `${asp}:${name}:${leds.map((i) => `${i}=${farbe}`).join(",")}`;
  const ta = $("#sig-asp");
  ta.value = ta.value.trim() ? `${ta.value.trim()}\n${line}` : line;
});

$("#sig-add").onclick = () => {
  const updating = editing.kind === "signal" && editing.id;
  runAction(updating ? "Signal gespeichert" : "Signal angelegt", async () => {
    const id = $("#sig-id").value.trim();
    if (!id) throw new Error("Bitte eine ID vergeben.");
    const next = await api("/api/config");
    const begriffe = {};
    for (const line of $("#sig-asp").value.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      const [asp, name, rest] = t.split(":");
      const leds = {};
      for (const part of (rest || "").split(",")) {
        const [idx, col] = part.split("=");
        if (idx) leds[Number(idx)] = (col || "FF0000").trim();
      }
      begriffe[Number(asp)] = { name: name || String(asp), leds };
    }
    if (!Object.keys(begriffe).length) throw new Error("Bitte mindestens einen Begriff übernehmen.");
    next.signale = next.signale || {};
    replaceKey(next.signale, updating ? editing.id : null, id, { controller: $("#sig-ctrl").value, begriffe });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("signal");
  });
};

$("#sp-add").onclick = () => {
  const updating = editing.kind === "spezial" && editing.id;
  runAction(updating ? "Spezial gespeichert" : "Spezial angelegt", async () => {
    const id = $("#sp-id").value.trim();
    const leds = toGlobals($("#sp-ctrl").value, $("#sp-out").value, selectedLocals("sp-leds"));
    if (!id) throw new Error("Bitte eine ID vergeben.");
    if (!leds.length) throw new Error("Bitte mindestens eine LED wählen.");
    const fx = Number($("#sp-fx").value);
    if (!Number.isInteger(fx) || fx < 0) throw new Error("Bitte einen Effekt wählen.");
    const pal = Number($("#sp-pal").value);
    const sx = Number($("#sp-sx").value);
    const ix = Number($("#sp-ix").value);
    if (!Number.isInteger(sx) || sx < 0 || sx > 255) throw new Error("Geschwindigkeit muss 0–255 sein.");
    if (!Number.isInteger(ix) || ix < 0 || ix > 255) throw new Error("Intensität muss 0–255 sein.");
    const next = await api("/api/config");
    next.spezial = next.spezial || {};
    replaceKey(next.spezial, updating ? editing.id : null, id, {
      controller: $("#sp-ctrl").value,
      leds,
      effekt: fx,
      palette: Number.isInteger(pal) && pal >= 0 ? pal : 0,
      geschwindigkeit: sx,
      intensitaet: ix,
      farbe: parseHex($("#sp-farbe").value) || DEFAULT_COLOR,
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("spezial");
  });
};

async function loadYaml() {
  const data = await api("/api/config");
  $("#yaml").value = JSON.stringify(data, null, 2);
  $("#yml-err").textContent = "";
}

$("#yml-apply").onclick = () => runAction("Konfiguration übernommen", async () => {
  let payload;
  try {
    payload = JSON.parse($("#yaml").value);
  } catch (e) {
    $("#yml-err").textContent = e.message;
    throw new Error("JSON ungültig – Speichern fehlgeschlagen");
  }
  try {
    await api("/api/config", { method: "PUT", body: JSON.stringify(payload) });
  } catch (e) {
    $("#yml-err").textContent = e.message;
    throw e;
  }
  $("#yml-err").textContent = "";
  await refresh();
});

$("#yml-reload").onclick = () => runAction("Konfiguration neu geladen", async () => {
  await api("/api/reload", { method: "POST" });
  await refresh();
  await loadYaml();
});

refresh();
setInterval(() => {
  if (!isEditing()) refresh();
}, 4000);
