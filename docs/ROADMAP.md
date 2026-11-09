# Roadmap

Each phase starts with a **request from Zé**, the pizzeria owner. The request is the problem; the tasks are the solution; the **definition of done** tells you when the phase is over.

Check the boxes as you make progress.

---

## Phase 1: "I want to see it running on your computer"

**Goal:** the orders API running locally, in containers, saving to the database.

- [x] Initial repository structure and documentation
- [ ] API with `GET /health` and `GET /menu` (menu hardcoded, to start)
- [ ] First automated test with pytest
- [ ] Dockerfile for the API
- [ ] `docker-compose.yml` with API + Postgres
- [ ] `.env.example` with the database variables (the real `.env` never goes into Git)
- [ ] Connect the API to Postgres (suggestion: SQLAlchemy or psycopg)
- [ ] Create the `pizzas` and `orders` tables
- [ ] Move the menu into the database
- [ ] `POST /orders`: create an order
- [ ] `GET /orders/{id}`: get an order
- [ ] `PATCH /orders/{id}/status`: change the status (`received` → `preparing` → `out_for_delivery` → `delivered`)
- [ ] Tests for the new routes

**Done when:** `docker compose up` brings everything up from scratch, and an order you created is still saved after `docker compose down` + `docker compose up`.

**You learn:** Python, SQL, Git, Docker, volumes and container networking.

---

## Phase 2: "I want the site live on my own domain"

**Goal:** the system reachable from the internet, over HTTPS, on your domain.

- [ ] Register a domain (e.g. Registro.br, Cloudflare or Namecheap)
- [ ] Create a cloud virtual machine (AWS EC2 or Oracle Cloud Free Tier)
- [ ] Set up SSH access with a key (no password)
- [ ] Open only ports 22, 80 and 443 in the firewall
- [ ] Install Docker on the virtual machine
- [ ] Build the menu website in `frontend/` (plain HTML + JS)
- [ ] Host the static site on a CDN (Cloudflare Pages or S3 + CloudFront)
- [ ] DNS: `www` (CNAME to the CDN), `api` and `admin` (A record to the virtual machine)
- [ ] Caddy as reverse proxy, with automatic HTTPS

**Done when:** you place an order from your phone, over HTTPS, through the internet.

**You learn:** DNS, SSH, firewalls, reverse proxies, TLS and CDNs.

---

## Phase 3: "Customers want to know when their pizza is on the way"

**Goal:** notify the customer on every status change, without slowing down the API.

- [ ] Add RabbitMQ to `docker-compose.yml`
- [ ] The API publishes an event to the queue when an order's status changes
- [ ] Create the worker in `worker/` that consumes the queue
- [ ] Create a Telegram bot and send the notification from the worker
- [ ] Build the kitchen dashboard (`admin.yourdomain.com`)

**Done when:** if you take the worker down, messages wait in the queue and are sent when it comes back.

**You learn:** asynchronous systems, queues and services talking to each other.

---

## Phase 4: "Every time you change something, something breaks"

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

**Goal:** close the most obvious doors.

- [ ] Passwords and keys in a secrets manager
- [ ] Scan images for vulnerabilities with Trivy in the pipeline
- [ ] Limit requests per client on the API (rate limiting)
- [ ] Containers running as a non-root user
- [ ] Review IAM permissions

**You learn:** the basics of DevSecOps.
