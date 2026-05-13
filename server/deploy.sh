#!/bin/bash
# ============================================================
# SmartSelect 一键部署脚本
# 适用：腾讯云轻量服务器 Ubuntu 22.04
# 域名：codecraftsure.com（需先在阿里云 DNS 将 A 记录指向此服务器 IP）
#
# 使用方式：
#   chmod +x deploy.sh
#   sudo bash deploy.sh
# ============================================================

set -e   # 任意命令失败则退出

DOMAIN="codecraftsure.com"
APP_DIR="/opt/smartselect"
APP_USER="smartselect"
PYTHON_BIN="python3"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo " SmartSelect 部署脚本 - $DOMAIN"
echo "========================================"

# ── 1. 更新系统 + 安装基础依赖 ─────────────────────────────
echo "[1/8] 更新系统并安装基础依赖…"
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    nginx certbot python3-certbot-nginx \
    git curl wget build-essential \
    libfreetype6-dev libpng-dev pkg-config \
    > /dev/null

# ── 2. 创建专用用户 ────────────────────────────────────────
echo "[2/8] 创建服务用户 $APP_USER…"
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
fi

# ── 3. 拉取/更新代码 ──────────────────────────────────────
echo "[3/8] 获取最新代码…"
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull origin master
else
    git clone https://github.com/lcfReact/SmartSelect.git "$APP_DIR"
    chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
fi

cd "$APP_DIR"

# ── 4. 创建 Python 虚拟环境 + 安装依赖 ────────────────────
echo "[4/8] 创建虚拟环境并安装 Python 依赖（需 3-5 分钟）…"
sudo -u "$APP_USER" $PYTHON_BIN -m venv "$VENV_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip -q
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r requirements-server.txt -q
echo "Python 依赖安装完成"

# ── 5. 初始化数据库 ────────────────────────────────────────
echo "[5/8] 初始化数据库…"
cd "$APP_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/python" -c "
from src.database.db_manager import DatabaseManager
db = DatabaseManager()
db.initialize()
print('数据库初始化完成')
"

# ── 6. 安装 Systemd 服务 ──────────────────────────────────
echo "[6/8] 配置 Systemd 服务…"
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
echo "Systemd 服务已启动"

# ── 7. 配置 Nginx ─────────────────────────────────────────
echo "[7/8] 配置 Nginx 反向代理…"
cat > /etc/nginx/sites-available/smartselect << EOF
# HTTP → HTTPS 重定向（Let's Encrypt 配置前先用 HTTP）
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    # Let's Encrypt 验证
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # 暂时直接代理（未配置 SSL 时）
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

# 启用站点
ln -sf /etc/nginx/sites-available/smartselect /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
echo "Nginx 配置完成（HTTP）"

# ── 8. 申请 SSL 证书（Let's Encrypt）──────────────────────
echo "[8/8] 申请 HTTPS 证书…"
mkdir -p /var/www/certbot

# 检查域名是否已解析到本机（DNS 传播需要最多 24 小时）
SERVER_IP=$(curl -s ifconfig.me)
DOMAIN_IP=$(dig +short $DOMAIN 2>/dev/null || host $DOMAIN | awk '/has address/ { print $4 }' | head -1)

if [ "$SERVER_IP" = "$DOMAIN_IP" ]; then
    certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
        --non-interactive --agree-tos --email admin@$DOMAIN \
        --redirect
    echo "SSL 证书申请成功！HTTPS 已启用"
    
    # 覆盖 Nginx 配置为 HTTPS
    cat > /etc/nginx/sites-available/smartselect << 'EOF2'
# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name PLACEHOLDER_DOMAIN www.PLACEHOLDER_DOMAIN;
    return 301 https://$host$request_uri;
}

# HTTPS 主配置
server {
    listen 443 ssl http2;
    server_name PLACEHOLDER_DOMAIN www.PLACEHOLDER_DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/PLACEHOLDER_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/PLACEHOLDER_DOMAIN/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # WebSocket 代理
    location /ws/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "Upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400s;
    }

    # 普通 HTTP 代理
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

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
}
EOF2
    sed -i "s/PLACEHOLDER_DOMAIN/$DOMAIN/g" /etc/nginx/sites-available/smartselect
    nginx -t && systemctl reload nginx
else
    echo ""
    echo "⚠  域名 $DOMAIN 尚未解析到本机 IP ($SERVER_IP)"
    echo "   当前解析到: $DOMAIN_IP"
    echo ""
    echo "   请到阿里云 DNS 控制台将以下记录指向本机："
    echo "     A 记录   @   →   $SERVER_IP"
    echo "     A 记录   www →   $SERVER_IP"
    echo ""
    echo "   DNS 生效后执行以下命令完成 SSL 配置："
    echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN --redirect"
fi

echo ""
echo "=========================================="
echo " 部署完成！"
echo "=========================================="
echo " 服务地址: http://$(curl -s ifconfig.me)"
echo " 域名访问: http://$DOMAIN（DNS 生效后）"
echo ""
echo " 常用命令："
echo "   sudo systemctl status  smartselect  # 查看服务状态"
echo "   sudo systemctl restart smartselect  # 重启服务"
echo "   sudo journalctl -u smartselect -f   # 实时日志"
echo "   sudo systemctl reload  nginx        # 重载 Nginx"
echo "=========================================="
