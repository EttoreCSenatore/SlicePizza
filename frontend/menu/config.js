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
window.SLICEPIZZA_CONFIG = {
  apiUrl: "/api",
};
