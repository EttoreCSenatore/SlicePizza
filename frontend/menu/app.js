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
    // Network down, wrong API address, or the API refused this site's origin (CORS).
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
  if (status === 503) {
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

async function loadMenu() {
  const status = $("menu-status");
  showNotice(status, "Loading the menu…");
  try {
    menu = await api("/menu");
  } catch (error) {
    showNotice(status, error.message, "error");
    status.append(" ", el("button", { class: "link", type: "button", onclick: loadMenu }, "Try again"));
    return;
  }
  if (menu.length === 0) {
    showNotice(status, "The menu is empty right now. Check back later.");
    return;
  }
  showNotice(status, "");
  renderMenu();
  $("order-form").hidden = false;
  $("basket").hidden = false;
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
    // A pizza may have sold out or left the menu since the page loaded.
    if (error.status === 404) loadMenu();
  } finally {
    button.textContent = "Place order";
    renderBasket();
  }
}

// --- Tracking view ------------------------------------------------------------

let refreshTimer = null;

function rememberOrder(id) {
  // Lets the customer find the order again after closing the tab. Storage can
  // be unavailable (private mode, blocked cookies); the site works without it.
  try {
    localStorage.setItem("slicepizza:last-order", id);
  } catch {}
}

async function loadOrder(id) {
  clearTimeout(refreshTimer);
  const status = $("track-status");
  let order;
  try {
    order = await api(`/orders/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error.status === 404 || error.status === 422) {
      $("track-body").hidden = true;
      showNotice(status, "We couldn't find that order. Check the link you used.", "error");
      return;
    }
    showNotice(status, `${error.message} Retrying in a few seconds.`, "error");
    refreshTimer = setTimeout(() => loadOrder(id), REFRESH_MS);
    return;
  }

  showNotice(status, "");
  renderOrder(order);
  if (order.status !== "delivered" && order.status !== "cancelled") {
    refreshTimer = setTimeout(() => loadOrder(id), REFRESH_MS);
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
  const match = location.hash.match(/^#\/order\/([^/?#]+)$/);
  $("order-view").hidden = Boolean(match);
  $("track-view").hidden = !match;

  if (match) {
    $("track-body").hidden = true;
    showNotice($("track-status"), "Loading your order…");
    loadOrder(decodeURIComponent(match[1]));
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

$("order-form").addEventListener("submit", placeOrder);
window.addEventListener("hashchange", route);
route();
