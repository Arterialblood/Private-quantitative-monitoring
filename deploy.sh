#!/bin/bash
# 股票监控系统部署脚本
# 作者：Claude AI Assistant
# 日期：2023年4月13日

echo "========================================"
echo "   股票监控系统部署脚本开始执行"
echo "========================================"

# 确保系统更新
echo "[1/8] 正在更新系统包..."
sudo apt-get update -y || sudo yum update -y

# 安装必要的软件包
echo "[2/8] 正在安装必要的软件包..."
sudo apt-get install -y git python3 python3-pip || sudo yum install -y git python3 python3-pip

# 克隆GitHub仓库
echo "[3/8] 正在克隆代码仓库..."
REPO_DIR="$HOME/Private-quantitative-monitoring"
if [ -d "$REPO_DIR" ]; then
    echo "仓库目录已存在，正在更新..."
    cd "$REPO_DIR"
    git pull
else
    echo "仓库目录不存在，正在克隆..."
    git clone https://github.com/Arterialblood/Private-quantitative-monitoring.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 安装Python依赖
echo "[4/8] 正在安装Python依赖..."
pip3 install pandas numpy matplotlib tushare requests || pip install pandas numpy matplotlib tushare requests

# 设置配置文件
echo "[5/8] 正在设置配置文件..."
if [ ! -f "config.json" ]; then
    cp config.json.example config.json
    echo "请编辑config.json文件，填入您的API密钥和其他配置信息。"
    echo "现在将自动打开编辑器，请完成编辑后保存并关闭。"
    sleep 3
    if command -v nano > /dev/null; then
        nano config.json
    elif command -v vim > /dev/null; then
        vim config.json
    else
        echo "找不到编辑器（nano或vim）。请稍后手动编辑config.json文件。"
    fi
else
    echo "config.json文件已存在，跳过创建步骤。"
fi

# 创建系统服务文件
echo "[6/8] 正在创建系统服务..."
SERVICE_FILE="/tmp/stock-monitor.service"
cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Stock Monitoring Service
After=network.target

[Service]
User=$(whoami)
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/python3 $REPO_DIR/底分型微信通知.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# 复制服务文件并启用服务
echo "[7/8] 正在启用系统服务..."
sudo mv "$SERVICE_FILE" /etc/systemd/system/stock-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable stock-monitor
sudo systemctl start stock-monitor

# 检查服务状态
echo "[8/8] 正在检查服务状态..."
sudo systemctl status stock-monitor

echo "========================================"
echo "   股票监控系统部署完成"
echo "========================================"
echo ""
echo "使用以下命令查看程序日志："
echo "sudo journalctl -u stock-monitor -f"
echo ""
echo "使用以下命令重启服务："
echo "sudo systemctl restart stock-monitor"
echo ""
echo "使用以下命令停止服务："
echo "sudo systemctl stop stock-monitor"
echo ""
echo "使用以下命令查看服务状态："
echo "sudo systemctl status stock-monitor"
echo "" 