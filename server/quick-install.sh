#!/bin/bash
# ============================================================
# SmartSelect 蹇€熷畨瑁咃紙鏃犻渶 git锛岀洿鎺ョ敤 curl 涓嬭浇锛?
# 閫傜敤锛氳吘璁簯杞婚噺鏈嶅姟鍣?OpenCloudOS / CentOS / Ubuntu
# ============================================================
set -e

DOMAIN="codecraftsure.com"
APP_DIR="/opt/smartselect"
APP_USER="smartselect"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo " SmartSelect 蹇€熷畨瑁?- $DOMAIN"
echo "========================================"

# 鈹€鈹€ 1. 妫€娴嬬郴缁?+ 瀹夎鍩虹宸ュ叿 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[1/7] 瀹夎鍩虹宸ュ叿鈥?
if command -v yum &>/dev/null; then
    PKG="yum"
    yum install -y git curl wget python3 python3-pip nginx \
        python3-devel gcc make openssl-devel libffi-devel > /dev/null
    # certbot锛圗PEL锛?
    yum install -y epel-release > /dev/null 2>&1 || true
    yum install -y certbot python3-certbot-nginx > /dev/null 2>&1 || true
elif command -v apt-get &>/dev/null; then
    PKG="apt"
    apt-get update -qq
    apt-get install -y -qq git curl wget python3 python3-pip python3-venv \
        nginx certbot python3-certbot-nginx > /dev/null
fi
echo "鍩虹宸ュ叿宸插畨瑁?(git, python3, nginx)"

# 鈹€鈹€ 2. 鑾峰彇浠ｇ爜 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[2/7] 涓嬭浇浠ｇ爜鈥?
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR" && git pull origin master
else
    git clone https://github.com/lcfReact/SmartSelect.git "$APP_DIR"
fi
echo "浠ｇ爜宸茶幏鍙? $APP_DIR"

# 鈹€鈹€ 3. 鍒涘缓涓撶敤鐢ㄦ埛 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[3/7] 鍒涘缓鏈嶅姟鐢ㄦ埛鈥?
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER" 2>/dev/null || true
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR" 2>/dev/null || true

# 鈹€鈹€ 4. 鍒涘缓铏氭嫙鐜 + 瀹夎渚濊禆 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[4/7] 瀹夎 Python 渚濊禆锛?-8 鍒嗛挓锛夆€?
cd "$APP_DIR"

# 濡傛灉娌℃湁 venv 妯″潡锛屾墜鍔ㄨ
python3 -m venv "$VENV_DIR" 2>/dev/null || {
    if [ "$PKG" = "yum" ]; then
        yum install -y python3-virtualenv > /dev/null
    fi
    python3 -m venv "$VENV_DIR"
}

"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r requirements-server.txt -q
echo "Python 渚濊禆瀹夎瀹屾垚"

# 鈹€鈹€ 5. 鍒濆鍖栨暟鎹簱 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[5/7] 鍒濆鍖栨暟鎹簱鈥?
cd "$APP_DIR"
"$VENV_DIR/bin/python" -c "
import sys; sys.path.insert(0,'$APP_DIR')
from src.database.db_manager import DatabaseManager
db = DatabaseManager()
db.initialize()
print('鏁版嵁搴撳垵濮嬪寲瀹屾垚')
"

# 鈹€鈹€ 6. Systemd 鏈嶅姟 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[6/7] 閰嶇疆绯荤粺鏈嶅姟鈥?
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

# 楠岃瘉鏈嶅姟
if systemctl is-active --quiet smartselect; then
    echo "鏈嶅姟杩愯姝ｅ父 鉁?
else
    echo "鏈嶅姟鍚姩寮傚父锛屾煡鐪嬫棩蹇楋細"
    journalctl -u smartselect -n 20 --no-pager
fi

# 鈹€鈹€ 7. Nginx 閰嶇疆 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[7/7] 閰嶇疆 Nginx鈥?

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

# 鍒犻櫎鍙兘鍐茬獊鐨勯粯璁ら厤缃?
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

nginx -t && systemctl restart nginx
echo "Nginx 閰嶇疆瀹屾垚 鉁?

# 鈹€鈹€ 瀹屾垚鎻愮ず 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ip.sb 2>/dev/null || echo "鑾峰彇IP澶辫触")

echo ""
echo "=========================================="
echo " 瀹夎瀹屾垚锛?
echo "=========================================="
echo " 鏈満 IP:  $SERVER_IP"
echo " 鐩存帴璁块棶: http://$SERVER_IP"
echo ""
echo " 闃块噷浜?DNS 璁剧疆锛圓璁板綍锛夆啋 $SERVER_IP"
echo " DNS鐢熸晥鍚庤闂? http://$DOMAIN"
echo ""
echo " 鐢宠 HTTPS锛圖NS鐢熸晥鍚庤繍琛岋級:"
echo "   certbot --nginx -d $DOMAIN -d www.$DOMAIN --redirect"
echo ""
echo " 甯哥敤杩愮淮鍛戒护:"
echo "   systemctl status  smartselect   # 鐘舵€?
echo "   systemctl restart smartselect   # 閲嶅惎"
echo "   journalctl -u smartselect -f    # 瀹炴椂鏃ュ織"
echo "=========================================="
