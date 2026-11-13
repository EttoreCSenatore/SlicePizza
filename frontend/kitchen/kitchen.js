// Zé's Pizzeria kitchen board: plain JavaScript, no build step.
//
// Served at /kitchen/ behind the kitchen login (Caddy, ADR 0007). Its calls go
// to /kitchen/api/..., which Caddy forwards to the API with the kitchen token:
// this page never holds a token.
//
//   GET   api/orders                 the open orders, oldest first
//   PATCH api/orders/<id>/status     move one along
//
// The board refreshes every few seconds, and right away after every change.

"use strict";

const API = "api"; // relative to /kitchen/
const REFRESH_MS = 5_000;
const MAX_RETRY_MS = 60_000;
const LATE_AFTER_MINUTES = 30;
const TICKET_ERROR_MS = 15_000; // how long a ticket shows why a change failed

// One rail per open status, in the order an order moves through them.
const RAILS = {
  received: { next: "preparing", action: "Start preparing", canCancel: true },
  preparing: { next: "out_for_delivery", action: "Send out for delivery" },
  out_for_delivery: { next: "delivered", action: "Mark delivered" },
};

const DONE_MESSAGE = {
  preparing: "is in the oven",
  out_for_delivery: "is on its way",
  delivered: "was delivered",
  cancelled: "was cancelled",
};

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const clock = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });

const $ = (id) => document.getElementById(id);

const state = {
  orders: [],
  loadedAt: null,
  known: null, // ids on the board after the first load; null before it
  fresh: new Set(), // ids that just arrived: highlighted once
  busy: new Set(), // ids with a change in flight
  confirmingCancel: null, // the id whose "cancel?" question is open
  ticketError: new Map(), // id -> { message, until }, shown on that ticket
  failures: 0,
  timer: null,
  drawn: "", // what the tickets on screen were drawn from (see render)
  notice: null, // { message, until }: about an order no longer on the board
};

// --- API ----------------------------------------------------------------------

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function api(method, path, body) {
  let response;
  try {
    response = await fetch(`${API}${path}`, {
      method,
      headers: body
        ? { "Content-Type": "application/json", Accept: "application/json" }
        : { Accept: "application/json" },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Can't reach the pizzeria's system. Check the connection.", 0);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    // Some errors (from Caddy) have no JSON body.
  }
  if (response.ok) return data;
  const detail = typeof data?.detail === "string" ? data.detail : "";
  if (response.status === 401 || response.status === 503) {
    throw new ApiError(
      "The kitchen isn't connected to the orders. Whoever runs the server should " +
        "check KITCHEN_API_TOKEN: it must be set, and the same, on the web and api containers.",
      response.status,
    );
  }
  if (response.status >= 500) {
    throw new ApiError("The pizzeria's system is offline for a moment.", response.status);
  }
  throw new ApiError(detail || `Something went wrong (error ${response.status}).`, response.status);
}

// --- Loading ------------------------------------------------------------------

async function refresh() {
  clearTimeout(state.timer);
  try {
    const orders = await api("GET", "/orders");
    noteArrivals(orders);
    state.orders = orders;
    state.loadedAt = new Date();
    state.failures = 0;
    showProblem("");
  } catch (error) {
    state.failures += 1;
    const since = state.loadedAt ? ` Showing the orders from ${clock.format(state.loadedAt)}.` : "";
    showProblem(`${error.message}${since}`);
  }
  render();
  schedule();
}

function schedule() {
  clearTimeout(state.timer);
  if (document.hidden) return; // picked up again by visibilitychange
  // After errors, wait longer each time (up to a minute) instead of hammering.
  const delay = Math.min(REFRESH_MS * 2 ** state.failures, MAX_RETRY_MS);
  state.timer = setTimeout(refresh, delay);
}

function noteArrivals(orders) {
  const ids = new Set(orders.map((o) => o.id));
  if (state.known) {
    const arrived = orders.filter((o) => !state.known.has(o.id));
    for (const order of arrived) state.fresh.add(order.id);
    if (arrived.length === 1) announce(`New order from ${arrived[0].customer_name}.`);
    else if (arrived.length > 1) announce(`${arrived.length} new orders.`);
  }
  state.known = ids;
}

// --- Changing a status --------------------------------------------------------

async function move(order, next) {
  state.busy.add(order.id);
  state.ticketError.delete(order.id);
  state.confirmingCancel = null;
  render();
  try {
    await api("PATCH", `/orders/${encodeURIComponent(order.id)}/status`, { status: next });
    announce(`Order ${shortId(order.id)} ${DONE_MESSAGE[next]}.`);
  } catch (error) {
    // 409: someone else moved it first; 404: it's gone. The refresh below
    // shows where it is now.
    state.ticketError.set(order.id, {
      message: error.status === 409 ? "Someone already changed this order. Here is where it is now." : error.message,
      until: Date.now() + TICKET_ERROR_MS,
    });
  } finally {
    state.busy.delete(order.id);
  }
  await refresh();
  // A failed change on an order that has left the board (cancelled or
  // delivered on another screen): say so above the rails, since its ticket,
  // where the message would go, is gone.
  if (state.ticketError.has(order.id) && !state.orders.some((o) => o.id === order.id)) {
    state.ticketError.delete(order.id);
    state.notice = {
      message: `Order #${shortId(order.id)} (${order.customer_name}) was already changed on another screen and is no longer open.`,
      until: Date.now() + TICKET_ERROR_MS,
    };
    render();
  }
}

// --- Rendering ----------------------------------------------------------------

function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value === false || value == null) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  // Text from the API always goes in as text, never as HTML.
  node.append(...children.filter((child) => child !== null && child !== ""));
  return node;
}

const shortId = (id) => id.slice(0, 8);

function placedAt(order) {
  // The API sends ISO 8601 with an offset; a bare one (SQLite in development)
  // is UTC.
  const text = /[zZ]|[+-]\d\d:?\d\d$/.test(order.created_at) ? order.created_at : `${order.created_at}Z`;
  return new Date(text);
}

function waiting(order, now) {
  const minutes = Math.max(0, Math.floor((now - placedAt(order)) / 60_000));
  if (minutes < 1) return { minutes, label: "now" };
  if (minutes < 60) return { minutes, label: `${minutes} min` };
  const hours = Math.floor(minutes / 60);
  return { minutes, label: `${hours} h ${String(minutes % 60).padStart(2, "0")}` };
}

function ticket(order, now) {
  const rail = RAILS[order.status];
  const busy = state.busy.has(order.id);
  const age = waiting(order, now);
  const late = age.minutes >= LATE_AFTER_MINUTES;
  const confirming = state.confirmingCancel === order.id;
  const error = state.ticketError.get(order.id)?.message;

  const actions = confirming
    ? el(
        "div",
        { class: "ticket-actions is-confirming", role: "group", "aria-label": "Cancel this order?" },
        el("p", { class: "confirm-question" }, "Cancel this order? The customer will see it as cancelled."),
        el(
          "button",
          { type: "button", class: "btn btn-danger", "data-key": `${order.id}:cancel-yes`, disabled: busy, onclick: () => move(order, "cancelled") },
          "Yes, cancel it",
        ),
        el(
          "button",
          { type: "button", class: "btn btn-quiet", "data-key": `${order.id}:cancel-no`, onclick: () => { state.confirmingCancel = null; render(order.id + ":cancel"); } },
          "Keep it",
        ),
      )
    : el(
        "div",
        { class: "ticket-actions" },
        el(
          "button",
          { type: "button", class: "btn btn-go", "data-key": `${order.id}:next`, disabled: busy, onclick: () => move(order, rail.next) },
          busy ? "Saving…" : rail.action,
        ),
        rail.canCancel
          ? el(
              "button",
              { type: "button", class: "btn btn-quiet", "data-key": `${order.id}:cancel`, disabled: busy, onclick: () => { state.confirmingCancel = order.id; render(order.id + ":cancel-no"); } },
              "Cancel",
            )
          : null,
      );

  return el(
    "li",
    { class: ["ticket", late && "is-late", state.fresh.has(order.id) && "is-fresh"].filter(Boolean).join(" ") },
    el(
      "div",
      { class: "ticket-head" },
      el("p", { class: "ticket-age", title: `Placed at ${clock.format(placedAt(order))}` }, age.label),
      el(
        "p",
        { class: "ticket-meta" },
        el("span", { class: "ticket-id", title: order.id }, `#${shortId(order.id)}`),
        el("span", {}, `placed ${clock.format(placedAt(order))}`),
      ),
    ),
    el(
      "ul",
      { class: "ticket-items" },
      ...order.items.map((item) =>
        el("li", {}, el("span", { class: "qty" }, `${item.quantity}×`), " ", item.pizza_name),
      ),
    ),
    el(
      "dl",
      { class: "ticket-customer" },
      el("dt", {}, "For"),
      el("dd", {}, order.customer_name),
      el("dt", {}, "Phone"),
      el("dd", {}, el("a", { href: `tel:${order.customer_phone.replace(/[^\d+]/g, "")}` }, order.customer_phone)),
      el("dt", {}, "Deliver to"),
      el("dd", {}, order.delivery_address),
      el("dt", {}, "Total"),
      el("dd", {}, money.format(order.total_cents / 100)),
    ),
    error ? el("p", { class: "ticket-error", role: "status" }, error) : null,
    actions,
  );
}

// focusKey: put the keyboard focus on this control after rendering (when a
// button that had it is replaced). Otherwise, whatever had the focus keeps it.
function render(focusKey) {
  const keep = focusKey || document.activeElement?.dataset?.key;
  const now = new Date();
  for (const [id, { until }] of state.ticketError) {
    if (until <= now.getTime()) state.ticketError.delete(id);
  }
  if (state.notice && state.notice.until <= now.getTime()) state.notice = null;
  $("notice").textContent = state.notice?.message || "";
  $("notice").hidden = !state.notice;

  if (state.loadedAt) {
    $("updated").textContent = `Updated ${clock.format(state.loadedAt)}`;
  } else if (state.failures) {
    $("updated").textContent = "No orders loaded yet";
  }
  // Rebuild the tickets only when something on them changed (the data, a
  // minute passing, a button's state). Replacing them on every refresh could
  // swallow a tap that lands during it.
  const signature = JSON.stringify([
    state.orders,
    Math.floor(now / 60_000),
    [...state.busy],
    state.confirmingCancel,
    [...state.ticketError],
    [...state.fresh],
    Boolean(state.loadedAt),
  ]);
  if (signature === state.drawn && !focusKey) return;
  state.drawn = signature;

  for (const section of document.querySelectorAll(".rail")) {
    const status = section.dataset.status;
    const orders = state.orders.filter((o) => o.status === status);
    section.querySelector("[data-tickets]").replaceChildren(...orders.map((o) => ticket(o, now)));
    section.querySelector("[data-count]").textContent = state.loadedAt ? `(${orders.length})` : "";
    section.querySelector("[data-empty]").hidden = !state.loadedAt || orders.length > 0;
  }
  state.fresh.clear(); // the highlight plays once, on the render that adds it

  if (keep) {
    const target = document.querySelector(`[data-key="${CSS.escape(keep)}"]`);
    if (target && !target.disabled) target.focus();
  }
}

function showProblem(message) {
  $("problem").textContent = message;
  $("problem").hidden = !message;
}

function announce(message) {
  $("announce").textContent = message;
}

// --- Start --------------------------------------------------------------------

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});

refresh();
