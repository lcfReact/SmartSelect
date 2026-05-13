#!/bin/bash
# SmartSelect quick install (OpenCloudOS / CentOS / Ubuntu)
# Syncs repo with: git fetch + reset --hard (avoids local-change merge errors)
set -e
SELF="${BASH_SOURCE[0]}"
if command -v grep &>/dev/null && grep -q $'\r' "$SELF" 2>/dev/null; then
    sed -i 's/\r$//' "$SELF"
    exec /bin/bash "$SELF" "$@"
fi

DOMAIN="codecraftsure.com"
APP_DIR="/opt/smartselect"
APP_USER="smartselect"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo " SmartSelect quick install - $DOMAIN"
echo "========================================"

# 1) Base packages
echo "[1/7] Installing base tools..."
if command -v yum &>/dev/null; then
    PKG="yum"
    yum install -y git curl wget python3 python3-pip nginx \
        python3-devel gcc make openssl-devel libffi-devel > /dev/null
    yum install -y epel-release > /dev/null 2>&1 || true
    yum install -y certbot python3-certbot-nginx > /dev/null 2>&1 || true
elif command -v apt-get &>/dev/null; then
    PKG="apt"
    apt-get update -qq
    apt-get install -y -qq git curl wget python3 python3-pip python3-venv \
        nginx certbot python3-certbot-nginx > /dev/null
else
    echo "Unsupported package manager. Install git/python3/nginx manually."
    exit 1
fi
echo "Base tools OK (git, python3, nginx)"

# 2) Code: clone or hard-reset to remote (no merge conflicts)
echo "[2/7] Syncing code..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git fetch origin master
    git reset --hard origin/master
else
    git clone https://github.com/lcfReact/SmartSelect.git "$APP_DIR"
fi
echo "Code ready: $APP_DIR"

# 3) Service user (optional; service still runs as root in this script)
echo "[3/7] Service user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER" 2>/dev/null || true
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR" 2>/dev/null || true

# 4) venv + pip deps
echo "[4/7] Python deps (may take several minutes)..."
cd "$APP_DIR"
python3 -m venv "$VENV_DIR" 2>/dev/null || {
    if [ "${PKG:-}" = "yum" ]; then
        yum install -y python3-virtualenv > /dev/null
    fi
    python3 -m venv "$VENV_DIR"
}
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r requirements-server.txt -q
echo "Python deps OK"

# 5) DB init
echo "[5/7] Database init..."
"$VENV_DIR/bin/python" -c "
import sys
sys.path.insert(0, '$APP_DIR')
from src.database.db_manager import DatabaseManager
db = DatabaseManager()
db.initialize()
print('Database OK')
"

# 6) systemd
echo "[6/7] systemd service..."
cat > /etc/systemd/system/smartselect.service << EOF
[Unit]
Description=SmartSelect Web Service
After=network.target

[Service]
Type=simple
User=root
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
sleep 2
if systemctl is-active --quiet smartselect; then
    echo "smartselect: active"
else
    echo "smartselect failed, last logs:"
    journalctl -u smartselect -n 30 --no-pager || true
fi

# 7) nginx
echo "[7/7] nginx..."
cat > /etc/nginx/conf.d/smartselect.conf << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN _;

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
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
}
EOF
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
nginx -t && systemctl restart nginx
echo "nginx OK"

SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ip.sb 2>/dev/null || echo "?")
echo ""
echo "=========================================="
echo " Done"
echo "=========================================="
echo " IP:     $SERVER_IP"
echo " Open:   http://$SERVER_IP"
echo " Domain: http://$DOMAIN (after DNS A record)"
echo " HTTPS:  certbot --nginx -d $DOMAIN -d www.$DOMAIN --redirect"
echo " Logs:   journalctl -u smartselect -f"
echo "=========================================="
