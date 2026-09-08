"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  step: 1,
  uploadedFiles: [],      // File[]
  members: [],            // string[]
  receiptData: null,      // { items, charges, subtotal, printed_total, currency, math_is_valid, math_notes }
  assignments: {},        // { [itemIndex: number]: Set<memberName> }
  splitResult: null,      // SplitResponse
};

const $ = (id) => document.getElementById(id);

const CURRENCY_SYMBOLS = { USD: "$", INR: "₹", EUR: "€", GBP: "£" };
function symbolFor(code) {
  return CURRENCY_SYMBOLS[code] || (code ? code + " " : "₹");
}
function fmt(amount) {
  const sym = symbolFor(state.receiptData?.currency);
  return `${sym}${Number(amount).toFixed(2)}`;
}

function initials(name) {
  return name.trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("");
}
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Screen navigation
// ---------------------------------------------------------------------------
function goToScreen(n) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(`screen-${n}`).classList.add("active");
  state.step = n;

  document.querySelectorAll(".dot").forEach((dot) => {
    const dotStep = Number(dot.dataset.step);
    dot.classList.toggle("active", dotStep === n);
    dot.classList.toggle("done", dotStep < n);
  });

  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.querySelectorAll("[data-back]").forEach((btn) => {
  btn.addEventListener("click", () => goToScreen(Number(btn.dataset.back)));
});

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
let toastEl = null;
function showToast(message) {
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.className = "toast";
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = message;
  toastEl.classList.add("visible");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toastEl.classList.remove("visible"), 2200);
}

// ===========================================================================
// SCREEN 1: Upload & Roster
// ===========================================================================
const dropzone = $("dropzone");
const fileInput = $("file-input");
const previewStrip = $("preview-strip");
const dropzoneEmpty = $("dropzone-empty");
const memberInput = $("member-input");
const memberTags = $("member-tags");
const scanBtn = $("scan-btn");
const scanBtnText = $("scan-btn-text");
const scanSpinner = $("scan-spinner");
const screen1Error = $("screen1-error");

dropzone.addEventListener("click", (e) => {
  if (e.target.closest(".remove-photo-btn")) return;
  fileInput.click();
});

["dragover", "dragenter"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  })
);
["dragleave", "dragend"].forEach((evt) =>
  dropzone.addEventListener(evt, () => dropzone.classList.remove("drag-over"))
);
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
});

fileInput.addEventListener("change", () => {
  addFiles(fileInput.files);
  fileInput.value = "";
});

function addFiles(fileList) {
  state.uploadedFiles.push(...Array.from(fileList));
  renderPreviewStrip();
  updateScanButtonState();
}

function removePhotoAt(index) {
  state.uploadedFiles.splice(index, 1);
  renderPreviewStrip();
  updateScanButtonState();
}

function renderPreviewStrip() {
  previewStrip.innerHTML = "";
  if (state.uploadedFiles.length === 0) {
    dropzoneEmpty.classList.remove("hidden");
    previewStrip.classList.add("hidden");
    return;
  }
  dropzoneEmpty.classList.add("hidden");
  previewStrip.classList.remove("hidden");

  state.uploadedFiles.forEach((file, idx) => {
    const wrap = document.createElement("div");
    wrap.className = "preview-thumb";

    const reader = new FileReader();
    reader.onload = (e) => {
      const img = document.createElement("img");
      img.src = e.target.result;
      wrap.prepend(img);
    };
    reader.readAsDataURL(file);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-photo-btn";
    removeBtn.setAttribute("aria-label", `Remove photo ${idx + 1}`);
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      removePhotoAt(idx);
    });

    wrap.appendChild(removeBtn);
    previewStrip.appendChild(wrap);
  });
}

memberInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const name = memberInput.value.trim();
  if (!name) return;
  if (state.members.some((m) => m.toLowerCase() === name.toLowerCase())) {
    memberInput.value = "";
    return;
  }
  state.members.push(name);
  memberInput.value = "";
  renderMemberTags();
  updateScanButtonState();
});

function renderMemberTags() {
  memberTags.innerHTML = "";
  state.members.forEach((name, idx) => {
    const tag = document.createElement("div");
    tag.className = "tag";
    tag.innerHTML = `
      <span class="avatar">${initials(name)}</span>
      <span>${escapeHtml(name)}</span>
      <button type="button" aria-label="Remove ${escapeHtml(name)}">&times;</button>
    `;
    tag.querySelector("button").addEventListener("click", () => {
      state.members.splice(idx, 1);
      renderMemberTags();
      updateScanButtonState();
    });
    memberTags.appendChild(tag);
  });
}

function updateScanButtonState() {
  scanBtn.disabled = !(state.uploadedFiles.length > 0 && state.members.length > 0);
}

scanBtn.addEventListener("click", async () => {
  screen1Error.textContent = "";
  setScanLoading(true);

  const formData = new FormData();
  state.uploadedFiles.forEach((file) => formData.append("files", file));

  try {
    const res = await fetch("/api/upload-receipt", { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to scan receipt");
    }
    state.receiptData = await res.json();
    populateScreen2();
    goToScreen(2);
  } catch (e) {
    screen1Error.textContent = e.message;
  } finally {
    setScanLoading(false);
  }
});

function setScanLoading(isLoading) {
  scanBtn.disabled = isLoading || !(state.uploadedFiles.length > 0 && state.members.length > 0);
  scanSpinner.classList.toggle("hidden", !isLoading);
  scanBtnText.textContent = isLoading ? "Scanning..." : "Scan Bill";
}

// ===========================================================================
// SCREEN 2: OCR Verification & Review
// ===========================================================================
const receiptPreviewImg = $("receipt-preview-img");
const mathAlert = $("math-alert");
const mathAlertText = $("math-alert-text");
const currencySelect = $("currency-select");
const itemsTbody = $("items-tbody");
const addItemBtn = $("add-item-btn");
const chargesList = $("charges-list");
const addChargeBtn = $("add-charge-btn");
const inputSubtotal = $("input-subtotal");
const inputPrintedTotal = $("input-printed-total");
const computedTotalEl = $("computed-total");
const reviewReconciliation = $("review-reconciliation");
const reviewReconciliationText = $("review-reconciliation-text");
const autoBalanceBtn = $("auto-balance-btn");
const toScreen3Btn = $("to-screen-3-btn");

const CONFIDENCE_THRESHOLD = 0.85;
const TOLERANCE = 0.05;

function populateScreen2() {
  if (state.uploadedFiles[0]) {
    const reader = new FileReader();
    reader.onload = (e) => (receiptPreviewImg.src = e.target.result);
    reader.readAsDataURL(state.uploadedFiles[0]);
  }

  currencySelect.value = state.receiptData.currency || "INR";
  currencySelect.addEventListener("change", () => {
    state.receiptData.currency = currencySelect.value;
    recomputeAll();
  });

  inputSubtotal.value = state.receiptData.subtotal;
  inputSubtotal.addEventListener("input", () => {
    state.receiptData.subtotal = parseFloat(inputSubtotal.value) || 0;
    recomputeAll();
  });

  inputPrintedTotal.value = state.receiptData.printed_total;
  inputPrintedTotal.addEventListener("input", () => {
    state.receiptData.printed_total = parseFloat(inputPrintedTotal.value) || 0;
    recomputeAll();
  });

  autoBalanceBtn.addEventListener("click", () => {
    const { computedTotal } = computeTotals();
    const diff = round2(state.receiptData.printed_total - computedTotal);
    if (Math.abs(diff) < 0.01) return;

    state.receiptData.charges.push({
      label: "Adjustment",
      charge_type: diff > 0 ? "tax" : "discount",
      category: null,
      amount: Math.abs(diff),
    });
    renderChargesList();
    recomputeAll();
  });

  renderItemsTable();
  renderChargesList();
  recomputeAll();
}

function round2(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}

function computeTotals() {
  const itemsSum = state.receiptData.items.reduce((acc, i) => acc + (Number(i.price) || 0), 0);
  let chargesSum = 0;
  state.receiptData.charges.forEach((c) => {
    const amt = Number(c.amount) || 0;
    chargesSum += c.charge_type === "discount" ? -amt : amt;
  });
  const computedTotal = (Number(state.receiptData.subtotal) || 0) + chargesSum;
  return { itemsSum, chargesSum, computedTotal };
}

function recomputeAll() {
  const { itemsSum, computedTotal } = computeTotals();

  const subtotalDeviation = Math.abs(itemsSum - (Number(state.receiptData.subtotal) || 0));
  if (subtotalDeviation > TOLERANCE) {
    state.receiptData.math_is_valid = false;
    state.receiptData.math_notes = `Line items sum to ${itemsSum.toFixed(2)}, but subtotal is set to ${Number(
      state.receiptData.subtotal
    ).toFixed(2)} (off by ${subtotalDeviation.toFixed(2)}).`;
  } else {
    state.receiptData.math_is_valid = true;
    state.receiptData.math_notes = null;
  }
  mathAlert.classList.toggle("hidden", state.receiptData.math_is_valid !== false);
  if (state.receiptData.math_is_valid === false) {
    mathAlertText.textContent = state.receiptData.math_notes;
  }

  computedTotalEl.textContent = fmt(computedTotal);
  const printedTotal = Number(state.receiptData.printed_total) || 0;
  const totalDeviation = Math.abs(computedTotal - printedTotal);

  if (totalDeviation > TOLERANCE) {
    reviewReconciliation.classList.remove("hidden");
    const diff = round2(printedTotal - computedTotal);
    reviewReconciliationText.textContent =
      diff > 0
        ? `Computed total is ${fmt(Math.abs(diff))} short of the printed total.`
        : `Computed total is ${fmt(Math.abs(diff))} over the printed total.`;
  } else {
    reviewReconciliation.classList.add("hidden");
  }
}

function renderItemsTable() {
  itemsTbody.innerHTML = "";
  state.receiptData.items.forEach((item, idx) => {
    const tr = document.createElement("tr");
    const lowConfidence = item.confidence < CONFIDENCE_THRESHOLD;
    const badge = lowConfidence
      ? `<span class="confidence-badge">⚠ ${(item.confidence * 100).toFixed(0)}%</span>`
      : "";

    tr.innerHTML = `
      <td>
        <input type="text" class="item-name-input" value="${escapeHtml(item.name)}" />
        ${badge}
      </td>
      <td><input type="text" class="item-category-input" value="${escapeHtml(item.category || "Uncategorized")}" /></td>
      <td><input type="number" min="1" step="1" class="item-qty-input" value="${item.quantity}" /></td>
      <td><input type="number" step="0.01" class="item-price-input" value="${item.price}" /></td>
      <td><button type="button" class="remove-item-btn" aria-label="Remove item">&times;</button></td>
    `;

    tr.querySelector(".item-name-input").addEventListener("input", (e) => (item.name = e.target.value));
    tr.querySelector(".item-category-input").addEventListener(
      "input",
      (e) => (item.category = e.target.value || "Uncategorized")
    );
    tr.querySelector(".item-qty-input").addEventListener(
      "input",
      (e) => (item.quantity = parseInt(e.target.value, 10) || 1)
    );
    tr.querySelector(".item-price-input").addEventListener("input", (e) => {
      item.price = parseFloat(e.target.value) || 0;
      recomputeAll();
    });
    tr.querySelector(".remove-item-btn").addEventListener("click", () => {
      state.receiptData.items.splice(idx, 1);
      renderItemsTable();
      recomputeAll();
    });

    itemsTbody.appendChild(tr);
  });
}

addItemBtn.addEventListener("click", () => {
  state.receiptData.items.push({ name: "", category: "Uncategorized", quantity: 1, price: 0, confidence: 1.0 });
  renderItemsTable();
  recomputeAll();
});

function renderChargesList() {
  chargesList.innerHTML = "";
  state.receiptData.charges.forEach((charge, idx) => {
    const row = document.createElement("div");
    row.className = "charge-row";
    row.innerHTML = `
      <input type="text" class="charge-label-input" placeholder="Label (e.g. Food Tax)" value="${escapeHtml(charge.label)}" />
      <select class="charge-type-select">
        <option value="tax" ${charge.charge_type === "tax" ? "selected" : ""}>Tax</option>
        <option value="service_charge" ${charge.charge_type === "service_charge" ? "selected" : ""}>Service charge</option>
        <option value="discount" ${charge.charge_type === "discount" ? "selected" : ""}>Discount</option>
      </select>
      <input type="text" class="charge-category-input" placeholder="Category (blank = whole bill)" value="${charge.category ?? ""}" />
      <input type="number" step="0.01" class="charge-amount-input" value="${charge.amount}" />
      <button type="button" class="remove-item-btn" aria-label="Remove charge">&times;</button>
    `;

    row.querySelector(".charge-label-input").addEventListener("input", (e) => (charge.label = e.target.value));
    row.querySelector(".charge-type-select").addEventListener("change", (e) => {
      charge.charge_type = e.target.value;
      recomputeAll();
    });
    row.querySelector(".charge-category-input").addEventListener(
      "input",
      (e) => (charge.category = e.target.value.trim() === "" ? null : e.target.value.trim())
    );
    row.querySelector(".charge-amount-input").addEventListener("input", (e) => {
      charge.amount = parseFloat(e.target.value) || 0;
      recomputeAll();
    });
    row.querySelector(".remove-item-btn").addEventListener("click", () => {
      state.receiptData.charges.splice(idx, 1);
      renderChargesList();
      recomputeAll();
    });

    chargesList.appendChild(row);
  });
}

addChargeBtn.addEventListener("click", () => {
  state.receiptData.charges.push({ label: "", charge_type: "tax", category: null, amount: 0 });
  renderChargesList();
  recomputeAll();
});

toScreen3Btn.addEventListener("click", () => {
  buildInitialAssignments();
  renderScreen3();
  goToScreen(3);
});

// ===========================================================================
// SCREEN 3: Assignment Matrix
// ===========================================================================
const screen3MemberInput = $("screen3-member-input");
const memberPillRow = $("member-pill-row");
const assignmentCardsEl = $("assignment-cards");
const calculateBtn = $("calculate-btn");
const screen3Error = $("screen3-error");

function buildInitialAssignments() {
  state.receiptData.items.forEach((_, idx) => {
    if (!state.assignments[idx]) state.assignments[idx] = new Set();
  });
}

screen3MemberInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const name = screen3MemberInput.value.trim();
  if (!name) return;
  if (state.members.some((m) => m.toLowerCase() === name.toLowerCase())) {
    screen3MemberInput.value = "";
    return;
  }
  state.members.push(name);
  screen3MemberInput.value = "";
  renderScreen3();
});

function removeMember(name) {
  state.members = state.members.filter((m) => m !== name);
  Object.values(state.assignments).forEach((memberSet) => memberSet.delete(name));
  renderScreen3();
}

function renderScreen3() {
  memberPillRow.innerHTML = "";
  state.members.forEach((name) => {
    const pill = document.createElement("div");
    pill.className = "member-pill";
    pill.innerHTML = `
      <span class="avatar">${initials(name)}</span>
      <span>${escapeHtml(name)}</span>
      <button type="button" class="remove-member-btn" aria-label="Remove ${escapeHtml(name)}">&times;</button>
    `;
    pill.querySelector(".remove-member-btn").addEventListener("click", () => removeMember(name));
    memberPillRow.appendChild(pill);
  });

  assignmentCardsEl.innerHTML = "";
  state.receiptData.items.forEach((item, idx) => {
    const card = document.createElement("div");
    card.className = "assignment-card";
    card.innerHTML = `
      <div class="assignment-card-head">
        <span class="item-name">${escapeHtml(item.name || "(unnamed item)")} <span class="category-badge">${escapeHtml(item.category || "Uncategorized")}</span></span>
        <span class="item-price">${fmt(item.price)}</span>
      </div>
      <div class="avatar-toggle-row" data-item-index="${idx}"></div>
      <button type="button" class="split-all-btn">Split With All</button>
    `;

    const toggleRow = card.querySelector(".avatar-toggle-row");
    state.members.forEach((name) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "avatar-toggle";
      btn.textContent = initials(name);
      btn.title = name;
      if (state.assignments[idx].has(name)) btn.classList.add("selected");

      btn.addEventListener("click", () => {
        if (state.assignments[idx].has(name)) state.assignments[idx].delete(name);
        else state.assignments[idx].add(name);
        btn.classList.toggle("selected");
      });

      toggleRow.appendChild(btn);
    });

    card.querySelector(".split-all-btn").addEventListener("click", () => {
      state.assignments[idx] = new Set(state.members);
      renderScreen3();
    });

    assignmentCardsEl.appendChild(card);
  });
}

calculateBtn.addEventListener("click", async () => {
  screen3Error.textContent = "";

  const assignmentsPayload = [];
  for (const [idxStr, memberSet] of Object.entries(state.assignments)) {
    if (memberSet.size === 0) continue;
    assignmentsPayload.push({ item_index: Number(idxStr), assigned_members: Array.from(memberSet) });
  }

  const unassignedCount = state.receiptData.items.length - assignmentsPayload.length;
  if (unassignedCount > 0) {
    screen3Error.textContent = `${unassignedCount} item(s) have no one assigned. Assign everyone before continuing.`;
    return;
  }

  const payload = { receipt_data: state.receiptData, members: state.members, assignments: assignmentsPayload };

  calculateBtn.disabled = true;
  try {
    const res = await fetch("/api/calculate-split", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to calculate split");
    }
    state.splitResult = await res.json();
    renderScreen4();
    goToScreen(4);
  } catch (e) {
    screen3Error.textContent = e.message;
  } finally {
    calculateBtn.disabled = false;
  }
});

// ===========================================================================
// SCREEN 4: Final Settlement Breakdown
// ===========================================================================
const memberSummaryCards = $("member-summary-cards");
const breakdownTableBody = $("breakdownTableBody");
const grandTotalDisplay = $("grandTotalDisplay");
const reconciliationNote = $("reconciliation-note");
const copyWhatsappBtn = $("copy-whatsapp-btn");
const startOverBtn = $("start-over-btn");

const CHARGE_GROUP_LABELS = { tax: "Taxes", service_charge: "Service charges", discount: "Discounts" };

function renderScreen4() {
  const { member_breakdowns, table_subtotal, table_total, reconciliation_difference } = state.splitResult;

  memberSummaryCards.innerHTML = "";
  breakdownTableBody.innerHTML = "";

  let overallFinalSum = 0;

  member_breakdowns.forEach((mb) => {
    // 1. Render Member Accordion Cards
    const itemRows = mb.assigned_items
      .map(
        (it) =>
          `<div class="row"><span>${escapeHtml(it.name)} (÷${it.split_between})</span><span>${fmt(it.share_amount)}</span></div>`
      )
      .join("");

    const categoryRows = Object.entries(mb.category_subtotals)
      .map(([cat, amt]) => `<div class="row"><span>${escapeHtml(cat)}</span><span>${fmt(amt)}</span></div>`)
      .join("");

    const grouped = { tax: [], service_charge: [], discount: [] };
    mb.charge_shares.forEach((cs) => {
      (grouped[cs.charge_type] || grouped.tax).push(cs);
    });

    let memberTaxTotal = 0;
    let memberServiceChargeTotal = 0;

    mb.charge_shares.forEach(cs => {
      if (cs.charge_type === 'tax') memberTaxTotal += cs.amount;
      if (cs.charge_type === 'service_charge') memberServiceChargeTotal += cs.amount;
    });

    const chargeGroupsHtml = Object.entries(grouped)
      .filter(([, list]) => list.length > 0)
      .map(([type, list]) => {
        const rows = list
          .map((cs) => {
            const sign = type === "discount" ? "-" : "";
            const scope = cs.category ? ` (${escapeHtml(cs.category)})` : "";
            return `<div class="row"><span>${escapeHtml(cs.label)}${scope}</span><span>${sign}${fmt(Math.abs(cs.amount))}</span></div>`;
          })
          .join("");
        return `<div class="charge-type-group"><strong>${CHARGE_GROUP_LABELS[type]}</strong>${rows}</div>`;
      })
      .join("");

    const card = document.createElement("div");
    card.className = "summary-card";
    card.innerHTML = `
      <div class="summary-card-head">
        <span class="name"><span class="avatar" style="width:24px;height:24px;border-radius:50%;background:var(--accent);display:inline-flex;align-items:center;justify-content:center;font-size:10px;color:#fff;">${initials(
          mb.member_name
        )}</span> ${escapeHtml(mb.member_name)}</span>
        <span class="owed">${fmt(mb.total_owed)}</span>
      </div>
      <div class="summary-card-detail">
        <strong>Items consumed</strong>
        ${itemRows}
        <div class="row"><span>Food/item subtotal</span><span>${fmt(mb.individual_subtotal)}</span></div>
        <strong>By category</strong>
        ${categoryRows || '<div class="row"><span>—</span><span></span></div>'}
        ${chargeGroupsHtml}
        <div class="row" style="margin-top:6px;border-top:1px dashed var(--paper-shade);padding-top:6px;">
          <span><strong style="display:inline;margin:0;">Total owed</strong></span><span>${fmt(mb.total_owed)}</span>
        </div>
      </div>
    `;
    card.addEventListener("click", () => card.classList.toggle("expanded"));
    memberSummaryCards.appendChild(card);

    // 2. Render Row in the Detailed Summary Table
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(mb.member_name)}</strong></td>
      <td>${fmt(mb.individual_subtotal)}</td>
      <td>${fmt(memberServiceChargeTotal)}</td>
      <td>${fmt(memberTaxTotal)}</td>
      <td><strong>${fmt(mb.total_owed)}</strong></td>
    `;
    breakdownTableBody.appendChild(tr);

    overallFinalSum += mb.total_owed;
  });

  grandTotalDisplay.textContent = `Total: ${fmt(overallFinalSum)}`;

  reconciliationNote.textContent =
    Math.abs(reconciliation_difference) > 0.01
      ? `Table total ${fmt(table_total)} vs printed total (diff ${fmt(reconciliation_difference)})`
      : `Table subtotal ${fmt(table_subtotal)} · Total ${fmt(table_total)} — reconciled ✓`;
}

copyWhatsappBtn.addEventListener("click", async () => {
  const text = buildWhatsAppMessage();
  try {
    await navigator.clipboard.writeText(text);
    showToast("Copied to clipboard!");
  } catch {
    showToast("Could not copy — select and copy manually.");
  }
});

function buildWhatsAppMessage() {
  const { member_breakdowns, table_total } = state.splitResult;
  const lines = ["*🧾 FairSplit-AI Bill Summary*", ""];
  member_breakdowns.forEach((mb) => lines.push(`• *${mb.member_name}*: ${fmt(mb.total_owed)}`));
  lines.push("", `*Total: ${fmt(table_total)}*`);
  return lines.join("\n");
}

startOverBtn.addEventListener("click", () => {
  state.uploadedFiles = [];
  state.members = [];
  state.receiptData = null;
  state.assignments = {};
  state.splitResult = null;

  fileInput.value = "";
  memberInput.value = "";
  renderPreviewStrip();
  renderMemberTags();
  updateScanButtonState();
  screen1Error.textContent = "";

  goToScreen(1);
});