# Deploying RepoViva to AWS (decision 063)

One EC2 instance runs `docker-compose.prod.yml`. Postgres is Neon, MongoDB is
Atlas, SQS and EventBridge are real AWS. Do the steps in order.

## 0. Pick one region

Everything goes in the same region: EC2, SQS, EventBridge, Neon and Atlas.
Otherwise every database call crosses continents. Choose one close to your
users where Neon and Atlas's free tier both exist, e.g. `ap-southeast-2`
(Sydney) or `ap-southeast-1` (Singapore). Set it in the console's top-right
region menu before creating anything.

## 1. Protect the account (5 min)

- **MFA on root:** top-right account menu → Security credentials → Assign MFA.
- **Budget alert:** Billing → Budgets → Create budget → "Monthly cost budget",
  $20, alerts to your email. The free plan can't overcharge you, but this
  tells you how fast the credit is going.

## 2. Databases outside AWS

**Neon (Postgres):**
1. Create a project in the chosen region.
2. Copy the connection string. Remove `&channel_binding=require` if present
   (asyncpg doesn't support it); keep `?sslmode=require`.
3. Core API needs the SQLAlchemy form, the other two the plain form:
   - Core API: `postgresql+psycopg://USER:PASS@HOST/DB?sslmode=require`
   - Repository and Evaluation: `postgresql://USER:PASS@HOST/DB?sslmode=require`

`pgvector` needs nothing: `repository-service/sql/schema.sql` creates the
extension at startup.

**MongoDB Atlas:**
1. Create a free M0 cluster in the chosen region.
2. Database Access → add a user with a password.
3. Network Access → add the EC2 instance's Elastic IP (step 5). Until then,
   leave it empty; don't use `0.0.0.0/0`.
4. Connect → Drivers → copy the `mongodb+srv://...` string.

## 3. Queues and event bus (CloudShell)

1. Open CloudShell (the `>_` icon at the top, or bottom-left of the console).
   It already has the AWS CLI and `jq`, and runs in the region you selected.
2. Actions → Upload file → `infra/aws/setup-messaging.sh`.
3. `bash setup-messaging.sh`
4. Copy the queue URLs it prints; they go into the `.env.prod` files.

Check: SQS console shows 12 queues (6 + their DLQs); EventBridge → Event
buses → `repoviva` has 3 rules.

## 4. IAM role for the instance

1. IAM → Roles → Create role → Trusted entity: AWS service, use case **EC2**.
2. Skip adding managed policies → name it `repoviva-ec2` → Create.
3. Open the role → Add permissions → Create inline policy → JSON → paste
   `infra/aws/ec2-role-policy.json`, replacing `REGION` and `ACCOUNT_ID`
   (12 digits, top-right account menu). Name it `repoviva-messaging`.

This is how the containers get AWS credentials. No access keys anywhere.

## 5. Launch the EC2 instance

EC2 → Launch instance:

| Setting | Value |
|---|---|
| Name | `repoviva` |
| AMI | Ubuntu Server 24.04 LTS, **64-bit (Arm)** |
| Instance type | `t4g.small` |
| Key pair | Create one (`.pem`), keep it safe |
| Network | Allow SSH from **My IP**; allow HTTP and HTTPS from the internet |
| Storage | 20 GiB gp3 |
| Advanced → IAM instance profile | `repoviva-ec2` |
| Advanced → Metadata response hop limit | **2** |

The hop limit matters: with the default of 1, code inside Docker containers
can't reach the instance's credentials and every SQS call fails.

Then give it a fixed address: EC2 → Elastic IPs → Allocate → Associate with
the instance. Without it, the IP (and so your domain and GitHub callback)
changes on every stop/start. Add this IP to Atlas's Network Access now.

Your domain: `<ip-with-dashes>.sslip.io`, e.g. `13-54-1-2.sslip.io`. It
resolves to your IP with no setup, and Caddy gets an HTTPS certificate for it.

## 6. GitHub OAuth app for production

GitHub → Settings → Developer settings → OAuth Apps → New:
- Homepage URL: `https://<domain>`
- Callback URL: `https://<domain>/v1/auth/github/callback`

Keep the dev app for local work; this one gets its own client ID and secret.

## 7. Prepare the instance

```bash
ssh -i repoviva.pem ubuntu@<elastic-ip>

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit   # log back in after this

# 2 GB swap: eight Python processes sit close to the 2 GB of RAM
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

git clone https://github.com/missLaiba22/RepoViva.git && cd RepoViva
```

(If the repo is private, use a GitHub personal access token as the password.)

## 8. The `.env.prod` files

All secrets go in **one** file; a script writes the four `.env.prod` files:

```bash
cp ~/RepoViva/infra/aws/secrets.env.example ~/repoviva-secrets.env
chmod 600 ~/repoviva-secrets.env
nano ~/repoviva-secrets.env          # replace every <paste>
python3 ~/RepoViva/infra/aws/make_env.py
```

The script fills in the queue URLs, region and domain, builds both database
URL forms from the one Neon string (dropping `channel_binding`, which asyncpg
rejects), and generates the internal secrets once into
`~/repoviva-generated.env`, so rerunning it never rotates keys. It prints key
names only. After changing a secret, rerun it and recreate the affected
containers (`up -d --force-recreate <service>`).

Before starting everything, test the MongoDB login on its own:

```bash
cd ~/RepoViva && docker compose -f docker-compose.prod.yml run --rm --no-deps voice-worker \
  python -c "import os,pymongo; pymongo.MongoClient(os.environ['MONGODB_URI'], serverSelectionTimeoutMS=8000).admin.command('ping'); print('MongoDB OK')"
```

`bad auth` means the password is wrong: replace Atlas's `<db_password>`
including the `< >`.

## 9. Start it

```bash
cd ~/RepoViva
echo DOMAIN=<ip-with-dashes>.sslip.io > .env   # compose reads it; gitignored
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f core-api core-worker
```

Open `https://<domain>`, log in with GitHub, add a small repository, run an
interview.

## Updating

```bash
cd RepoViva && git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Saving credit

- Stop the instance when not in use (EC2 → Instance state → Stop). You still
  pay for the disk and Elastic IP (~$5/month), not the compute.
- Never create a NAT Gateway or load balancer for this setup.
