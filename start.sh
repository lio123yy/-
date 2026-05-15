#!/bin/bash

echo "===================================="
echo "  五子棋联机对战服务器启动中..."
echo "===================================="

# 安装依赖
echo "[1/2] 正在安装依赖..."
pip install -q fastapi uvicorn websockets python-multipart

echo "[2/2] 启动服务器..."
echo ""
echo "===================================="
echo "  服务器已启动！"
echo "  打开浏览器访问: http://localhost:8000"
echo "  按 Ctrl+C 停止服务器"
echo "===================================="
echo ""

# 启动服务器
python server.py
