@echo off
chcp 65001 >nul
title 网络检测修复工具
python "%~dp0network_tool.py"
pause
