#!/bin/bash
# SmartSelect full deploy (Ubuntu): nginx sites-available, certbot, app user
# Usage: chmod +x deploy.sh && sudo bash deploy.sh
set -e

DOMAIN="codecraftsure.com"
APP_DIR="/opt/smartselect"
APP_USER="smartselect"
PYTHON_BIN="python3"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo " SmartSelect deploy - $DOMAIN"
echo "========================================"

echo "[1/8] apt packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    nginx certbot python3-certbot-nginx \
    git curl wget build-essential \
    libfreetype6-dev libpng-dev pkg-config \
    > /dev/null

echo "[2/8] user $APP_USER..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
fi

echo "[3/8] sync code..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git fetch origin master
    git reset --hard origin/master
else
    git clone https://github.com/lcfReact/SmartSelect.git "$APP_DIR"
    chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
fi
cd "$APP_DIR"

echo "[4/8] venv + pip..."
sudo -u "$APP_USER" $PYTHON_BIN -m venv "$VENV_DIR"
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

echo "[7/8] nginx (HTTP)..."
cat > /etc/nginx/sites-available/smartselect << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
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
}
EOF
ln -sf /etc/nginx/sites-available/smartselect /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "[8/8] certbot (if DNS points here)..."
mkdir -p /var/www/certbot
SERVER_IP=$(curl -s ifconfig.me)
DOMAIN_IP=$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)
if [ -z "$DOMAIN_IP" ]; then
    DOMAIN_IP=$(host "$DOMAIN" 2>/dev/null | awk '/has address/ { print $4 }' | head -1 || true)
fi

if [ "$SERVER_IP" = "$DOMAIN_IP" ] && [ -n "$DOMAIN_IP" ]; then
    certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
        --non-interactive --agree-tos --email "admin@$DOMAIN" \
        --redirect || true
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
else
    echo "DNS for $DOMAIN not pointing to $SERVER_IP yet (resolved: $DOMAIN_IP). Run certbot later."
fi

echo "Done. http://$SERVER_IP  http://$DOMAIN"
