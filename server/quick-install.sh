#!/bin/bash
# ============================================================
# SmartSelect 快速安装（无需 git，直接用 curl 下载）
# 适用：腾讯云轻量服务器 OpenCloudOS / CentOS / Ubuntu
# ============================================================
set -e

DOMAIN="codecraftsure.com"
APP_DIR="/opt/smartselect"
APP_USER="smartselect"
VENV_DIR="$APP_DIR/venv"

echo "========================================"
echo " SmartSelect 快速安装 - $DOMAIN"
echo "========================================"

# ── 1. 检测系统 + 安装基础工具 ─────────────────────────────
echo "[1/7] 安装基础工具…"
if command -v yum &>/dev/null; then
    PKG="yum"
    yum install -y git curl wget python3 python3-pip nginx \
        python3-devel gcc make openssl-devel libffi-devel > /dev/null
    # certbot（EPEL）
    yum install -y epel-release > /dev/null 2>&1 || true
    yum install -y certbot python3-certbot-nginx > /dev/null 2>&1 || true
elif command -v apt-get &>/dev/null; then
    PKG="apt"
    apt-get update -qq
    apt-get install -y -qq git curl wget python3 python3-pip python3-venv \
        nginx certbot python3-certbot-nginx > /dev/null
fi
echo "基础工具已安装 (git, python3, nginx)"

# ── 2. 获取代码 ─────────────────────────────────────────────
echo "[2/7] 下载代码…"
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR" && git pull origin master
else
    git clone https://github.com/lcfReact/SmartSelect.git "$APP_DIR"
fi
echo "代码已获取: $APP_DIR"

# ── 3. 创建专用用户 ────────────────────────────────────────
echo "[3/7] 创建服务用户…"
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER" 2>/dev/null || true
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR" 2>/dev/null || true

# ── 4. 创建虚拟环境 + 安装依赖 ────────────────────────────
echo "[4/7] 安装 Python 依赖（3-8 分钟）…"
cd "$APP_DIR"

# 如果没有 venv 模块，手动装
python3 -m venv "$VENV_DIR" 2>/dev/null || {
    if [ "$PKG" = "yum" ]; then
        yum install -y python3-virtualenv > /dev/null
    fi
    python3 -m venv "$VENV_DIR"
}

"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r requirements-server.txt -q
echo "Python 依赖安装完成"

# ── 5. 初始化数据库 ────────────────────────────────────────
echo "[5/7] 初始化数据库…"
cd "$APP_DIR"
"$VENV_DIR/bin/python" -c "
import sys; sys.path.insert(0,'$APP_DIR')
from src.database.db_manager import DatabaseManager
db = DatabaseManager()
db.initialize()
print('数据库初始化完成')
"

# ── 6. Systemd 服务 ────────────────────────────────────────
echo "[6/7] 配置系统服务…"
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

# 验证服务
if systemctl is-active --quiet smartselect; then
    echo "服务运行正常 ✓"
else
    echo "服务启动异常，查看日志："
    journalctl -u smartselect -n 20 --no-pager
fi

# ── 7. Nginx 配置 ──────────────────────────────────────────
echo "[7/7] 配置 Nginx…"

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

# 删除可能冲突的默认配置
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

nginx -t && systemctl restart nginx
echo "Nginx 配置完成 ✓"

# ── 完成提示 ──────────────────────────────────────────────
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ip.sb 2>/dev/null || echo "获取IP失败")

echo ""
echo "=========================================="
echo " 安装完成！"
echo "=========================================="
echo " 本机 IP:  $SERVER_IP"
echo " 直接访问: http://$SERVER_IP"
echo ""
echo " 阿里云 DNS 设置（A记录）→ $SERVER_IP"
echo " DNS生效后访问: http://$DOMAIN"
echo ""
echo " 申请 HTTPS（DNS生效后运行）:"
echo "   certbot --nginx -d $DOMAIN -d www.$DOMAIN --redirect"
echo ""
echo " 常用运维命令:"
echo "   systemctl status  smartselect   # 状态"
echo "   systemctl restart smartselect   # 重启"
echo "   journalctl -u smartselect -f    # 实时日志"
echo "=========================================="
