// Zé's Pizzeria menu site: plain JavaScript, no build step.
//
// Two views, chosen by the URL hash:
//   #/              the menu, the basket and the delivery form
//   #/order/<id>    one order and its status, refreshed every few seconds
//
// Every call to the API goes through api() below. It always sends JSON with
// "Content-Type: application/json" (the API rejects JSON bodies without it,
// see issue #25) and turns the API's error responses into readable messages.

"use strict";

const API_URL = String(window.SLICEPIZZA_CONFIG?.apiUrl || "").replace(/\/+$/, "");
const REFRESH_MS = 10_000;
const MAX_RETRY_MS = 60_000; // after repeated errors, retry at most this far apart
const MAX_PIZZAS_PER_ORDER = 50; // same limit as the API (api/app/schemas.py)

const STEPS = [
  { status: "received", label: "Order received", detail: "The kitchen has your order." },
  { status: "preparing", label: "Being prepared", detail: "Your pizzas are in the oven." },
  { status: "out_for_delivery", label: "On the way", detail: "The courier has left the pizzeria." },
  { status: "delivered", label: "Delivered", detail: "Enjoy your meal." },
];

const MISSING_FIELD = {
  name: "Enter your name.",
  phone: "Enter a phone number so the courier can call you.",
  address: "Enter the delivery address.",
};

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const formatPrice = (cents) => money.format(cents / 100);

const $ = (id) => document.getElementById(id);

// --- API --------------------------------------------------------------------

class ApiError extends Error {
  constructor(message, status, fields = {}) {
    super(message);
    this.status = status;
    this.fields = fields; // { name: "message", ... } for invalid form fields
  }
}

async function api(path, { method = "GET", body } = {}) {
  const options = { method, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    // No answer at all: network down, wrong API address, blocked by the page's
    // Content-Security-Policy (connect-src) or refused by the API's CORS.
    throw new ApiError("Couldn't reach the pizzeria. Check your connection and try again.", 0);
  }

  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // Not JSON (e.g. a proxy error page); handled below by the status code.
  }

  if (!response.ok) throw toApiError(response.status, data);
  return data;
}

function toApiError(status, data) {
  const detail = data?.detail;

  if (status === 422 && Array.isArray(detail)) {
    // FastAPI validation errors: [{ loc: ["body", "customer", "phone"], msg: "..." }, ...]
    const fields = {};
    const general = [];
    for (const error of detail) {
      const field = { name: "name", phone: "phone", address: "address" }[error.loc?.at(-1)];
      const message = String(error.msg || "Invalid value").replace(/^Value error, /, "");
      if (field && error.loc?.includes("customer")) fields[field] ??= message;
      else general.push(message);
    }
    const message = general[0] || "Some details need fixing. Check the highlighted fields.";
    return new ApiError(message, status, fields);
  }
  // 503 comes from the API (database down); 502 and 504 from the web proxy
  // (Caddy) when the API itself is down or too slow to answer.
  if (status === 502 || status === 503 || status === 504) {
    return new ApiError("The pizzeria's system is offline for a moment. Try again in a minute.", status);
  }
  if (typeof detail === "string") return new ApiError(detail, status);
  return new ApiError(`Something went wrong on our side (error ${status}). Try again.`, status);
}

// --- Small DOM helpers --------------------------------------------------------

function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  // Text from the API always goes in as text, never as HTML.
  node.append(...children);
  return node;
}

function showNotice(node, message, kind = "info") {
  node.textContent = message;
  node.classList.toggle("notice-error", kind === "error");
  node.hidden = !message;
}

// --- Order view ---------------------------------------------------------------

const basket = new Map(); // pizza id -> quantity
let menu = [];

// Loads the menu and returns how many basket lines it had to drop because
// their pizza left the menu or sold out.
async function loadMenu() {
  const status = $("menu-status");
  showNotice(status, "Loading the menu…");
  try {
    menu = await api("/menu");
  } catch (error) {
    showNotice(status, error.message, "error");
    status.append(" ", el("button", { class: "link", type: "button", onclick: () => loadMenu() }, "Try again"));
    return 0;
  }
  const dropped = pruneBasket();
  if (menu.length === 0) {
    showNotice(status, "The menu is empty right now. Check back later.");
    renderBasket();
    return dropped;
  }
  showNotice(status, "");
  renderMenu();
  $("order-form").hidden = false;
  $("basket").hidden = false;
  return dropped;
}

// Removes from the basket what the customer can no longer order. Without
// this, a pizza that left the menu stays in the basket with no button to
// take it out, and every new order fails on it again.
function pruneBasket() {
  let dropped = 0;
  for (const id of [...basket.keys()]) {
    if (!menu.find((pizza) => pizza.id === id)?.available) {
      basket.delete(id);
      dropped += 1;
    }
  }
  return dropped;
}

function renderMenu() {
  const list = $("menu");
  list.replaceChildren(
    ...menu.map((pizza) => {
      const quantity = basket.get(pizza.id) || 0;
      const nameId = `pizza-${pizza.id}`;
      const controls = pizza.available
        ? el(
            "div",
            { class: "stepper", role: "group", "aria-labelledby": nameId },
            el("button", {
              type: "button",
              class: "step",
              "aria-label": `Remove one ${pizza.name}`,
              onclick: () => changeQuantity(pizza.id, -1),
              ...(quantity === 0 ? { disabled: "" } : {}),
            }, "−"),
            el("output", { class: "qty", "aria-live": "polite", "aria-label": `${pizza.name} quantity` }, String(quantity)),
            el("button", {
              type: "button",
              class: "step",
              "aria-label": `Add one ${pizza.name}`,
              onclick: () => changeQuantity(pizza.id, +1),
              ...(totalPizzas() >= MAX_PIZZAS_PER_ORDER ? { disabled: "" } : {}),
            }, "+"),
          )
        : el("p", { class: "sold-out" }, "Sold out today");

      return el(
        "li",
        { class: `dish${pizza.available ? "" : " is-unavailable"}${quantity ? " is-chosen" : ""}` },
        el(
          "div",
          { class: "dish-line" },
          el("h3", { class: "dish-name", id: nameId }, pizza.name),
          el("span", { class: "leader", "aria-hidden": "true" }),
          el("span", { class: "price" }, formatPrice(pizza.price_cents)),
        ),
        el("p", { class: "dish-description" }, pizza.description),
        controls,
      );
    }),
  );
  renderBasket();
}

function totalPizzas() {
  let total = 0;
  for (const quantity of basket.values()) total += quantity;
  return total;
}

function changeQuantity(pizzaId, delta) {
  const next = (basket.get(pizzaId) || 0) + delta;
  if (next <= 0) basket.delete(pizzaId);
  else if (totalPizzas() + delta <= MAX_PIZZAS_PER_ORDER) basket.set(pizzaId, next);

  // Keep keyboard focus on the button that was pressed after re-rendering.
  const label = document.activeElement?.getAttribute("aria-label");
  renderMenu();
  if (label) {
    const again = [...document.querySelectorAll(".step")].find((b) => b.getAttribute("aria-label") === label);
    if (again && !again.disabled) again.focus();
  }
}

function renderBasket() {
  const count = totalPizzas();
  let total = 0;
  for (const [id, quantity] of basket) {
    const pizza = menu.find((p) => p.id === id);
    if (pizza) total += pizza.price_cents * quantity;
  }
  $("basket-count").textContent =
    count === 0 ? "No pizzas yet" : `${count} pizza${count === 1 ? "" : "s"}`;
  $("basket-total").textContent = count === 0 ? "" : formatPrice(total);
  $("place-order").disabled = count === 0;
}

function clearFieldErrors(form) {
  for (const field of form.querySelectorAll(".field")) {
    field.classList.remove("has-error");
    field.querySelector(".field-error")?.remove();
    field.querySelector("input, textarea").removeAttribute("aria-invalid");
  }
}

function showFieldError(form, name, message) {
  const input = form.elements[name];
  const field = input.closest(".field");
  field.classList.add("has-error");
  input.setAttribute("aria-invalid", "true");
  const id = `${name}-error`;
  input.setAttribute("aria-describedby", id);
  field.append(el("p", { class: "field-error", id }, message));
}

async function placeOrder(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("place-order");
  const formError = $("form-error");
  clearFieldErrors(form);
  showNotice(formError, "");

  const customer = {
    name: form.elements.name.value.trim(),
    phone: form.elements.phone.value.trim(),
    address: form.elements.address.value.trim(),
  };

  const missing = Object.keys(customer).filter((key) => !customer[key]);
  if (missing.length) {
    for (const key of missing) showFieldError(form, key, MISSING_FIELD[key]);
    form.elements[missing[0]].focus();
    return;
  }

  const items = [...basket].map(([pizza_id, quantity]) => ({ pizza_id, quantity }));
  button.disabled = true;
  button.textContent = "Placing order…";
  try {
    const order = await api("/orders", { method: "POST", body: { customer, items } });
    basket.clear();
    form.reset();
    rememberOrder(order.id);
    location.hash = `#/order/${order.id}`;
  } catch (error) {
    const fields = Object.entries(error.fields || {});
    for (const [name, message] of fields) showFieldError(form, name, message);
    showNotice(formError, error.message, "error");
    if (fields.length) form.elements[fields[0][0]].focus();
    // 404: a pizza left the menu; 409: one sold out, since the page loaded.
    // Reload the menu so the page shows what is really available.
    if (error.status === 404 || error.status === 409) {
      if (await loadMenu()) {
        showNotice(formError, `${error.message} We took it out of your basket: check it and place the order again.`, "error");
      }
    }
  } finally {
    button.textContent = "Place order";
    renderBasket();
  }
}

// --- Tracking view ------------------------------------------------------------

let refreshTimer = null;
// Bumped on every route change. A request that answers after the customer
// left its view (or opened another order) sees a different number and is
// ignored, so it can neither draw the wrong order nor restart the polling.
let viewGeneration = 0;
// The order being followed while its status can still change, or null.
let pollingId = null;
let failedRefreshes = 0;

function rememberOrder(id) {
  // Lets the customer find the order again after closing the tab. Storage can
  // be unavailable (private mode, blocked cookies); the site works without it.
  try {
    localStorage.setItem("slicepizza:last-order", id);
  } catch {}
}

function showOrderNotFound() {
  pollingId = null;
  $("track-body").hidden = true;
  showNotice($("track-status"), "We couldn't find that order. Check the link you used.", "error");
}

// Asks for the order again after `delay`. A tab in the background does not
// poll: the visibilitychange listener below refreshes it when it comes back.
function scheduleRefresh(id, generation, delay) {
  clearTimeout(refreshTimer);
  pollingId = id;
  if (!document.hidden) refreshTimer = setTimeout(() => loadOrder(id, generation), delay);
}

async function loadOrder(id, generation) {
  clearTimeout(refreshTimer);
  const status = $("track-status");
  let order;
  try {
    order = await api(`/orders/${encodeURIComponent(id)}`);
  } catch (error) {
    if (generation !== viewGeneration) return;
    if (error.status === 404 || error.status === 422) {
      showOrderNotFound();
      return;
    }
    // Wait longer after each failure in a row: 10 s, 20 s, 40 s, then 60 s.
    failedRefreshes += 1;
    showNotice(status, `${error.message} Retrying in a few seconds.`, "error");
    scheduleRefresh(id, generation, Math.min(REFRESH_MS * 2 ** (failedRefreshes - 1), MAX_RETRY_MS));
    return;
  }
  if (generation !== viewGeneration) return;

  failedRefreshes = 0;
  showNotice(status, "");
  renderOrder(order);
  if (order.status !== "delivered" && order.status !== "cancelled") {
    scheduleRefresh(id, generation, REFRESH_MS);
  } else {
    pollingId = null;
  }
}

function renderOrder(order) {
  $("track-body").hidden = false;
  $("order-id").textContent = order.id.slice(0, 8);
  $("order-id").title = order.id;

  const cancelled = order.status === "cancelled";
  const current = STEPS.findIndex((step) => step.status === order.status);
  $("steps").replaceChildren(
    ...STEPS.map((step, index) => {
      const state = cancelled ? "skipped" : index < current ? "done" : index === current ? "current" : "todo";
      return el(
        "li",
        { class: `step-item is-${state}`, ...(state === "current" ? { "aria-current": "step" } : {}) },
        el("span", { class: "step-label" }, step.label),
        state === "current" ? el("span", { class: "step-detail" }, step.detail) : "",
      );
    }),
  );
  $("steps").hidden = cancelled;
  $("cancelled").hidden = !cancelled;

  $("order-items").replaceChildren(
    ...order.items.map((item) =>
      el(
        "li",
        {},
        el("span", {}, `${item.quantity} × ${item.pizza_name}`),
        el("span", { class: "price" }, formatPrice(item.unit_price_cents * item.quantity)),
      ),
    ),
  );
  $("order-total").textContent = formatPrice(order.total_cents);
  $("order-address").textContent = order.delivery_address;
}

// --- Routing ------------------------------------------------------------------

function showLastOrderLink() {
  let id = null;
  try {
    id = localStorage.getItem("slicepizza:last-order");
  } catch {}
  const link = $("last-order");
  link.hidden = !id;
  if (id) link.querySelector("a").href = `#/order/${encodeURIComponent(id)}`;
}

function route(event) {
  clearTimeout(refreshTimer);
  viewGeneration += 1;
  pollingId = null;
  failedRefreshes = 0;
  const match = location.hash.match(/^#\/order\/([^/?#]+)$/);
  $("order-view").hidden = Boolean(match);
  $("track-view").hidden = !match;

  if (match) {
    $("track-body").hidden = true;
    let id = null;
    try {
      id = decodeURIComponent(match[1]);
    } catch {
      // A cut or mangled link (e.g. "%E0%A4") is not a valid order id.
    }
    if (id === null) {
      showOrderNotFound();
    } else {
      showNotice($("track-status"), "Loading your order…");
      loadOrder(id, viewGeneration);
    }
  } else {
    showLastOrderLink();
    if (menu.length === 0) loadMenu();
    else renderMenu();
  }
  // On navigation (not the first load), move focus and scroll to the new view.
  if (event) {
    $("main").focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
}

// Stop polling while the tab is in the background; refresh as soon as the
// customer comes back to it.
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearTimeout(refreshTimer);
  else if (pollingId) loadOrder(pollingId, viewGeneration);
});

$("order-form").addEventListener("submit", placeOrder);
window.addEventListener("hashchange", route);
route();
