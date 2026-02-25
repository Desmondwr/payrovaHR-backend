const state = {
  baseUrl: "",
  employerToken: "",
  employeeToken: "",
  employerId: "",
  mode: "employer",
  cache: {
    subscriptions: [],
    invoices: [],
    payouts: [],
  },
};

const $ = (id) => document.getElementById(id);

function loadConfig() {
  const saved = JSON.parse(localStorage.getItem("billingConfig") || "{}");
  state.baseUrl = saved.baseUrl || "http://127.0.0.1:8000/api";
  state.employerToken = saved.employerToken || "";
  state.employeeToken = saved.employeeToken || "";
  state.employerId = saved.employerId || "";
  $("baseUrl").value = state.baseUrl;
  $("employerToken").value = state.employerToken;
  $("employeeToken").value = state.employeeToken;
  $("employerId").value = state.employerId;
}

function saveConfig() {
  state.baseUrl = $("baseUrl").value.trim();
  state.employerToken = $("employerToken").value.trim();
  state.employeeToken = $("employeeToken").value.trim();
  state.employerId = $("employerId").value.trim();
  localStorage.setItem("billingConfig", JSON.stringify(state));
  showToast("Configuration saved", "success");
}

function buildUrl(path) {
  const root = state.baseUrl.replace(/\/$/, "");
  return `${root}${path}`;
}

function activeToken() {
  if (state.mode === "employer") {
    return state.employerToken;
  }
  return state.employeeToken || state.employerToken;
}

function headers({ includeEmployer = false } = {}) {
  const hdrs = { "Content-Type": "application/json" };
  const token = activeToken();
  if (token) {
    hdrs.Authorization = `Bearer ${token.replace("Bearer ", "")}`;
  }
  if (includeEmployer && state.employerId) {
    hdrs["X-Employer-Id"] = state.employerId;
  }
  return hdrs;
}

function showToast(message, type = "info") {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toast.className = "toast";
  }, 2500);
}

function getMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload.message === "string" && payload.message) return payload.message;
  if (typeof payload.detail === "string" && payload.detail) return payload.detail;
  if (payload.errors) return JSON.stringify(payload.errors);
  return fallback;
}

async function apiRequest(path, options = {}) {
  const { method = "GET", body, includeEmployer = false } = options;
  const config = {
    method,
    headers: headers({ includeEmployer }),
  };
  if (body) {
    config.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(buildUrl(path), config);
  } catch (err) {
    showToast("Network error. Check your connection.", "error");
    return { ok: false, data: null };
  }

  let data = null;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await res.json();
  }

  const ok = data && typeof data.success === "boolean" ? data.success : res.ok;
  if (!ok) {
    showToast(getMessage(data, "Request failed"), "error");
  } else if (method !== "GET" && data && data.message) {
    showToast(data.message, "success");
  }

  return { ok, data, res };
}

function unwrapData(payload) {
  if (!payload) return payload;
  if (payload.data !== undefined) return payload.data;
  return payload;
}

function extractList(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (payload.results) return payload.results;
  if (payload.data) {
    if (Array.isArray(payload.data)) return payload.data;
    if (payload.data.results) return payload.data.results;
  }
  return [];
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function statusPill(status) {
  const upper = String(status || "UNKNOWN").toUpperCase();
  const toneMap = {
    ACTIVE: "success",
    INACTIVE: "warning",
    INVALID: "danger",
    TRIALING: "info",
    PAST_DUE: "warning",
    PAUSED: "warning",
    CANCELED: "danger",
    ISSUED: "warning",
    PAID: "success",
    FAILED: "danger",
    PENDING: "warning",
    PROCESSING: "warning",
    COMPLETED: "success",
    PARTIAL: "warning",
    SUCCESS: "success",
    REVERSED: "info",
    DRAFT: "info",
  };
  const tone = toneMap[upper] || "info";
  return `<span class="pill" data-tone="${tone}">${escapeHtml(upper)}</span>`;
}

function formatMoney(amount, currency) {
  const value = amount !== undefined && amount !== null ? amount : "0.00";
  const money = typeof value === "number" ? value.toFixed(2) : value;
  return `${money} ${currency || ""}`.trim();
}

function formatDate(value) {
  if (!value) return "n/a";
  return value;
}

function renderList(containerId, items, formatter, emptyMessage = "No data") {
  const el = $(containerId);
  if (!el) return;
  if (!items.length) {
    el.innerHTML = `<div class="list-item">${escapeHtml(emptyMessage)}</div>`;
    return;
  }
  el.innerHTML = items.map((item) => `<div class="list-item">${formatter(item)}</div>`).join("");
}

function updateStats() {
  const subscriptions = state.cache.subscriptions || [];
  const invoices = state.cache.invoices || [];
  const payouts = state.cache.payouts || [];

  const active = subscriptions.find((sub) =>
    ["ACTIVE", "TRIALING", "PAST_DUE"].includes(String(sub.status || "").toUpperCase())
  );
  $("statPlan").textContent = active ? active.plan_detail?.name || active.plan || "Active" : "No active plan";
  $("statNext").textContent = active ? formatDate(active.next_billing_date) : "Not scheduled";

  const openInvoices = invoices.filter((inv) =>
    ["ISSUED", "FAILED"].includes(String(inv.status || "").toUpperCase())
  );
  $("statInvoices").textContent = String(openInvoices.length);

  const pending = payouts.filter((pay) =>
    ["PENDING", "PROCESSING"].includes(String(pay.status || "").toUpperCase())
  );
  const total = pending.reduce((sum, item) => sum + parseFloat(item.amount || 0), 0);
  const currency = pending[0]?.currency || "";
  $("statPayroll").textContent = `${total.toFixed(2)} ${currency}`.trim();
}

async function refreshGbpayConnections() {
  const result = await apiRequest("/billing/gbpay-connections/", { includeEmployer: true });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  renderList("gbpayList", items, (item) => {
    const statusValue = String(item.status || "").toUpperCase();
    const isActive = !!item.is_active;
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.label || "GbPay connection")}</p>
        ${statusPill(statusValue)}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(item.environment || "")}</span>
        <span>${escapeHtml(item.credentials_hint || "No hint")}</span>
        <span>${escapeHtml(item.last_validated_at || "Not validated")}</span>
      </div>
      <div class="item-actions">
        <button class="btn ghost small" data-action="test-gbpay" data-id="${escapeHtml(item.id)}">Test</button>
        ${!isActive ? `<button class="btn small" data-action="enable-gbpay" data-id="${escapeHtml(item.id)}">Enable</button>` : ""}
        ${isActive ? `<button class="btn neutral small" data-action="disable-gbpay" data-id="${escapeHtml(item.id)}">Disable</button>` : ""}
      </div>
    `;
  }, "No GbPay connections yet.");
}

async function refreshFunding() {
  const result = await apiRequest("/billing/funding-methods/", { includeEmployer: true });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  renderList("fundingList", items, (item) => {
    const defaults = [];
    if (item.is_default_subscription) defaults.push("Subscription default");
    if (item.is_default_payroll) defaults.push("Payroll default");
    const defaultText = defaults.length ? defaults.join(", ") : "Not default";
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.label || item.method_type || "Funding method")}</p>
        ${statusPill(item.verification_status || "UNVERIFIED")}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(item.method_type || "")}</span>
        <span>${escapeHtml(item.provider || "No provider")}</span>
        <span>${escapeHtml(item.currency || "")}</span>
        <span>${escapeHtml(defaultText)}</span>
      </div>
      <div class="item-actions">
        <button class="btn ghost small" data-action="set-default-subscription" data-id="${escapeHtml(item.id)}">Set subscription default</button>
        <button class="btn ghost small" data-action="set-default-payroll" data-id="${escapeHtml(item.id)}">Set payroll default</button>
      </div>
    `;
  }, "No funding methods yet.");
}

async function refreshSubscriptions() {
  const result = await apiRequest("/billing/subscriptions/", { includeEmployer: true });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  state.cache.subscriptions = items;
  updateStats();
  renderList("subscriptionList", items, (item) => {
    const planName = item.plan_detail?.name || item.plan || "Plan";
    const nextBilling = formatDate(item.next_billing_date);
    const status = String(item.status || "").toUpperCase();
    const showCancel = status !== "CANCELED";
    const showResume = status === "PAUSED" || status === "CANCELED";
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(planName)}</p>
        ${statusPill(status)}
      </div>
      <div class="item-meta">
        <span>Next billing: ${escapeHtml(nextBilling)}</span>
        <span>${item.auto_renew ? "Auto renew" : "Manual renew"}</span>
      </div>
      <div class="item-actions">
        <button class="btn ghost small" data-action="issue-invoice" data-id="${escapeHtml(item.id)}">Issue invoice</button>
        ${showCancel ? `<button class="btn neutral small" data-action="cancel-subscription" data-id="${escapeHtml(item.id)}">Cancel</button>` : ""}
        ${showResume ? `<button class="btn small" data-action="resume-subscription" data-id="${escapeHtml(item.id)}">Resume</button>` : ""}
      </div>
    `;
  }, "No subscriptions yet.");
}

async function refreshInvoices() {
  const result = await apiRequest("/billing/invoices/", { includeEmployer: true });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  state.cache.invoices = items;
  updateStats();
  renderList("invoiceList", items, (item) => {
    const period = item.period_start && item.period_end ? `${item.period_start} to ${item.period_end}` : "Period not set";
    const status = String(item.status || "").toUpperCase();
    const markable = status === "ISSUED";
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.number || "Invoice")}</p>
        ${statusPill(status)}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(period)}</span>
        <span>${escapeHtml(formatMoney(item.total_amount, item.currency))}</span>
      </div>
      <div class="item-actions">
        <button class="btn ghost small" data-action="download-invoice" data-id="${escapeHtml(item.id)}" data-number="${escapeHtml(item.number)}">Download PDF</button>
        ${markable ? `<button class="btn small" data-action="mark-invoice-paid" data-id="${escapeHtml(item.id)}">Mark paid</button>` : ""}
        ${markable ? `<button class="btn danger small" data-action="mark-invoice-failed" data-id="${escapeHtml(item.id)}">Mark failed</button>` : ""}
      </div>
    `;
  }, "No invoices yet.");
}

async function refreshTransactions() {
  const category = $("txnCategory").value;
  const status = $("txnStatus").value;
  const direction = $("txnDirection").value;
  const params = new URLSearchParams();
  if (category) params.append("category", category);
  if (status) params.append("status", status);
  if (direction) params.append("direction", direction);

  const result = await apiRequest(`/billing/transactions/?${params.toString()}`, { includeEmployer: true });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  renderList("transactionList", items, (item) => {
    const statusValue = String(item.status || "").toUpperCase();
    const canRefund = statusValue === "SUCCESS" && String(item.category || "").toUpperCase() !== "REFUND";
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.category || "Transaction")}</p>
        ${statusPill(statusValue)}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(item.direction || "")}</span>
        <span>${escapeHtml(formatMoney(item.amount, item.currency))}</span>
        <span>${escapeHtml(item.description || "")}</span>
      </div>
      <div class="item-actions">
        ${canRefund ? `<button class="btn warn small" data-action="refund-transaction" data-id="${escapeHtml(item.id)}">Refund</button>` : ""}
      </div>
    `;
  }, "No transactions yet.");
}

async function refreshPayouts() {
  const result = await apiRequest("/billing/payouts/", { includeEmployer: true });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  state.cache.payouts = items;
  updateStats();
  renderList("payoutList", items, (item) => {
    const statusValue = String(item.status || "").toUpperCase();
    const showUpdate = ["PENDING", "PROCESSING"].includes(statusValue);
    const showReverse = statusValue === "PAID";
    const canExecute = statusValue === "PENDING";
    const canRetry = statusValue === "FAILED";
    const canReceipt = statusValue === "PAID";
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.employee_name || "Employee")}</p>
        ${statusPill(statusValue)}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(item.category || "")}</span>
        <span>${escapeHtml(formatMoney(item.amount, item.currency))}</span>
        <span>${escapeHtml(item.provider_reference || "No provider ref")}</span>
      </div>
      <div class="item-actions">
        ${canExecute ? `<button class="btn small" data-action="execute-payout" data-id="${escapeHtml(item.id)}">Execute</button>` : ""}
        ${canRetry ? `<button class="btn warn small" data-action="retry-payout" data-id="${escapeHtml(item.id)}">Retry</button>` : ""}
        ${canReceipt ? `<button class="btn ghost small" data-action="download-receipt" data-id="${escapeHtml(item.id)}">Receipt</button>` : ""}
        ${showUpdate ? `<button class="btn small" data-action="mark-payout-paid" data-id="${escapeHtml(item.id)}">Mark paid</button>` : ""}
        ${showUpdate ? `<button class="btn danger small" data-action="mark-payout-failed" data-id="${escapeHtml(item.id)}">Mark failed</button>` : ""}
        ${showReverse ? `<button class="btn warn small" data-action="mark-payout-reversed" data-id="${escapeHtml(item.id)}">Reverse</button>` : ""}
      </div>
    `;
  }, "No payouts yet.");
}

async function refreshBatches() {
  const result = await apiRequest("/billing/payout-batches/", { includeEmployer: true });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  renderList("batchList", items, (item) => {
    const statusValue = String(item.status || "").toUpperCase();
    const canStart = ["DRAFT", "FAILED", "PARTIAL"].includes(statusValue);
    const canRetry = ["FAILED", "PARTIAL"].includes(statusValue);
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.batch_type || "Batch")}</p>
        ${statusPill(statusValue || "DRAFT")}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(formatDate(item.planned_date))}</span>
        <span>${escapeHtml(formatMoney(item.total_amount, item.currency))}</span>
        <span>${escapeHtml(String(item.payout_count || 0))} payouts</span>
      </div>
      <div class="item-actions">
        ${canStart ? `<button class="btn small" data-action="start-batch" data-id="${escapeHtml(item.id)}">Start</button>` : ""}
        ${canRetry ? `<button class="btn warn small" data-action="retry-batch" data-id="${escapeHtml(item.id)}">Retry failed</button>` : ""}
      </div>
    `;
  }, "No payout batches yet.");
}

async function refreshEmployeePayouts() {
  const result = await apiRequest("/billing/payout-methods/", { includeEmployer: false });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  renderList("employeePayoutList", items, (item) => {
    const defaultText = item.is_default ? "Default" : "Not default";
    const details = [];
    if (item.method_type === "BANK_ACCOUNT" && item.account_last4) {
      details.push(`****${escapeHtml(item.account_last4)}`);
    }
    if (item.method_type === "MOBILE_MONEY" && item.mobile_number) {
      details.push(escapeHtml(item.mobile_number));
    }
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.label || item.method_type || "Payout method")}</p>
        ${statusPill(item.verification_status || "UNVERIFIED")}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(item.method_type || "")}</span>
        <span>${escapeHtml(item.currency || "")}</span>
        <span>${details.join(" ") || ""}</span>
        <span>${escapeHtml(defaultText)}</span>
      </div>
      <div class="item-actions">
        <button class="btn ghost small" data-action="set-default-payout" data-id="${escapeHtml(item.id)}">Set default</button>
      </div>
    `;
  }, "No payout methods yet.");
}

async function refreshMyTransactions() {
  const result = await apiRequest("/billing/my/transactions/", { includeEmployer: false });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  renderList("myTransactionList", items, (item) => {
    const statusValue = String(item.status || "").toUpperCase();
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.category || "Transaction")}</p>
        ${statusPill(statusValue)}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(formatMoney(item.amount, item.currency))}</span>
        <span>${escapeHtml(item.description || "")}</span>
      </div>
    `;
  }, "No transactions yet.");
}

async function refreshMyPayouts() {
  const result = await apiRequest("/billing/my/payouts/", { includeEmployer: false });
  if (!result.ok) return;
  const items = extractList(unwrapData(result.data));
  renderList("myPayoutList", items, (item) => {
    const statusValue = String(item.status || "").toUpperCase();
    return `
      <div class="item-head">
        <p class="item-title">${escapeHtml(item.category || "Payout")}</p>
        ${statusPill(statusValue)}
      </div>
      <div class="item-meta">
        <span>${escapeHtml(formatMoney(item.amount, item.currency))}</span>
      </div>
    `;
  }, "No payouts yet.");
}

function setMode(mode) {
  state.mode = mode;
  const isEmployer = mode === "employer";
  $("employerSection").classList.toggle("hidden", !isEmployer);
  $("employeeSection").classList.toggle("hidden", isEmployer);
  $("employerMode").classList.toggle("active", isEmployer);
  $("employeeMode").classList.toggle("active", !isEmployer);
  const modePill = $("modePill");
  if (modePill) {
    modePill.textContent = isEmployer ? "Employer mode" : "Employee mode";
  }
  if (isEmployer) {
    refreshEmployerAll();
  } else {
    refreshEmployeeAll();
  }
}

async function refreshEmployerAll() {
  await Promise.all([
    refreshGbpayConnections(),
    refreshFunding(),
    refreshSubscriptions(),
    refreshInvoices(),
    refreshTransactions(),
    refreshPayouts(),
    refreshBatches(),
  ]);
}

async function refreshEmployeeAll() {
  await Promise.all([refreshEmployeePayouts(), refreshMyTransactions(), refreshMyPayouts()]);
}

function formToPayload(form) {
  const data = new FormData(form);
  const payload = {};
  for (const [key, value] of data.entries()) {
    if (value === "") continue;
    if (value === "on") {
      payload[key] = true;
    } else {
      payload[key] = value;
    }
  }
  return payload;
}

function parseJsonValue(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch (err) {
    return null;
  }
}

async function downloadInvoice(id, number) {
  const res = await fetch(buildUrl(`/billing/invoices/${id}/download/`), {
    headers: headers({ includeEmployer: true }),
  });
  if (!res.ok) {
    showToast("Unable to download invoice", "error");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${number || "invoice"}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function downloadReceipt(id) {
  const res = await fetch(buildUrl(`/billing/payouts/${id}/receipt/`), {
    headers: headers({ includeEmployer: true }),
  });
  if (!res.ok) {
    showToast("Unable to download receipt", "error");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `payout-receipt-${id}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

document.addEventListener("DOMContentLoaded", () => {
  loadConfig();

  $("saveConfig").addEventListener("click", (event) => {
    event.preventDefault();
    saveConfig();
  });

  $("loadConfig").addEventListener("click", (event) => {
    event.preventDefault();
    loadConfig();
  });

  $("employerMode").addEventListener("click", () => setMode("employer"));
  $("employeeMode").addEventListener("click", () => setMode("employee"));

  $("refreshFunding").addEventListener("click", refreshFunding);
  $("refreshGbpay").addEventListener("click", refreshGbpayConnections);
  $("refreshSubscriptions").addEventListener("click", refreshSubscriptions);
  $("refreshInvoices").addEventListener("click", refreshInvoices);
  $("refreshTransactions").addEventListener("click", refreshTransactions);
  $("refreshPayouts").addEventListener("click", refreshPayouts);
  $("refreshBatches").addEventListener("click", refreshBatches);
  $("refreshEmployeePayouts").addEventListener("click", refreshEmployeePayouts);
  $("refreshMyTransactions").addEventListener("click", refreshMyTransactions);
  $("refreshMyPayouts").addEventListener("click", refreshMyPayouts);

  $("fundingForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToPayload(event.target);
    const result = await apiRequest("/billing/funding-methods/", {
      method: "POST",
      body: payload,
      includeEmployer: true,
    });
    if (result.ok) {
      event.target.reset();
      refreshFunding();
    }
  });

  $("gbpayForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToPayload(event.target);
    if (!payload.api_key || !payload.secret_key || !payload.scope) {
      showToast("API key, secret key, and scope are required", "error");
      return;
    }
    const result = await apiRequest("/billing/gbpay-connections/", {
      method: "POST",
      body: payload,
      includeEmployer: true,
    });
    if (result.ok) {
      event.target.reset();
      refreshGbpayConnections();
    }
  });

  $("subscriptionForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToPayload(event.target);
    if (!payload.plan_id) {
      showToast("Plan ID is required", "error");
      return;
    }
    const result = await apiRequest("/billing/subscriptions/", {
      method: "POST",
      body: payload,
      includeEmployer: true,
    });
    if (result.ok) {
      event.target.reset();
      refreshSubscriptions();
    }
  });

  $("payoutForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToPayload(event.target);
    if (!payload.employee_id || !payload.amount) {
      showToast("Employee ID and amount are required", "error");
      return;
    }
    const result = await apiRequest("/billing/payouts/", {
      method: "POST",
      body: payload,
      includeEmployer: true,
    });
    if (result.ok) {
      event.target.reset();
      refreshPayouts();
    }
  });

  $("batchForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToPayload(event.target);
    const itemsRaw = payload.items;
    const items = parseJsonValue(itemsRaw);
    if (!items || !Array.isArray(items) || items.length === 0) {
      showToast("Batch items must be a JSON array.", "error");
      return;
    }
    payload.items = items;
    const result = await apiRequest("/billing/payout-batches/", {
      method: "POST",
      body: payload,
      includeEmployer: true,
    });
    if (result.ok) {
      event.target.reset();
      refreshBatches();
      refreshPayouts();
    }
  });

  $("employeePayoutForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToPayload(event.target);
    if (!payload.method_type) {
      showToast("Method type is required", "error");
      return;
    }
    if (!payload.country || !payload.entity_product_uuid) {
      showToast("Country and entity product UUID are required", "error");
      return;
    }
    if (payload.method_type === "BANK_ACCOUNT") {
      if (!payload.bank_code || !payload.account_number) {
        showToast("Bank code and account number are required for bank payouts", "error");
        return;
      }
    }
    if (payload.method_type === "MOBILE_MONEY") {
      if (!payload.operator_code || !payload.wallet_destination) {
        showToast("Operator code and wallet destination are required for mobile payouts", "error");
        return;
      }
    }
    const result = await apiRequest("/billing/payout-methods/", {
      method: "POST",
      body: payload,
      includeEmployer: false,
    });
    if (result.ok) {
      event.target.reset();
      refreshEmployeePayouts();
    }
  });

  $("fundingList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "set-default-subscription") {
      await apiRequest(`/billing/funding-methods/${id}/set-default/`, {
        method: "POST",
        body: { scope: "SUBSCRIPTION" },
        includeEmployer: true,
      });
      refreshFunding();
    }
    if (action === "set-default-payroll") {
      await apiRequest(`/billing/funding-methods/${id}/set-default/`, {
        method: "POST",
        body: { scope: "PAYROLL" },
        includeEmployer: true,
      });
      refreshFunding();
    }
  });

  $("gbpayList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "test-gbpay") {
      await apiRequest(`/billing/gbpay-connections/${id}/test/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshGbpayConnections();
    }
    if (action === "enable-gbpay") {
      await apiRequest(`/billing/gbpay-connections/${id}/enable/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshGbpayConnections();
    }
    if (action === "disable-gbpay") {
      await apiRequest(`/billing/gbpay-connections/${id}/disable/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshGbpayConnections();
    }
  });

  $("subscriptionList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "issue-invoice") {
      await apiRequest(`/billing/subscriptions/${id}/issue-invoice/`, {
        method: "POST",
        body: { auto_charge: true },
        includeEmployer: true,
      });
      refreshInvoices();
      refreshSubscriptions();
    }
    if (action === "cancel-subscription") {
      await apiRequest(`/billing/subscriptions/${id}/cancel/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshSubscriptions();
    }
    if (action === "resume-subscription") {
      await apiRequest(`/billing/subscriptions/${id}/resume/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshSubscriptions();
    }
  });

  $("invoiceList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "download-invoice") {
      await downloadInvoice(id, button.dataset.number);
    }
    if (action === "mark-invoice-paid") {
      const reference = window.prompt("Provider reference (optional)", "");
      await apiRequest(`/billing/invoices/${id}/mark-paid/`, {
        method: "POST",
        body: { status: "PAID", provider_reference: reference || "" },
        includeEmployer: true,
      });
      refreshInvoices();
    }
    if (action === "mark-invoice-failed") {
      const reason = window.prompt("Failure reason (optional)", "");
      await apiRequest(`/billing/invoices/${id}/mark-failed/`, {
        method: "POST",
        body: { status: "FAILED", failure_reason: reason || "" },
        includeEmployer: true,
      });
      refreshInvoices();
    }
  });

  $("transactionList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "refund-transaction") {
      const reason = window.prompt("Refund reason (optional)", "");
      await apiRequest(`/billing/transactions/${id}/refund/`, {
        method: "POST",
        body: { reason: reason || "" },
        includeEmployer: true,
      });
      refreshTransactions();
    }
  });

  $("payoutList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "execute-payout") {
      await apiRequest(`/billing/payouts/${id}/execute/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshPayouts();
    }
    if (action === "retry-payout") {
      await apiRequest(`/billing/payouts/${id}/retry/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshPayouts();
    }
    if (action === "download-receipt") {
      await downloadReceipt(id);
    }
    if (action === "mark-payout-paid") {
      const reference = window.prompt("Provider reference (optional)", "");
      await apiRequest(`/billing/payouts/${id}/mark-status/`, {
        method: "POST",
        body: { status: "PAID", provider_reference: reference || "" },
        includeEmployer: true,
      });
      refreshPayouts();
    }
    if (action === "mark-payout-failed") {
      const reason = window.prompt("Failure reason (optional)", "");
      await apiRequest(`/billing/payouts/${id}/mark-status/`, {
        method: "POST",
        body: { status: "FAILED", failure_reason: reason || "" },
        includeEmployer: true,
      });
      refreshPayouts();
    }
    if (action === "mark-payout-reversed") {
      await apiRequest(`/billing/payouts/${id}/mark-status/`, {
        method: "POST",
        body: { status: "REVERSED" },
        includeEmployer: true,
      });
      refreshPayouts();
    }
  });

  $("batchList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === "start-batch") {
      await apiRequest(`/billing/payout-batches/${id}/start/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshBatches();
      refreshPayouts();
    }
    if (action === "retry-batch") {
      await apiRequest(`/billing/payout-batches/${id}/retry-failed/`, {
        method: "POST",
        includeEmployer: true,
      });
      refreshBatches();
      refreshPayouts();
    }
  });

  $("employeePayoutList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    if (button.dataset.action === "set-default-payout") {
      await apiRequest(`/billing/payout-methods/${id}/set-default/`, {
        method: "POST",
        body: { confirm: true },
        includeEmployer: false,
      });
      refreshEmployeePayouts();
    }
  });

  setMode("employer");
});
