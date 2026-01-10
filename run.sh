#!/bin/bash
# Paper Reader MCP 服务启动脚本
# Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
# MIT License

cd "$(dirname "$0")"

echo "=================================="
echo "  Paper Reader MCP 服务"
echo "=================================="

# 检查并安装依赖
echo ""
echo "检查依赖..."
pip3 install -q -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ 依赖安装失败"
    exit 1
fi

echo "✅ 依赖已就绪"
echo ""

# 启动服务
echo "启动服务..."
python3.11 server.py
