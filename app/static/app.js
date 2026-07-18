const state = { order: null, index: 0, accessories: [], audit: [], resultTab: "glasses" };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[char]);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = "No se pudo completar la operación.";
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(node.timer);
  node.timer = setTimeout(() => node.classList.remove("show"), 3000);
}

function showView(id) {
  $$(".view").forEach(view => view.classList.add("hidden"));
  $(id).classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "instant" });
}

async function loadOrders() {
  const orders = await api("/api/orders");
  const list = $("#orders-list");
  if (!orders.length) {
    list.innerHTML = '<p class="empty">Todavía no hay órdenes procesadas.</p>';
    return;
  }
  list.innerHTML = orders.map(order => `
    <button class="order-row" data-order="${order.id}">
      <span><strong>${escapeHtml(order.client_name)}</strong><span>${escapeHtml(order.source_filename)} · ${new Date(order.created_at).toLocaleString("es-AR")}</span></span>
      <i class="status-chip ${order.status === "confirmed" ? "confirmed" : "review"}">${order.status === "confirmed" ? "Confirmada" : "En revisión"}</i>
    </button>`).join("");
  $$(".order-row").forEach(button => button.addEventListener("click", () => openOrder(button.dataset.order)));
}

async function openOrder(id) {
  state.order = await api(`/api/orders/${id}`);
  state.index = Math.max(0, state.order.document.typologies.findIndex(item => item.review.status !== "confirmed"));
  $("#order-context").textContent = `${state.order.client_name} · ${state.order.source_filename}`;
  renderReview();
  showView("#review-view");
}

function currentTypology() { return state.order.document.typologies[state.index]; }

function stateLabel(status) {
  return ({ detected: "Detectado", modified: "Modificado", quantity_modified: "Modificado", manual: "Agregado manualmente", excluded: "Excluido" })[status] || status;
}

function naturalCompare(left, right) {
  return left.code.localeCompare(right.code, "es", { numeric: true, sensitivity: "base" });
}

function renderReview() {
  const document = state.order.document;
  const typologies = document.typologies;
  const current = currentTypology();
  const confirmed = typologies.filter(item => item.review.status === "confirmed").length;
  const percent = Math.round((confirmed / typologies.length) * 100);
  $("#progress-text").textContent = `${confirmed} de ${typologies.length}`;
  $("#progress-percent").textContent = `${percent}%`;
  $("#progress-bar").style.width = `${percent}%`;
  $("#typology-list").innerHTML = typologies.map((item, index) => `
    <button class="typology-link ${index === state.index ? "active" : ""}" data-index="${index}">
      <span class="page">${item.page}</span><strong>${escapeHtml(item.typology.value)}</strong>
      <i class="review-dot ${item.review.status === "confirmed" ? "confirmed" : ""}"></i>
    </button>`).join("");
  $$(".typology-link").forEach(button => button.addEventListener("click", () => {
    state.index = Number(button.dataset.index); renderReview();
  }));
  $("#typology-title").textContent = current.typology.value;
  $("#fact-page").textContent = `${current.page} / ${typologies.length}`;
  $("#fact-detail").textContent = current.detail.value;
  $("#fact-quantity").textContent = current.typology_quantity.value;
  $("#fact-status").textContent = current.review.status === "confirmed" ? "Confirmada" : "Pendiente";
  $("#confirm-typology").textContent = current.review.status === "confirmed" ? "Tipología confirmada" : "Confirmar tipología";
  $("#confirm-typology").disabled = current.review.status === "confirmed";
  $("#previous-typology").disabled = state.index === 0;
  $("#next-typology").disabled = state.index === typologies.length - 1;

  const quantityWarning = current.warnings.find(item => item.code === "cantidad_tipologia_mayor_uno");
  const otherWarnings = current.warnings.filter(item => item.code !== "cantidad_tipologia_mayor_uno");
  $("#typology-warning").innerHTML = [
    quantityWarning ? `<div class="warning">${escapeHtml(quantityWarning.message)}</div>` : "",
    otherWarnings.length ? `<div class="warning danger">${otherWarnings.length} dato(s) requieren revisión. Verificá las filas señaladas antes de confirmar.</div>` : ""
  ].join("");

  $("#glass-count").textContent = `${current.glasses.length} ${current.glasses.length === 1 ? "fila" : "filas"}`;
  $("#glass-rows").innerHTML = current.glasses.length ? current.glasses.map(item => `
    <tr class="${item.excluded ? "excluded" : ""}">
      <td><span class="state ${item.status}">${stateLabel(item.status)}</span></td>
      <td><strong>${item.material_type === "mesh" ? "Tela mosquitera" : "Vidrio"}</strong></td>
      <td><input class="table-input" data-glass-quantity="${item.id}" type="number" min="0" step="any" value="${item.quantity_final}" ${item.excluded ? "disabled" : ""}></td>
      <td><input class="table-input" data-glass-measure="${item.id}" value="${escapeHtml(item.measure_final)}" ${item.excluded ? "disabled" : ""}></td>
      <td><input class="table-input description-input" data-glass-description="${item.id}" value="${escapeHtml(item.description_final)}" ${item.excluded ? "disabled" : ""}></td>
      <td><input class="table-input observation-input" data-glass-observations="${item.id}" value="${escapeHtml(item.observations || "")}" placeholder="Opcional" ${item.excluded ? "disabled" : ""}></td>
      <td><div class="row-actions">
        <button class="button ghost small" data-save-glass="${item.id}" ${item.excluded ? "disabled" : ""}>Guardar</button>
        <button class="button ghost small" data-exclude-glass="${item.id}" data-value="${!item.excluded}">${item.excluded ? "Restaurar" : "Excluir"}</button>
      </div></td>
    </tr>
  `).join("") : '<tr><td colspan="7" class="empty">Sin vidrios ni telas para esta tipología.</td></tr>';

  const sortedAccessories = [...current.accessories].sort(naturalCompare);
  $("#accessory-rows").innerHTML = sortedAccessories.length ? sortedAccessories.map(item => `
    <tr class="${item.excluded ? "excluded" : ""}">
      <td><span class="state ${item.status}">${stateLabel(item.status)}</span>${item.confidence === "low" ? '<br><small>Revisar extracción</small>' : ""}</td>
      <td><strong>${escapeHtml(item.code)}</strong></td>
      <td><input class="quantity-input" data-quantity="${item.id}" type="number" min="0" step="any" value="${item.quantity_final}" ${item.excluded ? "disabled" : ""}></td>
      <td>${escapeHtml(item.detail_final || "Sin descripción")}${item.warnings?.length ? `<br><small>${escapeHtml(item.warnings.join(" "))}</small>` : ""}</td>
      <td><input class="table-input observation-input" data-accessory-observations="${item.id}" value="${escapeHtml(item.observations || "")}" placeholder="Opcional" ${item.excluded ? "disabled" : ""}></td>
      <td><div class="row-actions">
        <button class="button ghost small" data-save="${item.id}" ${item.excluded ? "disabled" : ""}>Guardar</button>
        <button class="button ghost small" data-exclude="${item.id}" data-value="${!item.excluded}">${item.excluded ? "Restaurar" : "Excluir"}</button>
      </div></td>
    </tr>`).join("") : '<tr><td colspan="6" class="empty">Sin accesorios detectados.</td></tr>';

  $$("[data-save-glass]").forEach(button => button.addEventListener("click", () => saveGlass(button.dataset.saveGlass)));
  $$("[data-exclude-glass]").forEach(button => button.addEventListener("click", () => setGlassExcluded(button.dataset.excludeGlass, button.dataset.value === "true")));
  $$("[data-save]").forEach(button => button.addEventListener("click", () => saveQuantity(button.dataset.save)));
  $$("[data-exclude]").forEach(button => button.addEventListener("click", () => setExcluded(button.dataset.exclude, button.dataset.value === "true")));
}

async function reloadOrder() {
  state.order = await api(`/api/orders/${state.order.id}`);
  renderReview();
}

async function saveQuantity(accessoryId) {
  const input = document.querySelector(`[data-quantity="${accessoryId}"]`);
  const observations = document.querySelector(`[data-accessory-observations="${accessoryId}"]`);
  try {
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/accessories/${accessoryId}/quantity`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quantity: Number(input.value) })
    });
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/accessories/${accessoryId}/observations`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ observations: observations.value })
    });
    await reloadOrder(); toast("Cantidad actualizada.");
  } catch (error) { toast(error.message); }
}

async function saveGlass(glassId) {
  try {
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/glasses/${glassId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        quantity: Number(document.querySelector(`[data-glass-quantity="${glassId}"]`).value),
        measure: document.querySelector(`[data-glass-measure="${glassId}"]`).value,
        description: document.querySelector(`[data-glass-description="${glassId}"]`).value,
        observations: document.querySelector(`[data-glass-observations="${glassId}"]`).value
      })
    });
    await reloadOrder(); toast("Elemento actualizado.");
  } catch (error) { toast(error.message); }
}

async function setGlassExcluded(glassId, excluded) {
  try {
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/glasses/${glassId}/exclusion`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ excluded })
    });
    await reloadOrder(); toast(excluded ? "Elemento excluido." : "Elemento restaurado.");
  } catch (error) { toast(error.message); }
}

async function setExcluded(accessoryId, excluded) {
  try {
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/accessories/${accessoryId}/exclusion`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ excluded })
    });
    await reloadOrder(); toast(excluded ? "Accesorio excluido." : "Accesorio restaurado.");
  } catch (error) { toast(error.message); }
}

async function confirmCurrent() {
  try {
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/confirm`, { method: "POST" });
    await reloadOrder();
    const next = state.order.document.typologies.findIndex((item, index) => index > state.index && item.review.status !== "confirmed");
    if (next >= 0) { state.index = next; renderReview(); }
    toast("Tipología confirmada.");
  } catch (error) { toast(error.message); }
}

async function renderResults() {
  state.order = await api(`/api/orders/${state.order.id}`);
  state.accessories = await api(`/api/orders/${state.order.id}/results/accessories`);
  state.audit = await api(`/api/orders/${state.order.id}/audit`);
  const id = state.order.id;
  $("#results-client").textContent = `${state.order.client_name} · ${state.order.source_filename}`;
  $("#export-glasses-csv").href = `/api/orders/${id}/export/glasses.csv`;
  $("#export-accessories-csv").href = `/api/orders/${id}/export/accessories.csv`;
  const glasses = state.order.document.typologies.flatMap(typology => typology.glasses.filter(glass => !glass.excluded).map(glass => ({
    client: state.order.client_name, typology: typology.typology.value, opening: typology.detail.value, ...glass
  })));
  $("#result-glasses").innerHTML = glasses.map(item => `<tr><td>${escapeHtml(item.client)}</td><td>${escapeHtml(item.typology)}</td><td>${escapeHtml(item.opening)}</td><td>${item.material_type === "mesh" ? "Tela mosquitera" : "Vidrio"}</td><td>${item.quantity_final}</td><td>${escapeHtml(item.measure_final)}</td><td>${escapeHtml(item.description_final)}</td><td>${escapeHtml(item.observations || "")}</td></tr>`).join("");
  const conflicts = state.accessories.filter(item => item["Conflicto"]);
  $("#conflict-banner").innerHTML = conflicts.length ? `<div class="warning">${conflicts.length} código(s) tienen descripciones distintas. Confirmá una descripción final antes de finalizar.</div>` : "";
  $("#result-accessories").innerHTML = state.accessories.map(item => `
    <tr class="${item["Conflicto"] ? "conflict-row" : ""}">
      <td><strong>${escapeHtml(item["Código"])}</strong></td><td>${item["Cantidad Total"]}</td>
      <td>${item["Conflicto"] ? `<div class="conflict-editor"><small>${escapeHtml(item["Descripciones detectadas"].join(" · "))}</small><input data-description="${escapeHtml(item["Código"])}" placeholder="Descripción final"><button class="button secondary small" data-resolve="${escapeHtml(item["Código"])}">Confirmar descripción</button></div>` : escapeHtml(item["Detalle"])}</td>
      <td><span class="state">${escapeHtml(item["Origen"])}</span></td><td>${escapeHtml(item["Observaciones"] || "")}</td>
    </tr>`).join("");
  $$("[data-resolve]").forEach(button => button.addEventListener("click", () => resolveConflict(button.dataset.resolve)));
  $("#audit-list").innerHTML = state.audit.length ? state.audit.map(item => `<div class="audit-item"><time>${new Date(item.created_at).toLocaleString("es-AR")}</time><div><strong>${escapeHtml(item.event_type.replaceAll("_", " "))}</strong>${item.page ? ` · Página ${item.page}` : ""}</div></div>`).join("") : '<p class="empty">Sin modificaciones registradas.</p>';
  setResultTab(state.resultTab);
  showView("#results-view");
}

function setResultTab(name) {
  state.resultTab = name;
  $$(".tab").forEach(item => item.classList.toggle("active", item.dataset.tab === name));
  ["glasses", "accessories", "audit"].forEach(tabName => $(`#${tabName}-tab`).classList.toggle("hidden", tabName !== name));
  const exportable = name === "glasses" || name === "accessories";
  $("#export-xlsx").classList.toggle("hidden", !exportable);
  $("#export-pdf").classList.toggle("hidden", !exportable);
  if (exportable && state.order) {
    $("#export-xlsx").href = `/api/orders/${state.order.id}/export/${name}.xlsx`;
    $("#export-pdf").href = `/api/orders/${state.order.id}/export/${name}.pdf`;
  }
  $("#results-title").textContent = name === "accessories"
    ? "Listado de Accesorios"
    : name === "audit" ? "Trazabilidad de la Orden" : "Listado de Vidrios";
}

async function resolveConflict(code) {
  const input = document.querySelector(`[data-description="${CSS.escape(code)}"]`);
  try {
    await api(`/api/orders/${state.order.id}/results/accessories/${encodeURIComponent(code)}/description`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ final_description: input.value })
    });
    await renderResults(); toast("Descripción confirmada.");
  } catch (error) { toast(error.message); }
}

$("#pdf-file").addEventListener("change", event => {
  $("#file-label").textContent = event.target.files[0]?.name || "Seleccionar PDF de Winmaker";
});
$("#upload-form").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const message = $("#upload-message");
  button.disabled = true; button.textContent = "Analizando…"; message.textContent = "";
  try {
    const form = new FormData(event.currentTarget);
    const order = await api("/api/orders", { method: "POST", body: form });
    state.order = order; state.index = 0; renderReview(); showView("#review-view");
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; button.textContent = "Analizar orden"; }
});
$("#refresh-orders").addEventListener("click", loadOrders);
$("#back-home").addEventListener("click", () => { loadOrders(); showView("#home-view"); });
$("#previous-typology").addEventListener("click", () => { state.index--; renderReview(); });
$("#next-typology").addEventListener("click", () => { state.index++; renderReview(); });
$("#confirm-typology").addEventListener("click", confirmCurrent);
$("#open-add-accessory").addEventListener("click", () => $("#accessory-dialog").showModal());
$("#open-add-glass").addEventListener("click", () => $("#glass-dialog").showModal());
$("#add-accessory-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (event.submitter?.value === "cancel") { $("#accessory-dialog").close(); return; }
  const form = new FormData(event.currentTarget);
  try {
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/accessories`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: form.get("code"), quantity: Number(form.get("quantity")), detail: form.get("detail"), observations: form.get("observations") })
    });
    event.currentTarget.reset(); $("#accessory-dialog").close(); await reloadOrder(); toast("Accesorio agregado.");
  } catch (error) { toast(error.message); }
});
$("#add-glass-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (event.submitter?.value === "cancel") { $("#glass-dialog").close(); return; }
  const form = new FormData(event.currentTarget);
  try {
    await api(`/api/orders/${state.order.id}/typologies/${currentTypology().id}/glasses`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        material_type: form.get("material_type"), quantity: Number(form.get("quantity")),
        measure: form.get("measure"), description: form.get("description"), observations: form.get("observations")
      })
    });
    event.currentTarget.reset(); $("#glass-dialog").close(); await reloadOrder(); toast("Elemento agregado.");
  } catch (error) { toast(error.message); }
});
$("#view-results").addEventListener("click", renderResults);
$("#back-review").addEventListener("click", () => { renderReview(); showView("#review-view"); });
$("#finalize-order").addEventListener("click", async () => {
  try { await api(`/api/orders/${state.order.id}/finalize`, { method: "POST" }); await reloadOrder(); toast("Orden finalizada."); }
  catch (error) { toast(error.message); }
});
$$(".tab").forEach(tab => tab.addEventListener("click", () => setResultTab(tab.dataset.tab)));

loadOrders().catch(error => toast(error.message));
