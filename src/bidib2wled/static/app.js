const $ = (sel) => document.querySelector(sel);
let I18N = {};
let I18N_EN = {};
let LOCALE = "en";

function t(key, vars) {
  let s = (I18N && Object.prototype.hasOwnProperty.call(I18N, key) && I18N[key])
    || (I18N_EN && I18N_EN[key])
    || key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  }
  return s;
}

function applyI18n(root) {
  const scope = root || document;
  scope.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
  });
  scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.getAttribute("data-i18n-title"));
  });
  scope.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria")));
  });
}

async function initI18n() {
  let supported = ["en", "de"];
  try {
    const meta = await fetch("/api/languages").then((r) => r.json());
    if (meta && Array.isArray(meta.languages) && meta.languages.length) supported = meta.languages;
  } catch (_err) {
    /* keep defaults */
  }
  const prefs = [...(navigator.languages || []), navigator.language || "en"]
    .map((item) => String(item || "").slice(0, 2).toLowerCase())
    .filter(Boolean);
  LOCALE = prefs.find((code) => supported.includes(code)) || "en";
  try {
    I18N_EN = await fetch("/static/i18n/en.json").then((r) => r.json());
  } catch (_err) {
    I18N_EN = {};
  }
  if (LOCALE === "en") {
    I18N = I18N_EN;
  } else {
    try {
      I18N = await fetch(`/static/i18n/${LOCALE}.json`).then((r) => r.json());
    } catch (_err) {
      I18N = I18N_EN;
      LOCALE = "en";
    }
  }
  document.documentElement.lang = LOCALE;
  applyI18n();
}

const DEFAULT_COLOR = "FFFFFF";
const ANTEIL_PRIMARY = { r: "FF0000", g: "00FF00", b: "0000FF" };
const ANTEIL_SNAP_COLORS = new Set(["FF0000", "00FF00", "0000FF", "FFFFFF"]);
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
  if (el.closest(".combo") || el.closest(".listbox")) return true;
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
    throw new Error(msg || t("err.save"));
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
    notify(e.message || t("err.save"), false);
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
  { ctrl: "ins-ctrl", out: "ins-out", led: "ins-after", insert: true },
  { ctrl: "del-ctrl", out: "del-out", led: "del-from", remove: true },
  { ctrl: "l-ctrl", out: "l-out", led: "l-leds", anteil: "l-anteil", farbe: "l-farbe" },
  { ctrl: "h-ctrl", out: "h-out", led: "h-leds", anteil: "h-anteil", farbe: "h-win-farbe" },
  { ctrl: "sig-ctrl", out: "sig-out", led: "sig-leds", anteil: "sig-anteil", farbe: "sig-farbe" },
  { ctrl: "sp-ctrl", out: "sp-out", led: "sp-leds", anteil: "sp-anteil", farbe: "sp-farbe" },
  { ctrl: "v-ctrl", out: "v-out", led: "v-leds", anteil: "v-anteil", farbe: "v-farbe" },
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
    refreshSelectFilter(el);
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
  refreshSelectFilter(el);
}

const FILTER_SINGLE_SELECTS = ["id-led", "ins-after", "del-from", "sp-fx", "sp-pal"];
const FILTER_MULTI_SELECTS = [
  "l-leds", "h-leds", "sig-leds", "sp-leds", "v-leds",
  "g-mem", "s-grp", "v-mod-kan",
];

function allOptionsOf(el) {
  if (!el) return [];
  return el._optCache || [...el.options];
}

function selectedValuesOf(el) {
  return allOptionsOf(el).filter((opt) => opt.selected).map((opt) => opt.value);
}

function selectValue(el) {
  const selected = selectedValuesOf(el);
  return selected.length ? selected[0] : "";
}

function optionMatchesFilter(opt, q) {
  return opt.textContent.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q);
}

function cacheSelectOptions(el) {
  el._optCache = [...el.options];
  for (const opt of el._optCache) {
    const parent = opt.parentElement;
    opt._optGroup = parent && parent.tagName === "OPTGROUP" ? parent.label : null;
  }
}

function applySelectFilter(el) {
  const input = el && el._filterInput;
  if (!input) return;
  const cache = el._optCache || [...el.options];
  const q = input.value.trim().toLowerCase();
  const frag = document.createDocumentFragment();
  const groups = new Map();
  let shown = 0;
  for (const opt of cache) {
    if (q && !optionMatchesFilter(opt, q)) continue;
    shown += 1;
    if (opt._optGroup != null) {
      let grp = groups.get(opt._optGroup);
      if (!grp) {
        grp = document.createElement("optgroup");
        grp.label = opt._optGroup;
        groups.set(opt._optGroup, grp);
        frag.appendChild(grp);
      }
      grp.appendChild(opt);
    } else {
      frag.appendChild(opt);
    }
  }
  if (!shown) {
    const empty = document.createElement("option");
    empty.disabled = true;
    empty.textContent = t("filter.no_match");
    frag.appendChild(empty);
  }
  el.replaceChildren(frag);
}

function renderComboItems(el) {
  const c = el && el._combo;
  if (!c) return;
  const q = c.search.value.trim().toLowerCase();
  const frag = document.createDocumentFragment();
  let shown = 0;
  for (const opt of el.options) {
    if (q && !optionMatchesFilter(opt, q)) continue;
    const item = document.createElement("div");
    item.className = "combo-item";
    if (opt.className) item.classList.add(opt.className);
    if (opt.selected) item.classList.add("combo-sel");
    if (opt.disabled) {
      item.classList.add("combo-disabled");
    } else {
      item.dataset.value = opt.value;
    }
    if (opt.title) item.title = opt.title;
    item.textContent = opt.textContent;
    item.setAttribute("role", "option");
    frag.appendChild(item);
    shown += 1;
  }
  if (!shown) {
    const empty = document.createElement("div");
    empty.className = "combo-item combo-disabled";
    empty.textContent = t("filter.no_match");
    frag.appendChild(empty);
  }
  c.items.replaceChildren(frag);
  c.active = -1;
}

function syncComboDisplay(el) {
  const c = el && el._combo;
  if (!c) return;
  const opt = el.selectedOptions[0];
  c.label.textContent = opt ? opt.textContent : "–";
  c.btn.disabled = el.disabled;
}

function syncCombo(el) {
  const c = el && el._combo;
  if (!c) return;
  if (!c.panel.classList.contains("hidden")) renderComboItems(el);
  syncComboDisplay(el);
}

function closeCombo(el) {
  const c = el && el._combo;
  if (c) c.panel.classList.add("hidden");
}

function closeAllCombos() {
  document.querySelectorAll(".combo-panel:not(.hidden)").forEach((panel) => {
    panel.classList.add("hidden");
  });
}

function openCombo(el) {
  const c = el._combo;
  closeAllCombos();
  c.panel.classList.remove("hidden");
  c.search.value = "";
  renderComboItems(el);
  const rect = c.panel.getBoundingClientRect();
  c.root.classList.toggle("combo-up", rect.bottom > window.innerHeight - 8);
  c.search.focus();
}

function pickComboItem(el, item) {
  el.value = item.dataset.value;
  el.dispatchEvent(new Event("change", { bubbles: true }));
  closeCombo(el);
  el._combo.btn.focus();
}

function comboKeydown(el, e) {
  const c = el._combo;
  const items = [...c.items.querySelectorAll("[data-value]")];
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (!items.length) return;
    c.active = (c.active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items.forEach((it, i) => it.classList.toggle("combo-active", i === c.active));
    items[c.active].scrollIntoView({ block: "nearest" });
    return;
  }
  if (e.key === "Enter") {
    e.preventDefault();
    const pick = items[c.active] || items[0];
    if (pick) pickComboItem(el, pick);
  }
}

function refreshSelectFilter(el) {
  if (!el) return;
  if (el._combo) {
    syncCombo(el);
    return;
  }
  const input = el._filterInput;
  if (!input) return;
  cacheSelectOptions(el);
  input.disabled = el.disabled;
  applySelectFilter(el);
}

function clearSelectFilter(el) {
  if (!el) return;
  if (el._combo) {
    const search = el._combo.search;
    if (search.value) {
      search.value = "";
      renderComboItems(el);
    }
    return;
  }
  const input = el._filterInput;
  if (input && input.value) {
    input.value = "";
    applySelectFilter(el);
  }
}

function setSelectValue(el, value) {
  if (!el) return;
  clearSelectFilter(el);
  el.value = value;
  syncCombo(el);
}

function attachSelectFilter(el) {
  if (!el || el._filterInput) return;
  const wrap = document.createElement("div");
  wrap.className = "listbox";
  const input = document.createElement("input");
  input.type = "search";
  input.className = "select-filter";
  input.placeholder = t("ph.filter");
  input.setAttribute("aria-label", t("ph.filter"));
  input.autocomplete = "off";
  input.spellcheck = false;
  el.insertAdjacentElement("beforebegin", wrap);
  wrap.appendChild(input);
  wrap.appendChild(el);
  el._filterInput = input;
  input.addEventListener("input", () => applySelectFilter(el));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      input.value = "";
      applySelectFilter(el);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const first = [...el.options].find((opt) => !opt.disabled);
      if (!first) return;
      first.selected = !first.selected;
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      el.focus();
    }
  });
  refreshSelectFilter(el);
}

function attachCombo(el) {
  if (!el || el._combo) return;
  el.classList.add("combo-src");
  const root = document.createElement("div");
  root.className = "combo";
  root.innerHTML =
    '<button type="button" class="combo-btn" aria-haspopup="listbox">' +
    '<span class="combo-label"></span><span class="combo-caret">▾</span></button>' +
    '<div class="combo-panel hidden">' +
    `<input type="search" class="combo-search" autocomplete="off" spellcheck="false" placeholder="${esc(t("ph.filter"))}">` +
    '<div class="combo-items" role="listbox"></div></div>';
  el.insertAdjacentElement("beforebegin", root);
  const c = {
    root,
    btn: root.querySelector(".combo-btn"),
    panel: root.querySelector(".combo-panel"),
    search: root.querySelector(".combo-search"),
    items: root.querySelector(".combo-items"),
    label: root.querySelector(".combo-label"),
    active: -1,
  };
  el._combo = c;
  c.btn.addEventListener("click", () => {
    if (el.disabled) return;
    if (c.panel.classList.contains("hidden")) openCombo(el);
    else closeCombo(el);
  });
  c.btn.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      openCombo(el);
    }
  });
  c.search.addEventListener("input", () => renderComboItems(el));
  c.search.addEventListener("keydown", (e) => comboKeydown(el, e));
  c.items.addEventListener("click", (e) => {
    const item = e.target.closest("[data-value]");
    if (item) pickComboItem(el, item);
  });
  c.panel.addEventListener("click", (e) => e.stopPropagation());
  c.root.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !c.panel.classList.contains("hidden")) {
      e.stopPropagation();
      closeCombo(el);
      c.btn.focus();
    }
  });
  el.addEventListener("change", () => syncComboDisplay(el));
  syncCombo(el);
}

document.addEventListener("pointerdown", (e) => {
  if (e.target.closest(".combo")) return;
  closeAllCombos();
});

function ledOwners(ctrlName, globalIndex) {
  const leds = (status.usage && status.usage.leds && status.usage.leds[ctrlName]) || {};
  return leds[String(globalIndex)] || [];
}

function expandAnteil(anteil) {
  if (anteil === "r" || anteil === "g" || anteil === "b") return [anteil];
  return ["r", "g", "b"];
}

function ledOwnersForAnteil(ctrlName, globalIndex, anteil) {
  const channels = (status.usage && status.usage.channels && status.usage.channels[ctrlName]) || {};
  const perLed = channels[String(globalIndex)];
  if (!perLed) return ledOwners(ctrlName, globalIndex);
  const owners = new Set();
  for (const component of expandAnteil(anteil || "rgb")) {
    for (const id of perLed[component] || []) owners.add(id);
  }
  return [...owners];
}

function objectOwners(objId) {
  const objects = (status.usage && status.usage.objects) || {};
  return objects[objId] || [];
}

function currentLedExclude() {
  const ids = new Set();
  if (!editing.kind || !editing.id) return ids;
  if (editing.kind === "lamp" || editing.kind === "special" || editing.kind === "signal" || editing.kind === "vehicle") {
    ids.add(editing.id);
    return ids;
  }
  if (editing.kind === "house") {
    ids.add(editing.id);
    const house = (cfg.houses || {})[editing.id];
    if (house) {
      for (const windowId of Object.keys(house.windows || {})) {
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
    suffix: t("led.in_use"),
    title: t("led.in_use_by", { ids: other.join(", ") }),
  };
}

const ANTEIL_ALIASES = {
  r: "r",
  rot: "r",
  red: "r",
  g: "g",
  gruen: "g",
  "grün": "g",
  green: "g",
  b: "b",
  blau: "b",
  blue: "b",
  rgb: "rgb",
  alle: "rgb",
  all: "rgb",
};

function parseAnteil(value) {
  const raw = String(value || "rgb").trim().toLowerCase();
  return ANTEIL_ALIASES[raw] || "rgb";
}

function nameVon(item) {
  if (item == null) return NaN;
  if (item.start != null && item.start !== "") return Number(item.start);
  if (item.von != null && item.von !== "") return Number(item.von);
  return Number(item.led);
}

function nameBis(item) {
  if (item == null) return NaN;
  if (item.end != null && item.end !== "") return Number(item.end);
  if (item.bis != null && item.bis !== "") return Number(item.bis);
  return nameVon(item);
}

function controllerNames(name) {
  const ctrl = (cfg.controller || []).find((item) => item.name === name);
  return (ctrl && ctrl.names) || [];
}

function smallestLedName(items) {
  return items.slice().sort((a, b) => {
    const span = (nameBis(a) - nameVon(a)) - (nameBis(b) - nameVon(b));
    if (span) return span;
    return String(a.name || "").localeCompare(String(b.name || ""), LOCALE);
  })[0];
}

function ledNameFor(ctrlName, index, _anteil) {
  const covering = controllerNames(ctrlName).filter((item) => {
    const von = nameVon(item);
    const bis = nameBis(item);
    return Number.isFinite(von) && Number.isFinite(bis) && von <= index && index <= bis;
  });
  if (!covering.length) return "";
  const parts = [];
  for (const component of ["r", "g", "b"]) {
    const hits = covering.filter((item) => parseAnteil(item.channel || item.anteil) === component);
    if (hits.length) parts.push(smallestLedName(hits).name);
  }
  if (parts.length) return parts.join(" / ");
  const rgb = covering.filter((item) => parseAnteil(item.channel || item.anteil) === "rgb");
  return rgb.length ? smallestLedName(rgb).name : "";
}

function ledParen(ctrlName, index) {
  const name = ledNameFor(ctrlName, index);
  return name || t("led.no", { n: index });
}

function parseLedNameLine(line) {
  const raw = String(line || "").trim();
  if (!raw || raw.startsWith("#")) return null;
  let left;
  let name;
  const eq = raw.indexOf("=");
  const colon = raw.indexOf(":");
  if (eq >= 0 && (colon < 0 || eq < colon)) {
    left = raw.slice(0, eq);
    name = raw.slice(eq + 1);
  } else if (colon >= 0) {
    left = raw.slice(0, colon);
    name = raw.slice(colon + 1);
  } else {
    const parts = raw.split(/\s+/);
    if (parts.length < 2) return null;
    left = parts[0];
    name = parts.slice(1).join(" ");
  }
  name = name.trim();
  left = left.trim();
  if (!name || !left) return null;
  const match = left.match(/^(?:led\s*)?(\d+)(?:\s*[-–]\s*(?:led\s*)?(\d+))?(?:\s*(r|g|b|rot|gruen|grün|green|blau|blue))?$/i);
  if (!match) return null;
  let von = Number(match[1]);
  let bis = Number(match[2] || von);
  if (!Number.isInteger(von) || !Number.isInteger(bis) || von < 1 || bis < 1) return null;
  if (bis < von) [von, bis] = [bis, von];
  return { von, bis, anteil: match[3] ? parseAnteil(match[3]) : "rgb", name };
}

function formatLedNameLine(von1, bis1, anteil, name) {
  const span = von1 === bis1 ? String(von1) : `${von1}-${bis1}`;
  const color = !anteil || anteil === "rgb" ? "" : anteil;
  return `${span}${color} = ${name}`;
}

function outputRange(ctrlName, outId) {
  const outs = outputsOf(ctrlName);
  const out = outs.find((item) => String(item.id) === String(outId)) || outs[0];
  if (out) {
    const len = Number(out.len) || 0;
    return { start: out.start || 0, end: (out.start || 0) + len, out };
  }
  const ctrl = (cfg.controller || []).find((item) => item.name === ctrlName);
  const n = (ctrl && ctrl.leds) || 0;
  return { start: 0, end: n, out: null };
}

function fillLedNameText() {
  const ta = $("#nam-text");
  if (!ta) return;
  if (document.activeElement === ta) return;
  const ctrlName = $("#nam-ctrl") && $("#nam-ctrl").value;
  const range = outputRange(ctrlName, $("#nam-out") && $("#nam-out").value);
  const end = range.end > range.start ? range.end : Number.POSITIVE_INFINITY;
  const lines = controllerNames(ctrlName)
    .filter((item) => {
      const von = nameVon(item);
      return Number.isFinite(von) && von >= range.start && von < end;
    })
    .map((item) => {
      const von1 = nameVon(item) - range.start + 1;
      const bis1 = nameBis(item) - range.start + 1;
      return formatLedNameLine(von1, bis1, parseAnteil(item.channel || item.anteil), item.name);
    });
  ta.value = lines.join("\n");
}

function fillLedNameEditor() {
  const ctrlEl = $("#nam-ctrl");
  if (!ctrlEl) return;
  fillOutputSelect("nam-out", ctrlEl.value);
  fillLedNameText();
}

function formatOutputLabel(out) {
  const n = (out.id ?? 0) + 1;
  const extras = [];
  if (out.pin != null && out.pin !== "") extras.push(t("output.gpio", { pin: out.pin }));
  extras.push(t("output.leds", { n: out.len ?? 0 }));
  const start = out.start ?? 0;
  const end = start + (out.len ?? 0) - 1;
  extras.push(t("output.index", { start, end }));
  return `${t("output.name", { n })} (${extras.join(", ")})`;
}

function fillOutputSelect(outId, ctrlName) {
  const el = document.getElementById(outId);
  const outs = outputsOf(ctrlName);
  fillOptions(
    el,
    outs.map((out) => ({ value: out.id, label: formatOutputLabel(out) })),
    el && el.value
  );
}

function highestConfigLed(ctrlName) {
  const leds = (status.usage && status.usage.leds && status.usage.leds[ctrlName]) || {};
  const keys = Object.keys(leds).map(Number).filter(Number.isFinite);
  return keys.length ? Math.max(...keys) : -1;
}

function fillLedSelect(ledId, ctrlName, outId, anteilId, insert, remove) {
  const el = document.getElementById(ledId);
  if (!el) return;
  const outs = outputsOf(ctrlName);
  const out = outs.find((item) => String(item.id) === String(outId)) || outs[0];
  const selected = new Set(selectedValuesOf(el));
  const wledLen = out && out.len ? out.len : 0;
  const start = out ? out.start : 0;
  const highest = highestConfigLed(ctrlName);
  const end = remove ? Math.max(start + wledLen, highest + 1) : start + wledLen;
  const count = Math.max(0, end - start);
  if (!out || !count) {
    el.innerHTML = insert
      ? `<option value="-1">${esc(t("led.at_start"))}</option>`
      : `<option value="">${esc(t("led.none"))}</option>`;
    refreshSelectFilter(el);
    showChosenLeds(el);
    return;
  }
  const exclude = currentLedExclude();
  const anteil = anteilId && document.getElementById(anteilId) ? document.getElementById(anteilId).value : "rgb";
  const options = Array.from({ length: count }, (_, i) => {
    const global = start + i;
    const mark = usedMark(ledOwnersForAnteil(ctrlName, global, anteil), exclude);
    const cls = mark.used ? ' class="opt-used"' : "";
    const title = mark.title ? ` title="${esc(mark.title)}"` : "";
    const beyond = i >= wledLen ? t("led.config_only") : "";
    const label = `LED ${i + 1} (${esc(ledParen(ctrlName, global))})${mark.suffix}${beyond}`;
    return `<option value="${i}"${cls}${title}>${label}</option>`;
  });
  if (insert) options.unshift(`<option value="-1">${esc(t("led.at_start"))}</option>`);
  el.innerHTML = options.join("");
  if (el.multiple) {
    [...el.options].forEach((opt) => {
      opt.selected = selected.has(opt.value);
    });
  } else if (selected.size && [...el.options].some((opt) => selected.has(opt.value))) {
    el.value = [...selected][0];
  }
  refreshSelectFilter(el);
  scrollSelectToSelection(el);
  showChosenLeds(el);
}

function selectedLocals(ledId) {
  const el = document.getElementById(ledId);
  return allOptionsOf(el)
    .filter((opt) => opt.selected)
    .map((opt) => Number(opt.value))
    .filter((n) => Number.isFinite(n));
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
    fillLedSelect(group.led, ctrl.value, out && out.value, group.anteil, group.insert, group.remove);
  }
}

function fillCtrlSelects() {
  const names = (cfg.controller || []).map((c) => c.name).filter(Boolean);
  for (const id of ["id-ctrl", "ins-ctrl", "del-ctrl", "nam-ctrl", "l-ctrl", "h-ctrl", "sig-ctrl", "sp-ctrl", "v-ctrl"]) {
    const el = document.getElementById(id);
    if (!el) continue;
    const current = el.value;
    if (!names.length) {
      el.innerHTML = `<option value="">${esc(t("ctrl.empty_option"))}</option>`;
      continue;
    }
    el.innerHTML = names.map((n) => `<option value="${n}">${n}</option>`).join("");
    el.value = names.includes(current) ? current : names[0];
  }
  syncLedDropdowns();
  fillLedNameEditor();
  fillSpecialFx($("#sp-ctrl") && $("#sp-ctrl").value);
  renderLedBusDiff();
  updateRundumHint();
}

function fillNamedSelect(el, names, current, emptyLabel) {
  if (!el) return;
  if (!names.length) {
    el.innerHTML = `<option value="">${esc(emptyLabel)}</option>`;
    refreshSelectFilter(el);
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
    selectValue($("#sp-fx")),
    reachable ? t("fx.none") : t("fx.unloaded")
  );
  fillNamedSelect(
    $("#sp-pal"),
    (ctrl && ctrl.palettes) || [],
    selectValue($("#sp-pal")),
    reachable ? t("pal.none") : t("pal.unloaded")
  );
}

function groupMemberSections(excludeId) {
  const sections = [];
  const add = (label, ids) => {
    const items = ids.filter((id) => id && id !== excludeId);
    if (items.length) sections.push({ label, items });
  };
  add(t("section.lamps"), Object.keys(cfg.lamps || {}));
  add(t("section.houses"), Object.keys(cfg.houses || {}));
  const windows = [];
  for (const [houseId, house] of Object.entries(cfg.houses || {})) {
    for (const windowId of Object.keys(house.windows || {})) {
      windows.push(`${houseId}.${windowId}`);
    }
  }
  add(t("section.windows"), windows);
  add(t("section.signals"), Object.keys(cfg.signals || {}));
  add(t("section.special"), Object.keys(cfg.special || {}));
  add(t("section.vehicles"), Object.keys(cfg.vehicles || {}));
  add(t("section.groups"), Object.keys(cfg.groups || {}));
  add(t("section.sequences"), Object.keys(cfg.sequences || {}));
  return sections;
}

function fillGroupMemberSelect(selected) {
  const el = $("#g-mem");
  if (!el) return;
  const keep = selected
    ? new Set(selected.map(String))
    : new Set(selectedValuesOf(el));
  const exclude = editing.kind === "group" && editing.id ? editing.id : null;
  const sections = groupMemberSections(exclude);
  if (!sections.length) {
    el.innerHTML = `<option value="">${esc(t("members.empty"))}</option>`;
    el.disabled = true;
    refreshSelectFilter(el);
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
  refreshSelectFilter(el);
}

function fillMultiSelect(el, items, selected, emptyLabel, excludeIds) {
  if (!el) return;
  const keep = selected
    ? new Set(selected.map(String))
    : new Set(selectedValuesOf(el));
  if (!items.length) {
    el.innerHTML = `<option value="">${esc(emptyLabel)}</option>`;
    el.disabled = true;
    refreshSelectFilter(el);
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
  refreshSelectFilter(el);
}

function fillSequenceGroupSelect(selected) {
  const exclude = editing.kind === "sequence" && editing.id ? [editing.id] : [];
  fillMultiSelect($("#s-grp"), Object.keys(cfg.groups || {}), selected, t("groups.empty"), exclude);
}

function selectedMembers(selectId) {
  const el = document.getElementById(selectId);
  return selectedValuesOf(el).filter(Boolean);
}

for (const group of LED_GROUPS) {
  const ctrl = document.getElementById(group.ctrl);
  const out = document.getElementById(group.out);
  if (ctrl) {
    ctrl.addEventListener("change", () => {
      fillOutputSelect(group.out, ctrl.value);
      const next = document.getElementById(group.out);
      fillLedSelect(group.led, ctrl.value, next && next.value, group.anteil, group.insert, group.remove);
      if (group.ctrl === "sp-ctrl") fillSpecialFx(ctrl.value);
      if (group.insert || group.remove) renderLedBusDiff(ctrl.value);
    });
  }
  if (out) {
    out.addEventListener("change", () => {
      fillLedSelect(group.led, document.getElementById(group.ctrl).value, out.value, group.anteil, group.insert, group.remove);
    });
  }
  if (group.anteil) {
    const anteil = document.getElementById(group.anteil);
    if (anteil) {
      anteil.addEventListener("change", () => {
        if (group.farbe) syncFarbeToAnteil(group.farbe, anteil.value);
        const ctrlEl = document.getElementById(group.ctrl);
        const outEl = document.getElementById(group.out);
        fillLedSelect(group.led, ctrlEl && ctrlEl.value, outEl && outEl.value, group.anteil, group.insert, group.remove);
        if (group.led === "v-leds") updateRundumHint();
      });
    }
  }
  const ledEl = document.getElementById(group.led);
  if (ledEl) {
    ledEl.addEventListener("change", () => {
      showChosenLeds(ledEl);
      if (group.led === "v-leds") updateRundumHint();
    });
  }
}

if ($("#nam-ctrl")) {
  $("#nam-ctrl").addEventListener("change", () => {
    fillOutputSelect("nam-out", $("#nam-ctrl").value);
    fillLedNameText();
  });
}
if ($("#nam-out")) {
  $("#nam-out").addEventListener("change", fillLedNameText);
}

function pairingStatus(b) {
  if (b.logged_on) return t("pairing.connected");
  if (b.pairing_open) return t("pairing.open_wait");
  if (b.pending) return t("pairing.request_open");
  if ((b.sessions || 0) > 0) return t("pairing.host_not_logged");
  return t("status.dash");
}

function renderStatus() {
  const b = status.bidib || {};
  $("#bidib-dl").innerHTML = `
    <dt>${t("status.node")}</dt><dd>${b.node_name || ""}</dd>
    <dt>${t("status.uid")}</dt><dd><code>${b.unique_id || ""}</code></dd>
    <dt>${t("status.port_mode")}</dt><dd>${b.port} / ${b.mode} ${b.enabled ? "" : t("status.off")}</dd>
    <dt>${t("status.logged_on")}</dt><dd class="${b.logged_on ? "ok" : "bad"}">${b.logged_on ? t("status.yes") : t("status.no")} (${b.sessions || 0} ${t("status.links")})</dd>
    <dt>${t("status.pairing")}</dt><dd>${pairingStatus(b)}</dd>
    <dt>${t("status.trusted")}</dt><dd>${(b.trusted || []).join(", ") || t("status.dash")}</dd>
  `;
  const banner = $("#pairing-banner");
  if (b.pending) {
    banner.classList.remove("hidden");
    banner.innerHTML = t("pairing.needed", { who: `<strong>${esc(b.pending.user || b.pending.prod || b.pending.uid)}</strong>` });
  } else if (!b.logged_on && (b.sessions || 0) > 0) {
    banner.classList.remove("hidden");
    banner.innerHTML = t("pairing.host_waiting");
  } else {
    banner.classList.add("hidden");
  }
  $("#controllers").innerHTML = (status.controllers || [])
    .map((c) => {
      const href = c.url || (c.ip ? `http://${c.ip}:${c.port || 80}/` : "");
      const ip = c.ip
        ? `<a href="${href}" target="_blank" rel="noopener">${c.ip}</a>`
        : t("ctrl.no_ip");
      const outs = (c.outputs || []).map((o) => formatOutputLabel(o)).join(" · ");
      const warns = (c.warnings || [])
        .map((w) => `<li>${esc(t(w))}</li>`)
        .join("");
      return `<div><strong>${c.name}</strong> ${ip} · ${c.leds || "?"} LEDs ·
      <span class="${c.reachable ? "ok" : "bad"}">${c.reachable ? t("ctrl.reachable") : t("ctrl.unreachable")}</span>
      ${c.mac ? `<span class="chip">${c.mac}</span>` : ""}
      ${outs ? `<div class="sub">${outs}</div>` : ""}
      ${warns ? `<ul class="warn">${warns}</ul>` : ""}</div>`;
    })
    .join("") || `<p>${t("ctrl.none")}</p>`;
  renderObjects();
  renderLedBusDiff();
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
  return `<label class="switch" title="${esc(t("objects.test_title"))}">
    <input type="checkbox" data-switch="${esc(o.id)}" ${o.on ? "checked" : ""} ${o.in_progress ? "disabled" : ""}>
    <span></span>
  </label>`;
}

function objectInfoCell(o) {
  const rows = o.info || [];
  const body = rows.length
    ? rows.map((row) => `<div><strong>${esc(row.program)}:</strong> ${esc(row.text)}</div>`).join("")
    : t("objects.no_hints");
  return `<span class="obj-help-wrap">
    <button type="button" class="obj-help" aria-label="${esc(t("objects.info"))}">?</button>
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
  return `<th class="sortable${active}" data-sort="${key}" title="${esc(t("objects.sort", { label }))}">${esc(label)}${sortMark(key)}</th>`;
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
      cmp = String(a.kind_label || a.kind || "").localeCompare(String(b.kind_label || b.kind || ""), LOCALE);
      if (!cmp) cmp = String(a.id || "").localeCompare(String(b.id || ""), LOCALE);
    } else {
      cmp = String(a.id || "").localeCompare(String(b.id || ""), LOCALE);
    }
    return cmp * dir;
  });
}

function renderObjects() {
  const list = status.objects || [];
  if (!list.length) {
    $("#objects").innerHTML = `<p>${t("objects.none")}</p>`;
    return;
  }
  $("#objects").innerHTML = `
    <table><thead><tr>${sortHeader("id", t("objects.col.object"))}${sortHeader("kind", t("objects.col.type"))}${sortHeader("address", t("objects.col.address"))}<th>${t("objects.col.info")}</th><th>${t("objects.col.test")}</th><th></th></tr></thead><tbody>
    ${sortedObjects(list).map((o) => `
      <tr>
        <td>
          <button type="button" class="obj-link" data-edit="${esc(o.id)}">${esc(o.id)}</button>
          ${o.in_progress ? " …" : ""}
          ${o.error ? ` <span class="bad">${esc(o.error)}</span>` : ""}
        </td>
        <td>${esc(t(`kind.${o.kind}`) !== `kind.${o.kind}` ? t(`kind.${o.kind}`) : (o.kind_label || o.kind || ""))}</td>
        <td>
          <input type="number" min="0" max="255" step="1" data-address="${esc(o.id)}"
            value="${o.address != null ? esc(o.address) : ""}"
            placeholder="—"
            title="${esc(t("objects.address_title"))}">
        </td>
        <td class="obj-info">${objectInfoCell(o)}</td>
        <td>${objectTestControl(o)}</td>
        <td>
          <div class="obj-actions">
            <button type="button" class="secondary" data-edit="${esc(o.id)}">${esc(t("objects.edit"))}</button>
            <button type="button" class="secondary danger" data-del="${esc(o.id)}">${esc(t("objects.delete"))}</button>
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
  fillVehicleModeChannels();
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
      <input class="claim-name" placeholder="${esc(t("ph.name_example"))}">
      <button type="button">${esc(t("discovery.claim"))}</button>`;
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
    `${d.name} ${d.ip} · ${d.led_count} LEDs · ${d.mac || t("ctrl.no_mac")}`;
  return key;
}

async function syncDiscovery() {
  const box = $("#unbound");
  const data = await api("/api/discovery");
  const devices = data.unbound || [];
  if (!devices.length) {
    if (!box.querySelector(".claim-name")) {
      box.innerHTML = `<p>${t("discovery.empty")}</p>`;
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

window.claim = (btn) => runAction(t("ok.claimed"), async () => {
  const input = btn.parentElement.querySelector(".claim-name");
  const name = input.value.trim();
  if (!name) throw new Error(t("err.logical_name"));
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
    notify(e.message || t("err.switch"), false);
    await refresh();
  }
};

$("#btn-pair").onclick = () => runAction(t("ok.pairing"), async () => {
  await api("/api/pairing/accept", { method: "POST" });
  await refresh();
  const b = status.bidib || {};
  if (b.logged_on) {
    notify(t("ok.paired"), true);
    return false;
  }
  if (b.pending) {
    notify(t("ok.host_accepted"), true);
    return false;
  }
  notify(t("ok.pairing_wait"), true);
  return false;
});
$("#btn-reject").onclick = () => runAction(t("ok.rejected"), async () => {
  await api("/api/pairing/reject", { method: "POST" });
  await refresh();
});

$("#w-save-adapter").onclick = () => runAction(t("ok.adapter"), async () => {
  const next = await api("/api/config");
  next.adapter = next.adapter || {};
  next.adapter.netbidib = next.adapter.netbidib || {};
  next.adapter.netbidib.enabled = true;
  next.adapter.netbidib.node_name = $("#w-name").value;
  next.adapter.netbidib.port = Number($("#w-port").value);
  next.adapter.netbidib.mode = $("#w-mode").value;
  await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
  await refresh();
});

$("#m-add").onclick = () => runAction(t("ok.added"), async () => {
  const name = $("#m-name").value.trim();
  const ip = $("#m-ip").value.trim();
  if (!name) throw new Error(t("err.name"));
  if (!ip) throw new Error(t("err.ip"));
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

$("#id-go").onclick = () => runAction(t("ok.blink"), async () => {
  await api("/api/identify", {
    method: "POST",
    body: JSON.stringify({
      controller: $("#id-ctrl").value,
      output: Number($("#id-out").value),
      index: Number($("#id-led").value),
    }),
  });
});

function ledBusDiffText(ctrlName) {
  const ctrl = controllerByName(ctrlName);
  if (!ctrlName || !ctrl) return t("bus.none");
  const wled = Number(ctrl.leds) || 0;
  const highest = highestConfigLed(ctrlName);
  const span = highest + 1;
  const delta = span - wled;
  if (!wled && span <= 0) return t("bus.unknown");
  if (delta === 0) {
    return t("bus.match", { n: wled, s: wled === 1 ? "" : "s" });
  }
  if (delta > 0) {
    return t("bus.more_cfg", { wled, highest, span, delta });
  }
  return t("bus.more_wled", { wled, highest: Math.max(highest, 0), delta: -delta });
}

function renderLedBusDiff(name) {
  const el = $("#led-bus-diff");
  if (!el) return;
  const ins = $("#ins-ctrl") && $("#ins-ctrl").value;
  const del = $("#del-ctrl") && $("#del-ctrl").value;
  const names = [];
  for (const n of [name, del, ins]) {
    if (n && !names.includes(n)) names.push(n);
  }
  if (!names.length) {
    el.textContent = ledBusDiffText("");
    return;
  }
  el.innerHTML = names
    .map((n) => `<div><strong>${esc(n)}:</strong> ${esc(ledBusDiffText(n))}</div>`)
    .join("");
}

$("#ins-go").onclick = () => runAction(t("ok.leds_adjusted"), async () => {
  const controller = $("#ins-ctrl").value;
  const output = Number($("#ins-out").value);
  const after = Number($("#ins-after").value);
  const count = Number($("#ins-count").value);
  if (!controller) throw new Error(t("err.controller"));
  if (!Number.isInteger(after) || after < -1) throw new Error(t("err.after"));
  if (!Number.isInteger(count) || count < 1) throw new Error(t("err.count"));
  const out = outputsOf(controller).find((item) => String(item.id) === String(output));
  const start = out ? out.start : 0;
  const first = start + after + 1;
  const wled = (controllerByName(controller) && controllerByName(controller).leds) || 0;
  const where = after < 0
    ? t("confirm.insert_start")
    : t("confirm.insert_after", { n: after + 1, label: ledParen(controller, start + after) });
  const ok = window.confirm(t("confirm.insert", { count, where, first, wled }));
  if (!ok) return false;
  const data = await api("/api/leds/insert", {
    method: "POST",
    body: JSON.stringify({ controller, output, after, count }),
  });
  status = data.status || (await api("/api/status"));
  cfg = await api("/api/config");
  renderStatus();
  fillCtrlSelects();
  const extra = data.delta ? ` · ${t("ok.delta", { n: data.delta })}` : "";
  notify(t("ok.shifted", { n: data.shifted || 0, extra }), true);
  return false;
});

$("#del-go").onclick = () => runAction(t("ok.leds_adjusted"), async () => {
  const controller = $("#del-ctrl").value;
  const output = Number($("#del-out").value);
  const startAt = Number($("#del-from").value);
  const count = Number($("#del-count").value);
  if (!controller) throw new Error(t("err.controller"));
  if (!Number.isInteger(startAt) || startAt < 0) throw new Error(t("err.from"));
  if (!Number.isInteger(count) || count < 1) throw new Error(t("err.count"));
  const out = outputsOf(controller).find((item) => String(item.id) === String(output));
  const start = out ? out.start : 0;
  const first = start + startAt;
  const wled = (controllerByName(controller) && controllerByName(controller).leds) || 0;
  const span = highestConfigLed(controller) + 1;
  const owners = [];
  for (let i = 0; i < count; i += 1) {
    for (const id of ledOwners(controller, first + i)) {
      if (!owners.includes(id)) owners.push(id);
    }
  }
  const ownerLine = owners.length ? t("confirm.owners", { ids: owners.join(", ") }) : "";
  const ok = window.confirm(
    t("confirm.delete", {
      count,
      from: startAt + 1,
      label: ledParen(controller, first),
      first: first + count,
      wled,
      span,
      delta: span - wled,
      owners: ownerLine,
    })
  );
  if (!ok) return false;
  const data = await api("/api/leds/delete", {
    method: "POST",
    body: JSON.stringify({ controller, output, start: startAt, count }),
  });
  status = data.status || (await api("/api/status"));
  cfg = await api("/api/config");
  renderStatus();
  fillCtrlSelects();
  const parts = [t("ok.counted_down", { n: data.shifted || 0 })];
  if (data.dropped) parts.push(t("ok.dropped", { n: data.dropped }));
  if (data.delta) parts.push(t("ok.delta", { n: data.delta }));
  notify(parts.join(" · "), true);
  return false;
});

$("#nam-go").onclick = () => runAction(t("ok.names"), async () => {
  const controller = $("#nam-ctrl") && $("#nam-ctrl").value;
  if (!controller) throw new Error(t("err.controller"));
  const range = outputRange(controller, $("#nam-out") && $("#nam-out").value);
  const end = range.end > range.start ? range.end : Number.POSITIVE_INFINITY;
  const parsed = [];
  for (const raw of String($("#nam-text") && $("#nam-text").value || "").split("\n")) {
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const line = parseLedNameLine(trimmed);
    if (!line) throw new Error(t("err.line", { line: trimmed }));
    parsed.push({
      start: range.start + line.von - 1,
      end: range.start + line.bis - 1,
      channel: line.anteil || line.channel || "rgb",
      name: line.name,
    });
  }
  const next = await api("/api/config");
  const ctrl = (next.controller || []).find((item) => item.name === controller);
  if (!ctrl) throw new Error(t("err.controller_missing"));
  const kept = (ctrl.names || []).filter((item) => {
    const von = nameVon(item);
    return !(Number.isFinite(von) && von >= range.start && von < end);
  });
  ctrl.names = kept.concat(parsed);
  await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
  cfg = await api("/api/config");
  renderStatus();
  fillCtrlSelects();
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

function syncFarbeToAnteil(colorId, anteil) {
  const target = ANTEIL_PRIMARY[anteil];
  if (!target || !colorId) return;
  const input = document.getElementById(colorId);
  if (!input) return;
  const current = parseHex(input.value);
  if (current && !ANTEIL_SNAP_COLORS.has(current)) return;
  setColorInput(colorId, target);
}

function nextAspectNumber(begriffe) {
  const keys = Object.keys(begriffe || {}).map(Number).filter(Number.isFinite);
  return keys.length ? Math.max(...keys) + 1 : 0;
}

function parseSignalBegriffe(text) {
  const begriffe = {};
  for (const line of String(text || "").split("\n")) {
    const t = line.trim();
    if (!t) continue;
    const [aspRaw, name, rest] = t.split(":");
    const asp = Number(aspRaw);
    if (!Number.isFinite(asp)) continue;
    if (!begriffe[asp]) {
      begriffe[asp] = { name: (name || String(asp)).trim(), leds: {}, channels: {} };
    } else if (name && name.trim()) {
      begriffe[asp].name = name.trim();
    }
    for (const part of (rest || "").split(",")) {
      const bits = part.split("=").map((bit) => bit.trim());
      const idx = Number(bits[0]);
      if (!Number.isFinite(idx) || bits[0] === "") continue;
      begriffe[asp].leds[idx] = parseHex(bits[1]) || "FF0000";
      const anteil = (bits[2] || "rgb").toLowerCase();
      if (anteil && anteil !== "rgb") begriffe[asp].channels[idx] = anteil;
      else delete begriffe[asp].channels[idx];
    }
  }
  return begriffe;
}

function compactSignalBegriffe(begriffe) {
  for (const begriff of Object.values(begriffe || {})) {
    if (begriff.channels && !Object.keys(begriff.channels).length) delete begriff.channels;
  }
  return begriffe;
}

function scrollSelectToSelection(select) {
  if (!select || !select.size || select.size < 2) return;
  const option = select.selectedOptions[0];
  if (!option || !select.options.length) return;
  const avg = select.scrollHeight / select.options.length;
  select.scrollTop = Math.max(0, option.index * avg - select.clientHeight / 3);
}

function showChosenLeds(el) {
  if (!el) return;
  const host = el.closest(".listbox") || el;
  let hint = host.parentElement && host.parentElement.querySelector(":scope > .led-chosen");
  if (!hint) {
    hint = document.createElement("span");
    hint.className = "led-chosen";
    host.insertAdjacentElement("afterend", hint);
  }
  const labels = allOptionsOf(el)
    .filter((opt) => opt.selected)
    .map((opt) => opt.textContent.replace(/\s+·\s.*$/, "").trim())
    .filter(Boolean);
  hint.textContent = labels.length ? t("led.chosen", { labels: labels.join(", ") }) : "";
}

function selectLocals(ledId, locals) {
  const el = document.getElementById(ledId);
  if (!el) return;
  const want = new Set((locals || []).map(String));
  allOptionsOf(el).forEach((opt) => {
    opt.selected = want.has(opt.value);
  });
  applySelectFilter(el);
  scrollSelectToSelection(el);
  showChosenLeds(el);
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
  lamp: { title: "l-title", createKey: "edit.create.lamp", editKey: "edit.edit.lamp", art: "art-lampe", cancel: "l-cancel" },
  house: { title: "h-title", createKey: "edit.create.house", editKey: "edit.edit.house", art: "art-haus", cancel: "h-cancel" },
  group: { title: "g-title", createKey: "edit.create.group", editKey: "edit.edit.group", art: "art-gruppe", cancel: "g-cancel" },
  sequence: { title: "s-title", createKey: "edit.create.sequence", editKey: "edit.edit.sequence", art: "art-sequenz", cancel: "s-cancel" },
  signal: { title: "sig-title", createKey: "edit.create.signal", editKey: "edit.edit.signal", art: "art-signal", cancel: "sig-cancel" },
  special: { title: "sp-title", createKey: "edit.create.special", editKey: "edit.edit.special", art: "art-spezial", cancel: "sp-cancel" },
  vehicle: { title: "v-title", createKey: "edit.create.vehicle", editKey: "edit.edit.vehicle", art: "art-fahrzeug", cancel: "v-cancel" },
};

function setEditing(kind, id) {
  editing.kind = kind || null;
  editing.id = id || null;
  for (const [k, meta] of Object.entries(EDIT_META)) {
    const active = Boolean(kind === k && id);
    const title = document.getElementById(meta.title);
    if (title) title.textContent = t(active ? meta.editKey : meta.createKey);
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
  for (const g of Object.values(cfg.groups || {})) {
    g.members = (g.members || []).map((m) => rewriteRef(m, oldId, newId));
  }
  for (const seq of Object.values(cfg.sequences || {})) {
    seq.groups = (seq.groups || []).map((m) => rewriteRef(m, oldId, newId));
  }
  const acc = cfg.adapter && cfg.adapter.netbidib && cfg.adapter.netbidib.accessories;
  if (acc) {
    for (const [key, value] of Object.entries(acc)) acc[key] = rewriteRef(value, oldId, newId);
  }
}

function dropRefs(cfg, removed) {
  const gone = new Set(removed);
  for (const [gid, g] of Object.entries(cfg.groups || {})) {
    g.members = (g.members || []).filter((m) => !gone.has(m));
    if (!g.members.length) {
      delete cfg.groups[gid];
      gone.add(gid);
    }
  }
  for (const [sid, seq] of Object.entries(cfg.sequences || {})) {
    seq.groups = (seq.groups || []).filter((g) => !gone.has(g) && (cfg.groups || {})[g]);
    if (!seq.groups.length) {
      delete cfg.sequences[sid];
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
  if (cfg.lamps && cfg.lamps[id]) {
    delete cfg.lamps[id];
    removed.push(id);
  } else if (cfg.houses && cfg.houses[id]) {
    removed.push(id, ...Object.keys(cfg.houses[id].windows || {}).map((w) => `${id}.${w}`));
    delete cfg.houses[id];
  } else if (cfg.groups && cfg.groups[id]) {
    delete cfg.groups[id];
    removed.push(id);
  } else if (cfg.sequences && cfg.sequences[id]) {
    delete cfg.sequences[id];
    removed.push(id);
  } else if (cfg.signals && cfg.signals[id]) {
    delete cfg.signals[id];
    removed.push(id);
  } else if (cfg.special && cfg.special[id]) {
    delete cfg.special[id];
    removed.push(id);
  } else if (cfg.vehicles && cfg.vehicles[id]) {
    delete cfg.vehicles[id];
    removed.push(id);
  } else if (id.includes(".")) {
    const houseId = id.split(".")[0];
    const win = id.slice(houseId.length + 1);
    const house = cfg.houses && cfg.houses[houseId];
    if (house && house.windows && house.windows[win]) {
      delete house.windows[win];
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
    .map(([name, win]) => {
      const anteil = win.channel && win.channel !== "rgb" ? `:${win.channel}` : "";
      return `${name}:${(win.leds || []).join(",")}:${win.color || DEFAULT_COLOR}${anteil}`;
    })
    .join("\n");
}

function parseFensterLines(text) {
  const lines = [];
  for (const raw of String(text || "").split("\n")) {
    const t = raw.trim();
    if (!t) continue;
    const [name, leds, farbe, anteil] = t.split(":");
    if (!name) continue;
    lines.push({ name, leds: leds || "", color: (farbe || DEFAULT_COLOR).trim(), channel: anteil || "rgb" });
  }
  return lines;
}

function fensterLinesToText(lines) {
  return lines.map((win) => `${win.name}:${win.leds}:${win.color}${win.channel && win.channel !== "rgb" ? `:${win.channel}` : ""}`).join("\n");
}

function begriffeToText(begriffe) {
  return Object.entries(begriffe || {})
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([asp, b]) => {
      const leds = Object.entries(b.leds || {}).map(([idx, col]) => {
        const anteil = (b.channels && (b.channels[idx] || b.channels[Number(idx)])) || "rgb";
        return anteil === "rgb" ? `${idx}=${col}` : `${idx}=${col}=${anteil}`;
      }).join(",");
      return `${asp}:${b.name || asp}:${leds}`;
    })
    .join("\n");
}

function loadLamp(id, lamp) {
  $("#l-id").value = id;
  $("#l-ctrl").value = lamp.controller;
  setEditing("lamp", id);
  fillOutputSelect("l-out", lamp.controller);
  if ($("#l-anteil")) $("#l-anteil").value = lamp.channel || "rgb";
  const located = locateLeds(lamp.controller, lamp.leds || []);
  $("#l-out").value = located.outId;
  fillLedSelect("l-leds", lamp.controller, located.outId, "l-anteil");
  selectLocals("l-leds", located.locals);
  setColorInput("l-farbe", lamp.color || DEFAULT_COLOR);
  $("#art-lampe").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadHouse(id, house, windowId) {
  $("#h-id").value = id;
  $("#h-ctrl").value = house.controller;
  setEditing("house", id);
  fillOutputSelect("h-out", house.controller);
  $("#h-mode").value = house.turn_on || "random";
  $("#h-fenster").value = fensterToText(house.windows);
  $("#h-win-name").value = windowId || "";
  editingWindow = windowId || null;
  const win = windowId && house.windows ? house.windows[windowId] : null;
  if (win) {
    const located = locateLeds(house.controller, win.leds || []);
    $("#h-out").value = located.outId;
    if ($("#h-anteil")) $("#h-anteil").value = win.channel || "rgb";
    fillLedSelect("h-leds", house.controller, located.outId, "h-anteil");
    selectLocals("h-leds", located.locals);
    setColorInput("h-win-farbe", win.color || DEFAULT_COLOR);
  } else {
    fillLedSelect("h-leds", house.controller, $("#h-out").value, "h-anteil");
    if ($("#h-anteil")) $("#h-anteil").value = "rgb";
    setColorInput("h-win-farbe", DEFAULT_COLOR);
  }
  $("#art-haus").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadGroup(id, group) {
  $("#g-id").value = id;
  setEditing("group", id);
  fillGroupMemberSelect(group.members || []);
  $("#art-gruppe").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadSequence(id, seq) {
  $("#s-id").value = id;
  $("#s-ord").value = typeof seq.order === "string" ? seq.order : "defined";
  const delay = seq.delay;
  if (Array.isArray(delay) && delay.length >= 2) {
    $("#s-d1").value = durationSeconds(delay[0], 2);
    $("#s-d2").value = durationSeconds(delay[1], 8);
  }
  setEditing("sequence", id);
  fillSequenceGroupSelect(seq.groups || []);
  $("#art-sequenz").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadSignal(id, signal) {
  $("#sig-id").value = id;
  $("#sig-ctrl").value = signal.controller;
  setEditing("signal", id);
  fillOutputSelect("sig-out", signal.controller);
  fillLedSelect("sig-leds", signal.controller, $("#sig-out").value, "sig-anteil");
  $("#sig-asp").value = begriffeToText(signal.aspects);
  $("#sig-asp-n").value = "0";
  $("#sig-asp-name").value = "Halt";
  $("#sig-asp-name").placeholder = "Halt";
  if ($("#sig-anteil")) $("#sig-anteil").value = "rgb";
  setColorInput("sig-farbe", "FF0000");
  $("#art-signal").scrollIntoView({ behavior: "smooth", block: "start" });
}

function loadSpecial(id, spec) {
  $("#sp-id").value = id;
  $("#sp-ctrl").value = spec.controller;
  setEditing("special", id);
  fillOutputSelect("sp-out", spec.controller);
  fillSpecialFx(spec.controller);
  const located = locateLeds(spec.controller, spec.leds || []);
  $("#sp-out").value = located.outId;
  if ($("#sp-anteil")) $("#sp-anteil").value = spec.channel || "rgb";
  fillLedSelect("sp-leds", spec.controller, located.outId, "sp-anteil");
  selectLocals("sp-leds", located.locals);
  setSelectValue($("#sp-fx"), String(spec.effect ?? 0));
  setSelectValue($("#sp-pal"), String(spec.palette ?? 0));
  $("#sp-sx").value = String(spec.speed ?? 128);
  $("#sp-ix").value = String(spec.intensity ?? 128);
  setColorInput("sp-farbe", spec.color || DEFAULT_COLOR);
  $("#art-spezial").scrollIntoView({ behavior: "smooth", block: "start" });
}

function kanaeleToText(kanaele) {
  return Object.entries(kanaele || {})
    .map(([name, ch]) => {
      const base = `${name}:${(ch.leds || []).join(",")}:${ch.channel || "rgb"}:${ch.color || DEFAULT_COLOR}:${ch.type || "continuous"}`;
      return ch.steps && ch.steps !== "auto" ? `${base}:${ch.steps}` : base;
    })
    .join("\n");
}

function parseKanaelLines(text) {
  const lines = [];
  for (const raw of String(text || "").split("\n")) {
    const t = raw.trim();
    if (!t) continue;
    const parts = t.split(":");
    const name = parts[0];
    if (!name) continue;
    lines.push({
      name,
      leds: parts[1] || "",
      channel: parts[2] || "rgb",
      color: (parts[3] || DEFAULT_COLOR).trim(),
      type: parts[4] || "continuous",
      steps: parts[5] || "auto",
    });
  }
  return lines;
}

function kanaelLinesToText(lines) {
  return lines.map((ch) => {
    const base = `${ch.name}:${ch.leds}:${ch.channel}:${ch.color}:${ch.type}`;
    return ch.steps && ch.steps !== "auto" ? `${base}:${ch.steps}` : base;
  }).join("\n");
}

function updateRundumHint() {
  const wrap = $("#v-schritte-wrap");
  const art = $("#v-art") && $("#v-art").value;
  const isRundum = art === "beacon";
  if (wrap) wrap.classList.toggle("hidden", !isRundum);
  const hint = $("#v-rundum-hint");
  if (!hint) return;
  if (!isRundum) {
    hint.textContent = "";
    return;
  }
  const n = selectedLocals("v-leds").length;
  const anteil = ($("#v-anteil") && $("#v-anteil").value) || "rgb";
  const schritte = ($("#v-schritte") && $("#v-schritte").value) || "auto";
  const comps = anteil === "r" || anteil === "g" || anteil === "b" ? 1 : 3;
  if (!n) {
    hint.textContent = t("hint.beacon_ws2811");
    return;
  }
  const walk = schritte === "channels" || (schritte !== "leds" && n === 1 && comps > 1);
  const steps = walk ? n * comps : n;
  hint.textContent = walk
    ? t("hint.beacon_channels", { n: steps })
    : t("hint.beacon_leds", { n: steps });
}

function modiToText(modi) {
  return Object.entries(modi || {})
    .map(([n, m]) => `${n}:${m.name || n}:${(m.channels || []).join(",")}`)
    .join("\n");
}

function parseModiLines(text) {
  const lines = [];
  for (const raw of String(text || "").split("\n")) {
    const t = raw.trim();
    if (!t) continue;
    const [n, name, rest] = t.split(":");
    lines.push({
      n: n || "0",
      name: name || n || "Off",
      channels: (rest || "").split(",").map((s) => s.trim()).filter(Boolean),
    });
  }
  return lines;
}

function modiLinesToText(lines) {
  return lines.map((m) => `${m.n}:${m.name}:${m.channels.join(",")}`).join("\n");
}

function defaultVehicleModi(lines) {
  const dauer = lines.filter((ch) => ch.type === "continuous").map((ch) => ch.name);
  const blinker = lines.filter((ch) => ch.type === "blinker").map((ch) => ch.name);
  const einsatz = lines.filter((ch) => ["beacon", "strobe", "double_strobe"].includes(ch.type)).map((ch) => ch.name);
  const modi = [{ n: "0", name: t("vehicle.mode.off"), channels: [] }];
  let next = 1;
  if (dauer.length) {
    modi.push({ n: String(next++), name: t("vehicle.mode.lights"), channels: [...dauer] });
  }
  if (blinker.length) {
    modi.push({ n: String(next++), name: t("vehicle.mode.hazards"), channels: [...dauer, ...blinker] });
  }
  if (einsatz.length) {
    modi.push({ n: String(next++), name: t("vehicle.mode.emergency"), channels: [...dauer, ...einsatz] });
  }
  if (modi.length === 1 && lines.length) {
    modi.push({ n: "1", name: t("vehicle.mode.on"), channels: lines.map((ch) => ch.name) });
  }
  return modi;
}

function fillVehicleModeChannels(selected) {
  const el = $("#v-mod-kan");
  if (!el) return;
  const keep = selected
    ? new Set(selected.map(String))
    : new Set(selectedValuesOf(el));
  const names = parseKanaelLines($("#v-kanaele") && $("#v-kanaele").value).map((ch) => ch.name);
  if (!names.length) {
    el.innerHTML = `<option value="">${esc(t("veh.channels_empty"))}</option>`;
    el.disabled = true;
    refreshSelectFilter(el);
    return;
  }
  el.disabled = false;
  el.innerHTML = names.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
  [...el.options].forEach((opt) => {
    opt.selected = keep.has(opt.value);
  });
  refreshSelectFilter(el);
}

function loadVehicle(id, vehicle) {
  $("#v-id").value = id;
  $("#v-ctrl").value = vehicle.controller;
  setEditing("vehicle", id);
  fillOutputSelect("v-out", vehicle.controller);
  fillLedSelect("v-leds", vehicle.controller, $("#v-out").value, "v-anteil");
  $("#v-kanaele").value = kanaeleToText(vehicle.channels);
  const modi = vehicle.modi && Object.keys(vehicle.modi).length ? vehicle.modi : null;
  $("#v-modi").value = modi ? modiToText(modi) : modiLinesToText(defaultVehicleModi(parseKanaelLines($("#v-kanaele").value)));
  $("#v-blink").value = String(durationSeconds(vehicle.blink_period, 0.75));
  $("#v-rundum").value = String(durationSeconds(vehicle.beacon_step, 0.12));
  fillVehicleModeChannels();
  $("#v-ch-name").value = "";
  setColorInput("v-farbe", DEFAULT_COLOR);
  if ($("#v-schritte")) $("#v-schritte").value = "auto";
  updateRundumHint();
  $("#art-fahrzeug").scrollIntoView({ behavior: "smooth", block: "start" });
}

function startEdit(id) {
  const obj = (status.objects || []).find((item) => item.id === id);
  let kind = obj && obj.kind;
  let windowId = "";
  if (kind === "window") {
    const houseId = id.split(".")[0];
    windowId = id.slice(houseId.length + 1);
    id = houseId;
    kind = "house";
  }
  showTab("objects");
  if (kind === "lamp" && cfg.lamps && cfg.lamps[id]) return loadLamp(id, cfg.lamps[id]);
  if (kind === "house" && cfg.houses && cfg.houses[id]) return loadHouse(id, cfg.houses[id], windowId);
  if (kind === "group" && cfg.groups && cfg.groups[id]) return loadGroup(id, cfg.groups[id]);
  if (kind === "sequence" && cfg.sequences && cfg.sequences[id]) return loadSequence(id, cfg.sequences[id]);
  if (kind === "signal" && cfg.signals && cfg.signals[id]) return loadSignal(id, cfg.signals[id]);
  if (kind === "special" && cfg.special && cfg.special[id]) return loadSpecial(id, cfg.special[id]);
  if (kind === "vehicle" && cfg.vehicles && cfg.vehicles[id]) return loadVehicle(id, cfg.vehicles[id]);
  notify(t("err.load"), false);
}

function cancelEdit(kind) {
  if (kind === "lamp") {
    $("#l-id").value = "";
    setColorInput("l-farbe", DEFAULT_COLOR);
    if ($("#l-anteil")) $("#l-anteil").value = "rgb";
  } else if (kind === "house") {
    $("#h-id").value = "";
    $("#h-win-name").value = "";
    $("#h-fenster").value = "";
    setColorInput("h-win-farbe", DEFAULT_COLOR);
    if ($("#h-anteil")) $("#h-anteil").value = "rgb";
    editingWindow = null;
  } else if (kind === "group") {
    $("#g-id").value = "";
    fillGroupMemberSelect([]);
  } else if (kind === "sequence") {
    $("#s-id").value = "";
    fillSequenceGroupSelect([]);
    $("#s-d1").value = "2";
    $("#s-d2").value = "8";
  } else if (kind === "signal") {
    $("#sig-id").value = "";
    $("#sig-asp").value = "";
    $("#sig-asp-name").value = "Halt";
    $("#sig-asp-name").placeholder = "Halt";
    setColorInput("sig-farbe", "FF0000");
    const aspN = $("#sig-asp-n");
    if (aspN) aspN.value = "0";
    if ($("#sig-anteil")) $("#sig-anteil").value = "rgb";
  } else if (kind === "special") {
    $("#sp-id").value = "";
    $("#sp-sx").value = "128";
    $("#sp-ix").value = "128";
    setColorInput("sp-farbe", DEFAULT_COLOR);
    if ($("#sp-fx")) { $("#sp-fx").selectedIndex = 0; syncCombo($("#sp-fx")); }
    if ($("#sp-pal")) { $("#sp-pal").selectedIndex = 0; syncCombo($("#sp-pal")); }
    if ($("#sp-anteil")) $("#sp-anteil").value = "rgb";
  } else if (kind === "vehicle") {
    $("#v-id").value = "";
    $("#v-ch-name").value = "";
    $("#v-kanaele").value = "";
    $("#v-modi").value = "";
    $("#v-mod-n").value = "0";
    $("#v-mod-name").value = "";
    $("#v-blink").value = "0.75";
    $("#v-rundum").value = "0.12";
    setColorInput("v-farbe", DEFAULT_COLOR);
    if ($("#v-anteil")) $("#v-anteil").value = "rgb";
    if ($("#v-schritte")) $("#v-schritte").value = "auto";
    fillVehicleModeChannels([]);
    updateRundumHint();
  }
  setEditing(null, null);
}

async function afterSave(kind) {
  cancelEdit(kind);
  await refresh(true);
}

async function deleteListedObject(id) {
  if (!window.confirm(t("confirm.delete_object", { id }))) return;
  await runAction(t("ok.deleted"), async () => {
    const next = await api("/api/config");
    if (!removeObjectFromConfig(next, id)) throw new Error(t("err.object_missing"));
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    const editingId = editing.id;
    const editingKind = editing.kind;
    await refresh();
    if (editingId === id) {
      cancelEdit(editingKind);
    } else if (editingKind === "house" && editingId && id.startsWith(`${editingId}.`) && cfg.houses && cfg.houses[editingId]) {
      loadHouse(editingId, cfg.houses[editingId]);
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
      notify(t("err.address"), false);
      return;
    }
    runAction(t("ok.saved"), async () => {
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

$("#l-cancel").onclick = () => cancelEdit("lamp");
$("#h-cancel").onclick = () => cancelEdit("house");
$("#g-cancel").onclick = () => cancelEdit("group");
$("#s-cancel").onclick = () => cancelEdit("sequence");
$("#sig-cancel").onclick = () => cancelEdit("signal");
$("#sp-cancel").onclick = () => cancelEdit("special");
$("#v-cancel").onclick = () => cancelEdit("vehicle");

$("#l-add").onclick = () => {
  const updating = editing.kind === "lamp" && editing.id;
  runAction(updating ? t("ok.lamp_saved") : t("ok.lamp_created"), async () => {
    const id = $("#l-id").value.trim();
    const leds = toGlobals($("#l-ctrl").value, $("#l-out").value, selectedLocals("l-leds"));
    if (!id) throw new Error(t("err.id"));
    if (!leds.length) throw new Error(t("err.led"));
    const next = await api("/api/config");
    next.lamps = next.lamps || {};
    replaceKey(next.lamps, updating ? editing.id : null, id, {
      controller: $("#l-ctrl").value,
      leds,
      color: parseHex($("#l-farbe").value) || DEFAULT_COLOR,
      channel: $("#l-anteil") ? $("#l-anteil").value || "rgb" : "rgb",
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("lamp");
  });
};

$("#h-win-add").onclick = () => {
  const name = $("#h-win-name").value.trim();
  const leds = toGlobals($("#h-ctrl").value, $("#h-out").value, selectedLocals("h-leds"));
  const farbe = parseHex($("#h-win-farbe").value) || DEFAULT_COLOR;
  const anteil = $("#h-anteil") ? $("#h-anteil").value || "rgb" : "rgb";
  if (!name) {
    notify(t("err.window_name"), false);
    return;
  }
  if (!leds.length) {
    notify(t("err.led"), false);
    return;
  }
  const lines = parseFensterLines($("#h-fenster").value);
  let idx = lines.findIndex((win) => win.name === name);
  if (idx < 0 && editingWindow) idx = lines.findIndex((win) => win.name === editingWindow);
  const existed = idx >= 0;
  runAction(existed ? t("ok.window_updated") : t("ok.window_added"), () => {
    const entry = { name, leds: leds.join(","), color: farbe, channel: anteil };
    if (idx >= 0) lines[idx] = entry;
    else lines.push(entry);
    $("#h-fenster").value = fensterLinesToText(lines);
    editingWindow = null;
  });
};

$("#h-add").onclick = () => {
  const updating = editing.kind === "house" && editing.id;
  runAction(updating ? t("ok.house_saved") : t("ok.house_created"), async () => {
    const id = $("#h-id").value.trim();
    if (!id) throw new Error(t("err.id"));
    const next = await api("/api/config");
    const windows = {};
    for (const line of parseFensterLines($("#h-fenster").value)) {
      windows[line.name] = {
        leds: parseLeds(line.leds || ""),
        color: (line.color || DEFAULT_COLOR).trim(),
        channel: line.channel || "rgb",
      };
    }
    if (!Object.keys(windows).length) throw new Error(t("err.window"));
    next.houses = next.houses || {};
    replaceKey(next.houses, updating ? editing.id : null, id, {
      controller: $("#h-ctrl").value,
      turn_on: $("#h-mode").value,
      windows,
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("house");
  });
};

$("#g-add").onclick = () => {
  const updating = editing.kind === "group" && editing.id;
  runAction(updating ? t("ok.group_saved") : t("ok.group_created"), async () => {
    const id = $("#g-id").value.trim();
    if (!id) throw new Error(t("err.id"));
    const mitglieder = selectedMembers("g-mem");
    if (!mitglieder.length) throw new Error(t("err.member"));
    const next = await api("/api/config");
    next.groups = next.groups || {};
    replaceKey(next.groups, updating ? editing.id : null, id, { members: mitglieder });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("group");
  });
};

$("#s-add").onclick = () => {
  const updating = editing.kind === "sequence" && editing.id;
  runAction(updating ? t("ok.seq_saved") : t("ok.seq_created"), async () => {
    const id = $("#s-id").value.trim();
    if (!id) throw new Error(t("err.id"));
    const gruppen = selectedMembers("s-grp");
    if (!gruppen.length) throw new Error(t("err.group"));
    const minS = durationSeconds($("#s-d1").value, NaN);
    const maxS = durationSeconds($("#s-d2").value, NaN);
    if (!Number.isFinite(minS) || !Number.isFinite(maxS) || minS < 0 || maxS < 0) {
      throw new Error(t("err.pause"));
    }
    const next = await api("/api/config");
    next.sequences = next.sequences || {};
    replaceKey(next.sequences, updating ? editing.id : null, id, {
      groups: gruppen,
      order: $("#s-ord").value,
      delay: [durationToken(minS), durationToken(maxS)],
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("sequence");
  });
};

$("#sig-asp-add").onclick = () => runAction(t("ok.aspect_added"), () => {
  let asp = Number($("#sig-asp-n").value);
  if (!Number.isFinite(asp) || asp < 0) asp = 0;
  const nameField = $("#sig-asp-name");
  const typedName = (nameField.value || "").trim() || (nameField.placeholder || "").trim();
  const anteil = $("#sig-anteil") ? $("#sig-anteil").value || "rgb" : "rgb";
  syncFarbeToAnteil("sig-farbe", anteil);
  const farbe = parseHex($("#sig-farbe").value) || ANTEIL_PRIMARY[anteil] || "FF0000";
  const leds = toGlobals($("#sig-ctrl").value, $("#sig-out").value, selectedLocals("sig-leds"));
  if (!leds.length) throw new Error(t("err.led"));
  const begriffe = parseSignalBegriffe($("#sig-asp").value);
  const byName = typedName
    ? Object.entries(begriffe).find(([, begriff]) => (begriff.name || "") === typedName)
    : null;
  if (byName) {
    asp = Number(byName[0]);
  } else if (begriffe[asp] && typedName && begriffe[asp].name && begriffe[asp].name !== typedName) {
    asp = nextAspectNumber(begriffe);
  }
  const wasNew = !begriffe[asp];
  if (!begriffe[asp]) begriffe[asp] = { name: typedName || String(asp), leds: {}, channels: {} };
  else if (typedName) begriffe[asp].name = typedName;
  for (const idx of leds) {
    begriffe[asp].leds[idx] = farbe;
    if (anteil && anteil !== "rgb") begriffe[asp].channels[idx] = anteil;
    else delete begriffe[asp].channels[idx];
  }
  $("#sig-asp").value = begriffeToText(begriffe);
  if (wasNew) {
    $("#sig-asp-n").value = String(nextAspectNumber(begriffe));
    nameField.value = "";
    nameField.placeholder = "Fahrt";
  } else {
    $("#sig-asp-n").value = String(asp);
  }
});

$("#sig-add").onclick = () => {
  const updating = editing.kind === "signal" && editing.id;
  runAction(updating ? t("ok.signal_saved") : t("ok.signal_created"), async () => {
    const id = $("#sig-id").value.trim();
    if (!id) throw new Error(t("err.id"));
    const next = await api("/api/config");
    const begriffe = compactSignalBegriffe(parseSignalBegriffe($("#sig-asp").value));
    if (!Object.keys(begriffe).length) throw new Error(t("err.aspect"));
    next.signals = next.signals || {};
    replaceKey(next.signals, updating ? editing.id : null, id, { controller: $("#sig-ctrl").value, aspects: begriffe });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("signal");
  });
};

$("#sp-add").onclick = () => {
  const updating = editing.kind === "special" && editing.id;
  runAction(updating ? t("ok.special_saved") : t("ok.special_created"), async () => {
    const id = $("#sp-id").value.trim();
    const leds = toGlobals($("#sp-ctrl").value, $("#sp-out").value, selectedLocals("sp-leds"));
    if (!id) throw new Error(t("err.id"));
    if (!leds.length) throw new Error(t("err.led"));
    const fx = Number($("#sp-fx").value);
    if (!Number.isInteger(fx) || fx < 0) throw new Error(t("err.effect"));
    const pal = Number($("#sp-pal").value);
    const sx = Number($("#sp-sx").value);
    const ix = Number($("#sp-ix").value);
    if (!Number.isInteger(sx) || sx < 0 || sx > 255) throw new Error(t("err.speed"));
    if (!Number.isInteger(ix) || ix < 0 || ix > 255) throw new Error(t("err.intensity"));
    const next = await api("/api/config");
    next.special = next.special || {};
    replaceKey(next.special, updating ? editing.id : null, id, {
      controller: $("#sp-ctrl").value,
      leds,
      effect: fx,
      palette: Number.isInteger(pal) && pal >= 0 ? pal : 0,
      speed: sx,
      intensity: ix,
      color: parseHex($("#sp-farbe").value) || DEFAULT_COLOR,
      channel: $("#sp-anteil") ? $("#sp-anteil").value || "rgb" : "rgb",
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("special");
  });
};

$("#v-kanaele").addEventListener("input", () => fillVehicleModeChannels());

["v-art", "v-schritte"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener("change", updateRundumHint);
    el.addEventListener("input", updateRundumHint);
  }
});

$("#v-ch-add").onclick = () => {
  const name = $("#v-ch-name").value.trim();
  const leds = toGlobals($("#v-ctrl").value, $("#v-out").value, selectedLocals("v-leds"));
  const farbe = parseHex($("#v-farbe").value) || DEFAULT_COLOR;
  const anteil = $("#v-anteil").value || "rgb";
  const art = $("#v-art").value || "continuous";
  const schritte = art === "beacon" ? ($("#v-schritte") && $("#v-schritte").value) || "auto" : "auto";
  if (!name) {
    notify(t("err.channel_name"), false);
    return;
  }
  if (!leds.length) {
    notify(t("err.led"), false);
    return;
  }
  const lines = parseKanaelLines($("#v-kanaele").value);
  const idx = lines.findIndex((ch) => ch.name === name);
  const existed = idx >= 0;
  runAction(existed ? t("ok.channel_updated") : t("ok.channel_added"), () => {
    const entry = { name, leds: leds.join(","), channel: anteil, color: farbe, type: art, steps: schritte };
    if (idx >= 0) lines[idx] = entry;
    else lines.push(entry);
    $("#v-kanaele").value = kanaelLinesToText(lines);
    fillVehicleModeChannels();
  });
};

$("#v-mod-add").onclick = () => {
  const n = $("#v-mod-n").value;
  const name = $("#v-mod-name").value.trim() || String(n);
  const kanaele = selectedMembers("v-mod-kan");
  const lines = parseModiLines($("#v-modi").value);
  const idx = lines.findIndex((m) => String(m.n) === String(n));
  runAction(idx >= 0 ? t("ok.mode_updated") : t("ok.mode_added"), () => {
    const entry = { n: String(n), name, channels: kanaele };
    if (idx >= 0) lines[idx] = entry;
    else lines.push(entry);
    lines.sort((a, b) => Number(a.n) - Number(b.n));
    $("#v-modi").value = modiLinesToText(lines);
  });
};

$("#v-mod-default").onclick = () => {
  const channels = parseKanaelLines($("#v-kanaele").value);
  if (!channels.length) {
    notify(t("err.channels_first"), false);
    return;
  }
  $("#v-modi").value = modiLinesToText(defaultVehicleModi(channels));
  notify(t("ok.modes"), true);
};

$("#v-add").onclick = () => {
  const updating = editing.kind === "vehicle" && editing.id;
  runAction(updating ? t("ok.vehicle_saved") : t("ok.vehicle_created"), async () => {
    const id = $("#v-id").value.trim();
    if (!id) throw new Error(t("err.id"));
    const channels = {};
    for (const line of parseKanaelLines($("#v-kanaele").value)) {
      channels[line.name] = {
        leds: parseLeds(line.leds),
        channel: line.channel || "rgb",
        color: parseHex(line.color) || DEFAULT_COLOR,
        type: line.type || "continuous",
        ...(line.steps && line.steps !== "auto" ? { steps: line.steps } : {}),
      };
    }
    if (!Object.keys(channels).length) throw new Error(t("err.channel"));
    let modiLines = parseModiLines($("#v-modi").value);
    if (!modiLines.length) modiLines = defaultVehicleModi(parseKanaelLines($("#v-kanaele").value));
    const modes = {};
    for (const line of modiLines) {
      modes[Number(line.n)] = { name: line.name, channels: line.channels };
    }
    const blink = durationSeconds($("#v-blink").value, NaN);
    const rundum = durationSeconds($("#v-rundum").value, NaN);
    if (!Number.isFinite(blink) || blink <= 0) throw new Error(t("err.blink"));
    if (!Number.isFinite(rundum) || rundum <= 0) throw new Error(t("err.beacon"));
    const next = await api("/api/config");
    next.vehicles = next.vehicles || {};
    replaceKey(next.vehicles, updating ? editing.id : null, id, {
      controller: $("#v-ctrl").value,
      channels,
      modes,
      blink_period: durationToken(blink),
      beacon_step: durationToken(rundum),
    });
    if (updating) retargetRefs(next, editing.id, id);
    await api("/api/config", { method: "PUT", body: JSON.stringify(next) });
    await afterSave("vehicle");
  });
};

async function loadYaml() {
  const data = await api("/api/config");
  $("#yaml").value = JSON.stringify(data, null, 2);
  $("#yml-err").textContent = "";
}

$("#yml-apply").onclick = () => runAction(t("ok.yaml"), async () => {
  let payload;
  try {
    payload = JSON.parse($("#yaml").value);
  } catch (e) {
    $("#yml-err").textContent = e.message;
    throw new Error(t("err.json"));
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

$("#yml-reload").onclick = () => runAction(t("ok.reload"), async () => {
  await api("/api/reload", { method: "POST" });
  await refresh();
  await loadYaml();
});

initI18n().then(() => {
  FILTER_MULTI_SELECTS.forEach((id) => attachSelectFilter(document.getElementById(id)));
  FILTER_SINGLE_SELECTS.forEach((id) => attachCombo(document.getElementById(id)));
  refresh();
});
setInterval(() => {
  if (!isEditing()) refresh();
}, 4000);
