#!/bin/bash
# SmartSelect deploy: Ubuntu (apt) or OpenCloudOS/CentOS/RHEL (yum/dnf)
# Usage: sudo bash deploy.sh
# After Windows SCP, CRLF is stripped automatically.

set -e
SELF="${BASH_SOURCE[0]}"
# Windows SCP may leave CRLF (error: #!/bin/bash: No such file or directory)
if command -v grep &>/dev/null && grep -q $'\r' "$SELF" 2>/dev/null; then
    sed -i 's/\r$//' "$SELF"
    exec /bin/bash "$SELF" "$@"
fi

DOMAIN="codecraftsure.com"
APP_DIR="/opt/smartselect"
APP_USER="smartselect"
PYTHON_BIN="python3"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo " SmartSelect deploy - $DOMAIN"
echo "========================================"

# --- detect package manager ---
if command -v apt-get &>/dev/null; then
    OS_FLAVOR="debian"
elif command -v dnf &>/dev/null; then
    OS_FLAVOR="rhel"
    PKG_BIN="dnf"
elif command -v yum &>/dev/null; then
    OS_FLAVOR="rhel"
    PKG_BIN="yum"
else
    echo "ERROR: need apt-get (Ubuntu/Debian) or yum/dnf (OpenCloudOS/CentOS)."
    exit 1
fi
echo "Detected OS: $OS_FLAVOR ($([ "$OS_FLAVOR" = debian ] && echo apt-get || echo $PKG_BIN))"

# --- [1] packages ---
echo "[1/8] Installing packages..."
if [ "$OS_FLAVOR" = debian ]; then
    apt-get update -qq
    apt-get install -y -qq \
        python3 python3-pip python3-venv python3-dev \
        nginx certbot python3-certbot-nginx \
        git curl wget ca-certificates dnsutils \
        build-essential libfreetype6-dev libpng-dev pkg-config \
        > /dev/null
else
    $PKG_BIN install -y git curl wget ca-certificates nginx python3 python3-pip \
        python3-devel gcc make openssl-devel libffi-devel bind-utils \
        > /dev/null
    $PKG_BIN install -y epel-release > /dev/null 2>&1 || true
    $PKG_BIN install -y certbot python3-certbot-nginx > /dev/null 2>&1 || true
fi

echo "[2/8] User $APP_USER..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
fi

echo "[3/8] Sync code..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git fetch origin master 2>/dev/null || true
    git reset --hard origin/master 2>/dev/null || true
else
    if [ ! -d "$APP_DIR" ] || [ -z "$(ls -A "$APP_DIR" 2>/dev/null)" ]; then
        git clone https://github.com/lcfReact/SmartSelect.git "$APP_DIR" || {
            echo "git clone failed (GitHub blocked?). Copy project to $APP_DIR via scp and re-run."
            exit 1
        }
    fi
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
cd "$APP_DIR"

echo "[4/8] venv + pip..."
if [ ! -x "$VENV_DIR/bin/python" ]; then
    sudo -u "$APP_USER" $PYTHON_BIN -m venv "$VENV_DIR" 2>/dev/null || {
        if [ "$OS_FLAVOR" = rhel ]; then
            $PKG_BIN install -y python3-virtualenv > /dev/null 2>&1 || true
        fi
        sudo -u "$APP_USER" $PYTHON_BIN -m venv "$VENV_DIR"
    }
fi
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip -q
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r requirements-server.txt -q

echo "[5/8] database..."
sudo -u "$APP_USER" "$VENV_DIR/bin/python" -c "
from src.database.db_manager import DatabaseManager
db = DatabaseManager()
db.initialize()
print('Database OK')
"

echo "[6/8] systemd..."
cat > /etc/systemd/system/smartselect.service << EOF
[Unit]
Description=SmartSelect Web Service
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR/server
ExecStart=$VENV_DIR/bin/python app.py
Restart=always
RestartSec=5
Environment=PORT=8000
Environment=PYTHONPATH=$APP_DIR
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable smartselect
systemctl restart smartselect
echo "systemd OK"

# --- nginx: Debian uses sites-available; RHEL/OpenCloudOS uses conf.d ---
echo "[7/8] nginx (HTTP)..."
NGINX_BLOCK=$(cat << NGINX_EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location /ws/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection "Upgrade";
        proxy_set_header   Host \$host;
        proxy_read_timeout 86400s;
    }

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
}
NGINX_EOF
)

mkdir -p /var/www/certbot
if [ "$OS_FLAVOR" = debian ]; then
    printf '%s\n' "$NGINX_BLOCK" > /etc/nginx/sites-available/smartselect
    ln -sf /etc/nginx/sites-available/smartselect /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
else
    printf '%s\n' "$NGINX_BLOCK" > /etc/nginx/conf.d/smartselect.conf
    rm -f /etc/nginx/conf.d/default.conf 2>/dev/null || true
fi
nginx -t
systemctl reload nginx 2>/dev/null || systemctl restart nginx

echo "[8/8] certbot (if DNS points here)..."
SERVER_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || curl -s ip.sb 2>/dev/null || echo "")
DOMAIN_IP=$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)
if [ -z "$DOMAIN_IP" ]; then
    DOMAIN_IP=$(host "$DOMAIN" 2>/dev/null | awk '/has address/ { print $4 }' | head -1 || true)
fi

if [ -n "$SERVER_IP" ] && [ "$SERVER_IP" = "$DOMAIN_IP" ] && [ -n "$DOMAIN_IP" ]; then
    certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
        --non-interactive --agree-tos --email "admin@$DOMAIN" \
        --redirect 2>/dev/null || echo "certbot failed; run manually later."
    if [ "$OS_FLAVOR" = debian ] && [ -f /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem ]; then
        cat > /etc/nginx/sites-available/smartselect << 'EOF2'
server {
    listen 80;
    server_name PLACEHOLDER_DOMAIN www.PLACEHOLDER_DOMAIN;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl http2;
    server_name PLACEHOLDER_DOMAIN www.PLACEHOLDER_DOMAIN;
    ssl_certificate     /etc/letsencrypt/live/PLACEHOLDER_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/PLACEHOLDER_DOMAIN/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    location /ws/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "Upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400s;
    }
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
}
EOF2
        sed -i "s/PLACEHOLDER_DOMAIN/$DOMAIN/g" /etc/nginx/sites-available/smartselect
        nginx -t && systemctl reload nginx
    fi
else
    echo "DNS for $DOMAIN -> $DOMAIN_IP (server IP: $SERVER_IP). Skip auto-certbot."
    echo "Later: sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN --redirect"
fi

echo "Done. http://$SERVER_IP  http://$DOMAIN"
