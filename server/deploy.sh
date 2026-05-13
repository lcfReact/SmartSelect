#!/bin/bash
# ============================================================
# SmartSelect 涓€閿儴缃茶剼鏈?
# 閫傜敤锛氳吘璁簯杞婚噺鏈嶅姟鍣?Ubuntu 22.04
# 鍩熷悕锛歝odecraftsure.com锛堥渶鍏堝湪闃块噷浜?DNS 灏?A 璁板綍鎸囧悜姝ゆ湇鍔″櫒 IP锛?
#
# 浣跨敤鏂瑰紡锛?
#   chmod +x deploy.sh
#   sudo bash deploy.sh
# ============================================================

set -e   # 浠绘剰鍛戒护澶辫触鍒欓€€鍑?

DOMAIN="codecraftsure.com"
APP_DIR="/opt/smartselect"
APP_USER="smartselect"
PYTHON_BIN="python3"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo " SmartSelect 閮ㄧ讲鑴氭湰 - $DOMAIN"
echo "========================================"

# 鈹€鈹€ 1. 鏇存柊绯荤粺 + 瀹夎鍩虹渚濊禆 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[1/8] 鏇存柊绯荤粺骞跺畨瑁呭熀纭€渚濊禆鈥?
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    nginx certbot python3-certbot-nginx \
    git curl wget build-essential \
    libfreetype6-dev libpng-dev pkg-config \
    > /dev/null

# 鈹€鈹€ 2. 鍒涘缓涓撶敤鐢ㄦ埛 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[2/8] 鍒涘缓鏈嶅姟鐢ㄦ埛 $APP_USER鈥?
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
fi

# 鈹€鈹€ 3. 鎷夊彇/鏇存柊浠ｇ爜 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[3/8] 鑾峰彇鏈€鏂颁唬鐮佲€?
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull origin master
else
    git clone https://github.com/lcfReact/SmartSelect.git "$APP_DIR"
    chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
fi

cd "$APP_DIR"

# 鈹€鈹€ 4. 鍒涘缓 Python 铏氭嫙鐜 + 瀹夎渚濊禆 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[4/8] 鍒涘缓铏氭嫙鐜骞跺畨瑁?Python 渚濊禆锛堥渶 3-5 鍒嗛挓锛夆€?
sudo -u "$APP_USER" $PYTHON_BIN -m venv "$VENV_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip -q
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r requirements-server.txt -q
echo "Python 渚濊禆瀹夎瀹屾垚"

# 鈹€鈹€ 5. 鍒濆鍖栨暟鎹簱 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[5/8] 鍒濆鍖栨暟鎹簱鈥?
cd "$APP_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/python" -c "
from src.database.db_manager import DatabaseManager
db = DatabaseManager()
db.initialize()
print('鏁版嵁搴撳垵濮嬪寲瀹屾垚')
"

# 鈹€鈹€ 6. 瀹夎 Systemd 鏈嶅姟 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[6/8] 閰嶇疆 Systemd 鏈嶅姟鈥?
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
echo "Systemd 鏈嶅姟宸插惎鍔?

# 鈹€鈹€ 7. 閰嶇疆 Nginx 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[7/8] 閰嶇疆 Nginx 鍙嶅悜浠ｇ悊鈥?
cat > /etc/nginx/sites-available/smartselect << EOF
# HTTP 鈫?HTTPS 閲嶅畾鍚戯紙Let's Encrypt 閰嶇疆鍓嶅厛鐢?HTTP锛?
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    # Let's Encrypt 楠岃瘉
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # 鏆傛椂鐩存帴浠ｇ悊锛堟湭閰嶇疆 SSL 鏃讹級
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

# 鍚敤绔欑偣
ln -sf /etc/nginx/sites-available/smartselect /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
echo "Nginx 閰嶇疆瀹屾垚锛圚TTP锛?

# 鈹€鈹€ 8. 鐢宠 SSL 璇佷功锛圠et's Encrypt锛夆攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
echo "[8/8] 鐢宠 HTTPS 璇佷功鈥?
mkdir -p /var/www/certbot

# 妫€鏌ュ煙鍚嶆槸鍚﹀凡瑙ｆ瀽鍒版湰鏈猴紙DNS 浼犳挱闇€瑕佹渶澶?24 灏忔椂锛?
SERVER_IP=$(curl -s ifconfig.me)
DOMAIN_IP=$(dig +short $DOMAIN 2>/dev/null || host $DOMAIN | awk '/has address/ { print $4 }' | head -1)

if [ "$SERVER_IP" = "$DOMAIN_IP" ]; then
    certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
        --non-interactive --agree-tos --email admin@$DOMAIN \
        --redirect
    echo "SSL 璇佷功鐢宠鎴愬姛锛丠TTPS 宸插惎鐢?
    
    # 瑕嗙洊 Nginx 閰嶇疆涓?HTTPS
    cat > /etc/nginx/sites-available/smartselect << 'EOF2'
# HTTP 鈫?HTTPS 閲嶅畾鍚?
server {
    listen 80;
    server_name PLACEHOLDER_DOMAIN www.PLACEHOLDER_DOMAIN;
    return 301 https://$host$request_uri;
}

# HTTPS 涓婚厤缃?
server {
    listen 443 ssl http2;
    server_name PLACEHOLDER_DOMAIN www.PLACEHOLDER_DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/PLACEHOLDER_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/PLACEHOLDER_DOMAIN/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # WebSocket 浠ｇ悊
    location /ws/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "Upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400s;
    }

    # 鏅€?HTTP 浠ｇ悊
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

    # Gzip 鍘嬬缉
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
}
EOF2
    sed -i "s/PLACEHOLDER_DOMAIN/$DOMAIN/g" /etc/nginx/sites-available/smartselect
    nginx -t && systemctl reload nginx
else
    echo ""
    echo "鈿? 鍩熷悕 $DOMAIN 灏氭湭瑙ｆ瀽鍒版湰鏈?IP ($SERVER_IP)"
    echo "   褰撳墠瑙ｆ瀽鍒? $DOMAIN_IP"
    echo ""
    echo "   璇峰埌闃块噷浜?DNS 鎺у埗鍙板皢浠ヤ笅璁板綍鎸囧悜鏈満锛?
    echo "     A 璁板綍   @   鈫?  $SERVER_IP"
    echo "     A 璁板綍   www 鈫?  $SERVER_IP"
    echo ""
    echo "   DNS 鐢熸晥鍚庢墽琛屼互涓嬪懡浠ゅ畬鎴?SSL 閰嶇疆锛?
    echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN --redirect"
fi

echo ""
echo "=========================================="
echo " 閮ㄧ讲瀹屾垚锛?
echo "=========================================="
echo " 鏈嶅姟鍦板潃: http://$(curl -s ifconfig.me)"
echo " 鍩熷悕璁块棶: http://$DOMAIN锛圖NS 鐢熸晥鍚庯級"
echo ""
echo " 甯哥敤鍛戒护锛?
echo "   sudo systemctl status  smartselect  # 鏌ョ湅鏈嶅姟鐘舵€?
echo "   sudo systemctl restart smartselect  # 閲嶅惎鏈嶅姟"
echo "   sudo journalctl -u smartselect -f   # 瀹炴椂鏃ュ織"
echo "   sudo systemctl reload  nginx        # 閲嶈浇 Nginx"
echo "=========================================="
