#!/usr/bin/env python3
"""
自动启动股票监控的脚本
直接执行监控功能，无需用户交互
"""

import logging
import os
import sys

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("股票监控")

# 确保能够导入底分型微信通知模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    # 导入必要的函数
    from 底分型微信通知 import ConfigManager, initialize_tushare, run_multi_monitor
    
    logger.info("启动股票监控服务")
    
    # 确保配置文件存在
    ConfigManager.load_config()
    
    # 初始化Tushare API
    initialize_tushare()
    
    logger.info("自动启动监控...")
    
    # 直接运行监控功能
    run_multi_monitor()
    
except Exception as e:
    logger.error(f"程序启动失败: {str(e)}")
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1) 