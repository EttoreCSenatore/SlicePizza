# Roadmap

Each phase starts with a **request from Zé**, the pizzeria owner. The request is the problem; the tasks are the solution; the **definition of done** tells you when the phase is over.

Check the boxes as you make progress, and keep each phase's **Status** line in step with the roadmap table in the [README](../README.md#roadmap): ✅ Done, 🚧 In progress or ⏳ Not started.

---

## Phase 1: "I want to see it running on your computer"

**Status:** ✅ Done

**Goal:** the orders API running locally, in containers, saving to the database.

- [x] Initial repository structure and documentation
- [x] API with `GET /health` and `GET /menu` (menu hardcoded, to start)
- [x] First automated test with pytest
- [x] Dockerfile for the API
- [x] `docker-compose.yml` with API + Postgres
- [x] `.env.example` with the database variables (the real `.env` never goes into Git)
- [x] Connect the API to Postgres (suggestion: SQLAlchemy or psycopg)
- [x] Create the `pizzas` and `orders` tables
- [x] Move the menu into the database
- [x] `POST /orders`: create an order
- [x] `GET /orders/{id}`: get an order
- [x] `PATCH /orders/{id}/status`: change the status (`received` → `preparing` → `out_for_delivery` → `delivered`)
- [x] Tests for the new routes

**Done when:** `docker compose up` brings everything up from scratch, and an order you created is still saved after `docker compose down` + `docker compose up`.

**You learn:** Python, SQL, Git, Docker, volumes and container networking.

---

## Phase 2: "I want the site live on my own domain"

**Status:** 🚧 In progress

**Goal:** the system reachable from the internet, over HTTPS, on your domain.

- [ ] Register a domain (e.g. Registro.br, Cloudflare or Namecheap)
- [ ] Create a cloud virtual machine (AWS EC2 or Oracle Cloud Free Tier)
- [ ] Set up SSH access with a key (no password)
- [ ] Open only ports 22, 80 and 443 in the firewall
- [ ] Install Docker on the virtual machine
- [x] Build the menu website in `frontend/` (plain HTML + JS)
- [ ] Host the static site on a CDN (Cloudflare Pages or S3 + CloudFront)
- [ ] DNS: `www` (CNAME to the CDN), `api` and `admin` (A record to the virtual machine)
- [ ] Caddy as reverse proxy, with automatic HTTPS

> **How SlicePizza did it:** the system lives at `slicepizza.senatore.tech` on a shared server that already has a domain, Docker and an HTTPS proxy (Dokploy, see [DEPLOY.md](DEPLOY.md)). Instead of a CDN plus `api` and `admin` subdomains, a Caddy container serves the site at `/` and the API at `/api` on that one domain ([ADR 0003](adr/0003-one-domain-caddy-in-front.md)). The server's proxy keeps the HTTPS part.

**Done when:** you place an order from your phone, over HTTPS, through the internet.

**You learn:** DNS, SSH, firewalls, reverse proxies, TLS and CDNs.

---

## Phase 3: "Customers want to know when their pizza is on the way"

**Status:** 🚧 In progress: everything is built and passes CI (including the "done when" below); it goes live with the server switch that finishes Phase 2

**Goal:** notify the customer on every status change, without slowing down the API.

- [x] Add RabbitMQ to `docker-compose.yml`
- [x] The API publishes an event to the queue when an order's status changes (through an outbox, [ADR 0004](adr/0004-order-events-outbox-rabbitmq.md))
- [x] Create the worker in `worker/` that consumes the queue ([ADR 0005](adr/0005-notification-worker.md))
- [x] Create a Telegram bot and send the notification from the worker: to the pizzeria chat, and to customers who tap "Follow on Telegram" on their order page ([ADR 0006](adr/0006-customer-telegram-opt-in.md))
- [x] Build the kitchen dashboard: the kitchen board at `/kitchen`, behind a login; changing a status is now the kitchen's only ([ADR 0007](adr/0007-kitchen-login.md))

**Done when:** if you take the worker down, messages wait in the queue and are sent when it comes back.

**You learn:** asynchronous systems, queues and services talking to each other.

---

## Phase 4: "Every time you change something, something breaks"

**Status:** ⏳ Not started

**Goal:** all code goes through automated tests before reaching production.

- [ ] GitHub Actions pipeline: lint → tests → image build
- [ ] Publish images to GHCR (GitHub's container registry)
- [ ] Automatic deploy to the virtual machine after merging into `main`
- [ ] Staging environment at `staging.yourdomain.com`
- [ ] Secrets stored in GitHub Secrets

**Done when:** a merge into `main` puts the new version in production without you logging into the server.

**You learn:** CI/CD, separate environments, secrets and image versioning.

---

## Phase 5: "The site went down Friday night and nobody noticed"

**Status:** ⏳ Not started

**Goal:** know something broke before a customer complains.

- [ ] `/health` route on every service
- [ ] Expose API metrics to Prometheus (orders per minute, latency, errors)
- [ ] Grafana dashboards
- [ ] Centralize container logs in Loki
- [ ] Telegram alerts: API down, queue piling up

**Done when:** you take the API down on purpose and get the alert within 2 minutes.

**You learn:** observability, metrics, logs and alerting.

---

## Phase 6: "The server died and we lost the orders"

**Status:** ⏳ Not started

**Goal:** be able to rebuild everything from scratch, with the data, quickly.

- [ ] Daily Postgres backup, encrypted, uploaded to S3
- [ ] Retention rule on S3 (e.g. keep 30 days)
- [ ] Test restoring the backup
- [ ] Terraform in `infra/terraform/`: network, virtual machine, firewall, DNS records
- [ ] Ansible in `infra/ansible/`: install Docker and configure the server
- [ ] IAM user with least privilege for the backup

**Done when:** `terraform destroy`, then `terraform apply`, restore the backup, and everything is back in under 30 minutes.

**You learn:** infrastructure as code (IaC), disaster recovery and IAM.

---

## Phase 7: "We're running a R$20 pizza promo on Friday"

**Status:** ⏳ Not started

**Goal:** handle much more traffic without going down.

- [ ] Load test with k6 to find the bottleneck
- [ ] Cache the menu in Redis
- [ ] Pizza photos on S3 with a CDN
- [ ] Migrate to Kubernetes (k3s) with manifests in `infra/k8s/`
- [ ] Ingress + cert-manager (automatic HTTPS)
- [ ] Autoscaling with HPA
- [ ] Package with Helm

**Done when:** the system handles 10 times the normal traffic without errors.

**You learn:** scalability, caching, Kubernetes and load testing.

---

## Phase 8 (bonus): "I heard hackers attack pizzerias"

**Status:** ⏳ Not started

**Goal:** close the most obvious doors.

- [ ] Passwords and keys in a secrets manager
- [ ] Scan images for vulnerabilities with Trivy in the pipeline
- [ ] Limit requests per client on the API (rate limiting)
- [ ] Containers running as a non-root user
- [ ] Review IAM permissions

**You learn:** the basics of DevSecOps.
