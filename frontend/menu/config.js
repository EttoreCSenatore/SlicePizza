// Where the menu site finds the Orders API. No trailing slash.
//
// "/api" means "the same domain as this page": the web container (Caddy,
// infra/caddy/) forwards /api/* to the API, locally and in production. So the
// browser never calls another origin and the API needs no CORS (ADR 0003).
//
// To point the site at an API on another origin instead, put its full address
// here (e.g. "http://localhost:8000"), set EXTRA_CONNECT_SRC to that origin on
// the web container (the page's Content-Security-Policy blocks other origins
// otherwise) and allow this site's origin in the API's CORS_ORIGINS.
//
// telegramBot: the username of the Telegram bot behind "Follow on Telegram"
// (ADR 0006), without the @. The web container (Caddy) fills it in from its
// TELEGRAM_BOT_USERNAME setting when it serves this file; the `js` filter
// escapes it for a JavaScript string. Unset, or this file served without
// Caddy: the value is not a valid username and the page shows no button.
window.SLICEPIZZA_CONFIG = {
  apiUrl: "/api",
  telegramBot: '{{env "TELEGRAM_BOT_USERNAME" | js}}',
};
