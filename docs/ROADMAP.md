# Roadmap

Cada fase começa com um **pedido do Zé**, o dono da pizzaria. O pedido é o problema; as tarefas são a solução; o **critério de pronto** diz quando a fase acabou.

Marque as caixas conforme for avançando.

---

## Fase 1: "Quero ver funcionando no seu computador"

**Objetivo:** API de pedidos rodando localmente, em containers, salvando no banco.

- [x] Estrutura inicial do repositório e documentação
- [ ] API com `GET /health` e `GET /cardapio` (cardápio fixo no código, para começar)
- [ ] Primeiro teste automatizado com pytest
- [ ] Dockerfile da API
- [ ] `docker-compose.yml` com API + Postgres
- [ ] `.env.example` com as variáveis do banco (o `.env` real nunca vai para o Git)
- [ ] Conectar a API ao Postgres (sugestão: SQLAlchemy ou psycopg)
- [ ] Criar as tabelas `pizzas` e `pedidos`
- [ ] Mover o cardápio para o banco
- [ ] `POST /pedidos`: criar um pedido
- [ ] `GET /pedidos/{id}`: consultar um pedido
- [ ] `PATCH /pedidos/{id}/status`: mudar o status (`recebido` → `em_preparo` → `saiu_para_entrega` → `entregue`)
- [ ] Testes para as novas rotas

**Pronto quando:** `docker compose up` sobe tudo do zero e um pedido criado continua salvo depois de `docker compose down` + `docker compose up`.

**Você aprende:** Python, SQL, Git, Docker, volumes e redes entre containers.

---

## Fase 2: "Quero o site no ar com o meu domínio"

**Objetivo:** sistema acessível pela internet, com HTTPS, no seu domínio.

- [ ] Registrar um domínio (Registro.br ou Cloudflare)
- [ ] Criar uma máquina virtual na nuvem (AWS EC2 ou Oracle Cloud Free Tier)
- [ ] Configurar acesso por SSH com chave (sem senha)
- [ ] Liberar só as portas 22, 80 e 443 no firewall
- [ ] Instalar o Docker na máquina virtual
- [ ] Criar o site do cardápio em `frontend/` (HTML + JS simples)
- [ ] Hospedar o site estático em CDN (Cloudflare Pages ou S3 + CloudFront)
- [ ] DNS: `www` (CNAME para a CDN), `api` e `admin` (registro A para a máquina virtual)
- [ ] Caddy como proxy reverso, com HTTPS automático

**Pronto quando:** você faz um pedido pelo celular, com HTTPS, pela internet.

**Você aprende:** DNS, SSH, firewall, proxy reverso, TLS e CDN.

---

## Fase 3: "O cliente quer saber quando a pizza sai"

**Objetivo:** avisar o cliente a cada mudança de status, sem travar a API.

- [ ] Adicionar o RabbitMQ ao `docker-compose.yml`
- [ ] API publica um evento na fila quando o status do pedido muda
- [ ] Criar o worker em `worker/` que consome a fila
- [ ] Criar um bot no Telegram e enviar a notificação pelo worker
- [ ] Criar o painel da cozinha (`admin.seudominio.com.br`)

**Pronto quando:** se você derrubar o worker, as mensagens ficam na fila e são enviadas quando ele volta.

**Você aprende:** sistemas assíncronos, filas e serviços que conversam entre si.

---

## Fase 4: "Toda vez que você mexe, alguma coisa quebra"

**Objetivo:** todo código passa por testes automáticos antes de ir para produção.

- [ ] Pipeline no GitHub Actions: lint → testes → build da imagem
- [ ] Publicar as imagens no GHCR (registry de imagens do GitHub)
- [ ] Deploy automático na máquina virtual depois do merge na `main`
- [ ] Ambiente de homologação em `staging.seudominio.com.br`
- [ ] Segredos guardados no GitHub Secrets

**Pronto quando:** um merge na `main` coloca a nova versão em produção sem você entrar no servidor.

**Você aprende:** CI/CD, ambientes separados, segredos e versionamento de imagens.

---

## Fase 5: "O site caiu sexta à noite e ninguém percebeu"

**Objetivo:** saber que algo quebrou antes do cliente reclamar.

- [ ] Rota `/health` em todos os serviços
- [ ] Expor métricas da API para o Prometheus (pedidos por minuto, latência, erros)
- [ ] Painéis no Grafana
- [ ] Centralizar os logs dos containers no Loki
- [ ] Alertas no Telegram: API fora do ar, fila acumulando mensagens

**Pronto quando:** você derruba a API de propósito e recebe o alerta em até 2 minutos.

**Você aprende:** observabilidade, métricas, logs e alertas.

---

## Fase 6: "O servidor morreu e perdemos os pedidos"

**Objetivo:** conseguir recriar tudo do zero, com os dados, em pouco tempo.

- [ ] Backup diário do Postgres, criptografado, enviado para o S3
- [ ] Regra de retenção no S3 (ex.: manter 30 dias)
- [ ] Testar a restauração do backup
- [ ] Terraform em `infra/terraform/`: rede, máquina virtual, firewall, registros DNS
- [ ] Ansible em `infra/ansible/`: instalar Docker e configurar o servidor
- [ ] Usuário IAM com permissão mínima para o backup

**Pronto quando:** `terraform destroy`, depois `terraform apply`, restaurar o backup e tudo volta em menos de 30 minutos.

**Você aprende:** infraestrutura como código (IaC), recuperação de desastre e IAM.

---

## Fase 7: "Vamos fazer promoção de pizza a R$ 20 na sexta"

**Objetivo:** aguentar muito mais acesso sem cair.

- [ ] Teste de carga com k6 para descobrir o gargalo
- [ ] Cache do cardápio no Redis
- [ ] Fotos das pizzas no S3 com CDN
- [ ] Migrar para Kubernetes (k3s) com manifests em `infra/k8s/`
- [ ] Ingress + cert-manager (HTTPS automático)
- [ ] Autoescala com HPA
- [ ] Empacotar com Helm

**Pronto quando:** o sistema aguenta 10 vezes o tráfego normal sem erro.

**Você aprende:** escalabilidade, cache, Kubernetes e testes de carga.

---

## Fase 8 (bônus): "Ouvi falar que hackers atacam pizzarias"

**Objetivo:** fechar as portas mais óbvias.

- [ ] Senhas e chaves em um gerenciador de segredos
- [ ] Verificar vulnerabilidades das imagens com Trivy no pipeline
- [ ] Limitar requisições por cliente na API (rate limit)
- [ ] Containers rodando sem usuário root
- [ ] Revisar permissões IAM

**Você aprende:** o básico de DevSecOps.
