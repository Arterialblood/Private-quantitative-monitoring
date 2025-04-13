#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
底分型策略微信通知系统

本程序监控股票/指数，在发现底分型买入信号或顶分型卖出信号时
通过企业微信发送通知，帮助交易者把握交易时机。

使用说明：
1. 配置企业微信参数(corp_id, corp_secret, agent_id)
2. 配置个人自选股，可添加多个监控标的
3. 设置监控间隔，程序将定期检查并发送通知
"""

import os
import json
import time
import logging
import datetime
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from matplotlib.dates import DateFormatter
import tushare as ts

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bottom_pattern_strategy.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("底分型策略")

# 方糖Server酱通知器
class ServerChanNotifier:
    """使用方糖(Server酱)发送通知"""
    
    def __init__(self, sckey=None):
        """
        初始化方糖通知器
        :param sckey: 方糖的SCKEY，可以从 https://sct.ftqq.com/ 获取
        """
        # 尝试从配置文件读取
        config = ConfigManager.load_config()
        serverchan_config = config.get("serverchan_settings", {})
        
        # 优先使用参数传入的值，其次使用配置文件，最后使用环境变量
        self.sckey = sckey or serverchan_config.get("sckey") or os.environ.get('SERVERCHAN_SCKEY')
        self.enabled = bool(self.sckey)
        
        if not self.enabled:
            logger.warning("方糖通知未配置完整，将不会发送通知。请在配置文件中设置sckey。")
    
    def send_notification(self, title, content, level="info"):
        """
        发送方糖通知
        :param title: 通知标题
        :param content: 通知内容
        :param level: 通知级别(info/warning/error)，在方糖中体现为不同标题格式
        """
        if not self.enabled:
            logger.info(f"方糖通知未启用，消息未发送: {title}")
            return False
        
        # 根据级别添加不同的前缀
        prefix = {
            "info": "🔔 ",
            "warning": "⚠️ ",
            "error": "❌ "
        }.get(level, "")
        
        full_title = prefix + title
        
        # 发送消息
        url = f"https://sctapi.ftqq.com/{self.sckey}.send"
        data = {
            "title": full_title,
            "desp": content + f"\n\n*发送时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        }
        
        try:
            response = requests.post(url, data=data)
            response_json = response.json()
            if response_json.get("code") == 0:
                logger.info(f"方糖通知发送成功: {title}")
                return True
            else:
                logger.error(f"方糖通知发送失败: {response_json}")
                return False
        except Exception as e:
            logger.error(f"方糖通知发送异常: {e}")
            return False
    
    def send_image(self, image_path=None, image_buffer=None, title="图表分析"):
        """
        方糖免费版不支持直接发送图片，但我们可以生成图片链接的通知
        :param image_path: 图片路径
        :param image_buffer: 图片内存缓冲区
        :param title: 通知标题
        """
        logger.warning("方糖免费版不支持直接发送图片，仅发送通知。如需图片功能，请考虑升级到付费版或使用其他方式存储图片并生成链接。")
        
        if not self.enabled:
            logger.info("方糖通知未启用，图片通知未发送")
            return False
            
        # 发送一条通知说明图表已生成
        return self.send_notification(
            title, 
            "图表分析已生成，但方糖免费版不支持直接显示图片。\n您可以在程序运行目录查看保存的图表文件。",
            "info"
        )

# 配置管理类
class ConfigManager:
    """配置管理类，负责读取和保存配置"""
    
    CONFIG_FILE = "config.json"
    DEFAULT_CONFIG = {
        "api_settings": {
            "tushare_token": ""
        },
        "serverchan_settings": {
            "sckey": ""  # 添加方糖Server酱设置
        },
        "wechat_settings": {
            "corp_id": "",
            "corp_secret": "",
            "agent_id": ""
        },
        "monitoring": {
            "check_interval": 60,
            "days_back": 30,
            "watchlist": [
                {
                    "code": "399300",
                    "name": "沪深300",
                    "type": "index"
                }
            ]
        }
    }
    
    @classmethod
    def load_config(cls):
        """加载配置文件，如果不存在则创建默认配置"""
        try:
            if os.path.exists(cls.CONFIG_FILE):
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"成功加载配置文件: {cls.CONFIG_FILE}")
                return config
            else:
                logger.warning(f"配置文件不存在，创建默认配置: {cls.CONFIG_FILE}")
                cls.save_config(cls.DEFAULT_CONFIG)
                return cls.DEFAULT_CONFIG
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return cls.DEFAULT_CONFIG
    
    @classmethod
    def save_config(cls, config):
        """保存配置到文件"""
        try:
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logger.info(f"配置已保存到: {cls.CONFIG_FILE}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    @classmethod
    def update_config(cls, config_path, value):
        """
        更新配置中的特定路径
        :param config_path: 配置路径，例如 "api_settings.tushare_token"
        :param value: 新值
        :return: 更新后的配置
        """
        config = cls.load_config()
        paths = config_path.split('.')
        
        # 定位到最后一级的父对象
        target = config
        for path in paths[:-1]:
            if path not in target:
                target[path] = {}
            target = target[path]
        
        # 更新值
        target[paths[-1]] = value
        
        # 保存配置
        cls.save_config(config)
        return config

    @classmethod
    def add_watchlist_item(cls, code, name, type="stock"):
        """
        添加自选股到监控列表
        :param code: 股票代码
        :param name: 股票名称
        :param type: 类型(stock/index)
        :return: 更新后的配置
        """
        config = cls.load_config()
        
        # 确保监控列表存在
        if "monitoring" not in config:
            config["monitoring"] = {}
        if "watchlist" not in config["monitoring"]:
            config["monitoring"]["watchlist"] = []
        
        # 检查是否已存在
        for item in config["monitoring"]["watchlist"]:
            if item.get("code") == code:
                logger.info(f"自选股 {code} 已在监控列表中")
                return config
        
        # 添加到列表
        config["monitoring"]["watchlist"].append({
            "code": code,
            "name": name,
            "type": type
        })
        
        # 保存配置
        cls.save_config(config)
        logger.info(f"已添加自选股 {code}({name}) 到监控列表")
        return config
    
    @classmethod
    def remove_watchlist_item(cls, code):
        """
        从监控列表移除自选股
        :param code: 股票代码
        :return: 更新后的配置
        """
        config = cls.load_config()
        
        if "monitoring" in config and "watchlist" in config["monitoring"]:
            original_count = len(config["monitoring"]["watchlist"])
            config["monitoring"]["watchlist"] = [
                item for item in config["monitoring"]["watchlist"] 
                if item.get("code") != code
            ]
            
            if len(config["monitoring"]["watchlist"]) < original_count:
                cls.save_config(config)
                logger.info(f"已从监控列表移除 {code}")
            else:
                logger.info(f"自选股 {code} 不在监控列表中")
        
        return config

# 获取Tushare API密钥
def initialize_tushare():
    """初始化Tushare API"""
    config = ConfigManager.load_config()
    
    # 尝试从配置文件获取token
    ts_token = config.get("api_settings", {}).get("tushare_token", "")
    
    # 如果没有配置，尝试从环境变量获取
    if not ts_token:
        ts_token = os.environ.get('TUSHARE_TOKEN', '')
    
    # 如果还没有，提示用户输入
    if not ts_token:
        logger.warning("未设置Tushare Token，请配置后继续")
        return False
    
    # 设置token
    try:
        ts.set_token(ts_token)
        # 测试API是否可用
        pro = ts.pro_api()
        df = pro.trade_cal(exchange='', start_date='20230101', end_date='20230110')
        if df is not None and len(df) > 0:
            logger.info("Tushare API 初始化成功")
            return True
        else:
            logger.error("Tushare API 初始化失败: 返回数据为空")
            return False
    except Exception as e:
        logger.error(f"Tushare API 初始化失败: {e}")
        return False

# 微信通知功能 (保留但不建议使用)
class WeChatNotifier:
    def __init__(self, corp_id=None, corp_secret=None, agent_id=None):
        """
        初始化微信通知器
        :param corp_id: 企业微信企业ID
        :param corp_secret: 企业微信应用Secret
        :param agent_id: 企业微信应用ID
        """
        # 从配置文件读取
        config = ConfigManager.load_config()
        wechat_config = config.get("wechat_settings", {})
        
        # 优先使用参数传入的值，其次使用配置文件，最后使用环境变量
        self.corp_id = corp_id or wechat_config.get("corp_id") or os.environ.get('WECHAT_CORP_ID')
        self.corp_secret = corp_secret or wechat_config.get("corp_secret") or os.environ.get('WECHAT_CORP_SECRET')
        self.agent_id = agent_id or wechat_config.get("agent_id") or os.environ.get('WECHAT_AGENT_ID')
        self.token = None
        self.token_expires_time = 0
        
        # 检查配置是否完整
        self.enabled = all([self.corp_id, self.corp_secret, self.agent_id])
        if not self.enabled:
            logger.warning("微信通知未配置完整，将不会发送通知。请设置环境变量或在配置文件中提供参数。")
    
    def get_token(self):
        """获取访问令牌"""
        if not self.enabled:
            return None
            
        # 如果token有效，直接返回
        current_time = time.time()
        if self.token and current_time < self.token_expires_time:
            return self.token
        
        # 请求新token
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={self.corp_id}&corpsecret={self.corp_secret}"
        try:
            response = requests.get(url)
            response_json = response.json()
            if response_json.get("errcode") == 0:
                self.token = response_json.get("access_token")
                self.token_expires_time = current_time + response_json.get("expires_in") - 200  # 提前200秒过期，安全起见
                return self.token
            else:
                logger.error(f"获取微信token失败: {response_json}")
                return None
        except Exception as e:
            logger.error(f"获取微信token异常: {e}")
            return None
    
    def send_notification(self, title, content, level="info"):
        """
        发送微信通知
        :param title: 通知标题
        :param content: 通知内容
        :param level: 通知级别(info/warning/error)对应不同的文本颜色
        """
        if not self.enabled:
            logger.info(f"微信通知未启用，消息未发送: {title}")
            return False
        
        # 获取token
        token = self.get_token()
        if not token:
            return False
        
        # 设置颜色
        color = {
            "info": "#10aeff",
            "warning": "#ffc300",
            "error": "#ff0000"
        }.get(level, "#10aeff")
        
        # 拼接消息内容，支持Markdown格式
        message = f"""# <font color="{color}">{title}</font>
{content}
        
*发送时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        # 发送消息
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        data = {
            "touser": "@all",  # 发送给所有人，也可以指定用户ID
            "msgtype": "markdown",
            "agentid": self.agent_id,
            "markdown": {
                "content": message
            },
            "enable_duplicate_check": 0,
            "duplicate_check_interval": 600
        }
        
        try:
            response = requests.post(url, data=json.dumps(data))
            response_json = response.json()
            if response_json.get("errcode") == 0:
                logger.info(f"微信通知发送成功: {title}")
                return True
            else:
                logger.error(f"微信通知发送失败: {response_json}")
                return False
        except Exception as e:
            logger.error(f"微信通知发送异常: {e}")
            return False
    
    def send_image(self, image_path=None, image_buffer=None):
        """
        发送图片通知
        :param image_path: 图片路径
        :param image_buffer: 图片内存缓冲区
        """
        if not self.enabled:
            logger.info("微信通知未启用，图片未发送")
            return False
            
        token = self.get_token()
        if not token:
            return False
            
        # 上传图片
        media_url = f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={token}&type=image"
        
        try:
            if image_path:
                with open(image_path, 'rb') as f:
                    files = {'media': f}
                    response = requests.post(media_url, files=files)
            elif image_buffer:
                files = {'media': ('chart.png', image_buffer.getvalue(), 'image/png')}
                response = requests.post(media_url, files=files)
            else:
                logger.error("未提供图片路径或缓冲区")
                return False
                
            response_json = response.json()
            if response_json.get("errcode") == 0:
                media_id = response_json.get("media_id")
                
                # 发送图片消息
                send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
                data = {
                    "touser": "@all",
                    "msgtype": "image",
                    "agentid": self.agent_id,
                    "image": {
                        "media_id": media_id
                    }
                }
                
                send_response = requests.post(send_url, data=json.dumps(data))
                send_json = send_response.json()
                if send_json.get("errcode") == 0:
                    logger.info("图片消息发送成功")
                    return True
                else:
                    logger.error(f"图片消息发送失败: {send_json}")
                    return False
            else:
                logger.error(f"图片上传失败: {response_json}")
                return False
        except Exception as e:
            logger.error(f"发送图片异常: {e}")
            return False

# 技术指标计算函数
def calculate_rsi(prices, period=14):
    """计算相对强弱指数(RSI)"""
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    rs = up/down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100./(1. + rs)
    
    for i in range(period, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
            
        up = (up * (period-1) + upval) / period
        down = (down * (period-1) + downval) / period
        rs = up/down if down != 0 else 0
        rsi[i] = 100. - 100./(1. + rs)
    return rsi

def calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9):
    """计算MACD指标"""
    # 计算EMA值
    ema_fast = np.zeros_like(prices)
    ema_slow = np.zeros_like(prices)
    
    # 初始化
    ema_fast[slow_period-1] = np.mean(prices[:slow_period])
    ema_slow[slow_period-1] = np.mean(prices[:slow_period])
    
    # 计算EMA
    fast_multiplier = 2 / (fast_period + 1)
    slow_multiplier = 2 / (slow_period + 1)
    
    for i in range(slow_period, len(prices)):
        ema_fast[i] = (prices[i] - ema_fast[i-1]) * fast_multiplier + ema_fast[i-1]
        ema_slow[i] = (prices[i] - ema_slow[i-1]) * slow_multiplier + ema_slow[i-1]
    
    # 计算MACD线和信号线
    macd_line = ema_fast - ema_slow
    
    # 计算信号线(MACD的9日EMA)
    signal_line = np.zeros_like(macd_line)
    signal_line[slow_period+signal_period-1] = np.mean(macd_line[slow_period-1:slow_period+signal_period-1])
    signal_multiplier = 2 / (signal_period + 1)
    
    for i in range(slow_period+signal_period, len(prices)):
        signal_line[i] = (macd_line[i] - signal_line[i-1]) * signal_multiplier + signal_line[i-1]
    
    # 计算柱状图
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(prices, period=20, num_std=2):
    """计算布林带"""
    middle_band = np.zeros_like(prices)
    upper_band = np.zeros_like(prices)
    lower_band = np.zeros_like(prices)
    
    for i in range(period-1, len(prices)):
        window = prices[i-(period-1):i+1]
        middle_band[i] = np.mean(window)
        std_dev = np.std(window)
        upper_band[i] = middle_band[i] + (std_dev * num_std)
        lower_band[i] = middle_band[i] - (std_dev * num_std)
    
    return upper_band, middle_band, lower_band

def calculate_atr(high, low, close, period=14):
    """计算平均真实范围(ATR)"""
    tr = np.zeros(len(high))
    
    # 计算真实范围(TR)
    for i in range(1, len(tr)):
        hl = high[i] - low[i]
        hpc = abs(high[i] - close[i-1])
        lpc = abs(low[i] - close[i-1])
        tr[i] = max(hl, hpc, lpc)
    
    # 使用简单移动平均计算ATR
    atr = np.zeros_like(tr)
    atr[period] = np.mean(tr[1:period+1])
    
    for i in range(period+1, len(tr)):
        atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
        
    return atr

# 底分型策略实现
class BottomPatternStrategy:
    def __init__(self, stock_code, start_date, end_date, notifier=None):
        """
        初始化底分型策略
        :param stock_code: 股票/指数代码
        :param start_date: 开始日期
        :param end_date: 结束日期
        :param notifier: 通知器
        """
        self.stock_code = stock_code
        self.start_date = start_date
        self.end_date = end_date
        self.data = None
        self.bottom_results = []
        self.top_results = []
        
        # 使用方糖Server酱作为默认通知器
        self.notifier = notifier or ServerChanNotifier()
        
        # 获取Pro API接口
        self.pro = ts.pro_api()
        
        # 市场状态
        self.current_position = None  # 当前持仓状态
        self.position_price = 0  # 持仓价格
        self.position_date = None  # 持仓日期
    
    def get_data(self):
        """获取股票/指数数据"""
        # 处理股票代码格式
        code = self.stock_code
        # 指数代码处理
        if code.startswith('399'):
            code = code + '.SZ'
        elif code.startswith('000'):
            if len(code) == 6:  # 普通股票
                code = code + '.SZ'
            else:  # 特殊指数如000001、000300等
                code = code + '.SH'
        elif code.startswith('6'):
            code = code + '.SH'
        else:
            if len(code) == 6:
                if code.startswith('6'):
                    code = code + '.SH'
                else:
                    code = code + '.SZ'
        
        try:
            # 指数数据需要使用index_daily接口
            if code.startswith('000') or code.startswith('399'):
                df = self.pro.index_daily(ts_code=code, start_date=self.start_date, end_date=self.end_date)
            else:
                # 获取股票日线数据
                df = self.pro.daily(ts_code=code, start_date=self.start_date, end_date=self.end_date)
            
            # 按日期排序
            df = df.sort_values('trade_date')
            
            # 计算常用技术指标
            df['ma5'] = df['close'].rolling(5).mean()
            df['ma10'] = df['close'].rolling(10).mean()
            df['ma20'] = df['close'].rolling(20).mean()
            df['ma60'] = df['close'].rolling(60).mean()
            
            # 计算相对强弱指标（RSI）
            if len(df) > 14:
                df['rsi'] = calculate_rsi(df['close'].values, period=14)
            
            # 计算MACD
            if len(df) > 26:
                macd, macd_signal, macd_hist = calculate_macd(
                    df['close'].values, 
                    fast_period=12, 
                    slow_period=26, 
                    signal_period=9
                )
                df['macd'] = macd
                df['macd_signal'] = macd_signal
                df['macd_hist'] = macd_hist
            
            # 计算布林带
            if len(df) > 20:
                upper, middle, lower = calculate_bollinger_bands(
                    df['close'].values,
                    period=20,
                    num_std=2
                )
                df['bb_upper'] = upper
                df['bb_middle'] = middle
                df['bb_lower'] = lower
            
            # 计算ATR - 用于止损设置
            if len(df) > 14:
                df['atr'] = calculate_atr(
                    df['high'].values,
                    df['low'].values,
                    df['close'].values,
                    period=14
                )
            
            self.data = df
            return df
        except Exception as e:
            logger.error(f"获取数据失败: {e}")
            return pd.DataFrame()
    
    def identify_bottom_pattern(self):
        """识别底分型形态"""
        if self.data is None:
            self.get_data()
        
        df = self.data.copy()
        patterns = []
        
        # 至少需要3个点来判断底分型
        for i in range(1, len(df) - 1):
            # 基本底分型条件：前一个K线和后一个K线的低点都高于当前K线的低点
            if df['low'].iloc[i] < df['low'].iloc[i-1] and df['low'].iloc[i] < df['low'].iloc[i+1]:
                score = 0  # 初始分数
                reason = []  # 记录满足的条件
                
                # 条件1：当前K线收盘价高于开盘价（阳线）
                if df['close'].iloc[i] > df['open'].iloc[i]:
                    score += 1
                    reason.append("阳线")
                
                # 条件2：成交量放大
                if i > 0 and df['vol'].iloc[i] > df['vol'].iloc[i-1]:
                    score += 1
                    reason.append("放量")
                
                # 条件3：处于下降趋势中（当前价格低于10日均线）
                if 'ma10' in df.columns and df['close'].iloc[i] < df['ma10'].iloc[i]:
                    score += 1
                    reason.append("下降趋势")
                
                # 条件4：RSI低位
                if 'rsi' in df.columns and df['rsi'].iloc[i] < 30:
                    score += 2
                    reason.append("RSI低位")
                
                # 条件5：布林带下轨支撑
                if 'bb_lower' in df.columns and df['low'].iloc[i] <= df['bb_lower'].iloc[i]:
                    score += 1.5
                    reason.append("布林下轨支撑")
                
                # 条件6：MACD零轴以下，但柱状图向上（底部动能反转）
                if all(col in df.columns for col in ['macd', 'macd_hist']) and \
                   df['macd'].iloc[i] < 0 and \
                   i > 0 and df['macd_hist'].iloc[i] > df['macd_hist'].iloc[i-1]:
                    score += 1.5
                    reason.append("MACD底部反转")
                
                # 如果分数达到阈值，则认为是有效的底分型
                if score >= 3:
                    pattern = {
                        'date': df['trade_date'].iloc[i],
                        'price': df['close'].iloc[i],
                        'low': df['low'].iloc[i],
                        'volume': df['vol'].iloc[i],
                        'score': score,
                        'reason': reason
                    }
                    patterns.append(pattern)
        
        self.bottom_results = patterns
        return patterns
    
    def identify_top_pattern(self):
        """识别顶分型形态"""
        if self.data is None:
            self.get_data()
        
        df = self.data.copy()
        patterns = []
        
        # 至少需要3个点来判断顶分型
        for i in range(1, len(df) - 1):
            # 基本顶分型条件：前一个K线和后一个K线的高点都低于当前K线的高点
            if df['high'].iloc[i] > df['high'].iloc[i-1] and df['high'].iloc[i] > df['high'].iloc[i+1]:
                score = 0  # 初始分数
                reason = []  # 记录满足的条件
                
                # 条件1：当前K线收盘价低于开盘价（阴线）
                if df['close'].iloc[i] < df['open'].iloc[i]:
                    score += 1
                    reason.append("阴线")
                
                # 条件2：成交量放大
                if i > 0 and df['vol'].iloc[i] > df['vol'].iloc[i-1]:
                    score += 1
                    reason.append("放量")
                
                # 条件3：处于上升趋势中（当前价格高于10日均线）
                if 'ma10' in df.columns and df['close'].iloc[i] > df['ma10'].iloc[i]:
                    score += 1
                    reason.append("上升趋势")
                
                # 条件4：RSI高位
                if 'rsi' in df.columns and df['rsi'].iloc[i] > 70:
                    score += 2
                    reason.append("RSI高位")
                
                # 条件5：布林带上轨阻力
                if 'bb_upper' in df.columns and df['high'].iloc[i] >= df['bb_upper'].iloc[i]:
                    score += 1.5
                    reason.append("布林上轨阻力")
                
                # 条件6：MACD零轴以上，但柱状图向下（顶部动能减弱）
                if all(col in df.columns for col in ['macd', 'macd_hist']) and \
                   df['macd'].iloc[i] > 0 and \
                   i > 0 and df['macd_hist'].iloc[i] < df['macd_hist'].iloc[i-1]:
                    score += 1.5
                    reason.append("MACD顶部转向")
                
                # 如果分数达到阈值，则认为是有效的顶分型
                if score >= 3:
                    pattern = {
                        'date': df['trade_date'].iloc[i],
                        'price': df['close'].iloc[i],
                        'high': df['high'].iloc[i],
                        'volume': df['vol'].iloc[i],
                        'score': score,
                        'reason': reason
                    }
                    patterns.append(pattern)
        
        self.top_results = patterns
        return patterns

    def generate_chart(self, days_to_show=60):
        """
        生成分析图表
        :param days_to_show: 显示最近多少天的数据
        :return: 图表缓冲区对象
        """
        if self.data is None or len(self.data) == 0:
            return None
            
        df = self.data.copy()
        
        # 只显示最近的数据
        if len(df) > days_to_show:
            df = df.iloc[-days_to_show:]
        
        # 设置通用字体，避免中文显示问题
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'sans-serif']
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['axes.unicode_minus'] = False  # 解决坐标轴负号显示问题
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
        
        # 上面的子图显示K线和均线
        ax1.plot(df.index, df['close'], label='收盘价', color='black', linewidth=1.5)
        ax1.plot(df.index, df['ma5'], label='MA5', linestyle='--', color='blue', linewidth=1)
        ax1.plot(df.index, df['ma10'], label='MA10', linestyle='--', color='purple', linewidth=1)
        ax1.plot(df.index, df['ma20'], label='MA20', linestyle='--', color='green', linewidth=1)
        
        # 添加布林带
        if 'bb_upper' in df.columns and 'bb_middle' in df.columns and 'bb_lower' in df.columns:
            ax1.plot(df.index, df['bb_upper'], label='布林上轨', color='red', alpha=0.6, linewidth=1)
            ax1.plot(df.index, df['bb_middle'], label='布林中轨', color='gray', alpha=0.6, linewidth=1)
            ax1.plot(df.index, df['bb_lower'], label='布林下轨', color='green', alpha=0.6, linewidth=1)
            
            # 填充布林带区域
            ax1.fill_between(df.index, df['bb_upper'], df['bb_lower'], color='lightskyblue', alpha=0.15)
        
        # 标记底分型
        for pattern in self.bottom_results:
            if pattern['date'] in df['trade_date'].values:
                idx = df[df['trade_date'] == pattern['date']].index[0]
                ax1.scatter(idx, df.loc[idx, 'low'], color='red', s=100, marker='^')
                ax1.text(idx, df.loc[idx, 'low'] * 0.99, f"底分型\n{pattern['score']:.1f}分", 
                         ha='center', va='top', fontsize=8, color='red')
        
        # 标记顶分型
        for pattern in self.top_results:
            if pattern['date'] in df['trade_date'].values:
                idx = df[df['trade_date'] == pattern['date']].index[0]
                ax1.scatter(idx, df.loc[idx, 'high'], color='green', s=100, marker='v')
                ax1.text(idx, df.loc[idx, 'high'] * 1.01, f"顶分型\n{pattern['score']:.1f}分", 
                         ha='center', va='bottom', fontsize=8, color='green')
        
        # 设置第一个子图
        ax1.set_title(f"{self.stock_code} 分型分析", fontsize=15)
        ax1.set_ylabel('价格', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='best')
        
        # 下面的子图显示MACD
        if all(col in df.columns for col in ['macd', 'macd_signal', 'macd_hist']):
            # 绘制MACD柱状图
            colors = ['red' if x > 0 else 'green' for x in df['macd_hist']]
            ax2.bar(df.index, df['macd_hist'], color=colors, alpha=0.7, label='MACD柱状')
            
            # 绘制MACD线和信号线
            ax2.plot(df.index, df['macd'], label='MACD', color='blue', linewidth=1)
            ax2.plot(df.index, df['macd_signal'], label='Signal', color='red', linewidth=1)
            
            # 添加零轴线
            ax2.axhline(y=0, color='black', linestyle='-', alpha=0.3)
            
            # 设置第二个子图
            ax2.set_title("MACD指标", fontsize=12)
            ax2.set_xlabel('日期', fontsize=12)
            ax2.grid(True, alpha=0.3)
            ax2.legend(loc='best')
        
        # 添加时间标记
        x_ticks = np.linspace(0, len(df) - 1, min(10, len(df)))
        x_labels = [df['trade_date'].iloc[int(i)] for i in x_ticks]
        ax1.set_xticks(x_ticks)
        ax1.set_xticklabels(x_labels, rotation=45)
        
        plt.tight_layout()
        
        # 保存图表到内存缓冲区
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        buffer.seek(0)
        plt.close()
        
        return buffer

    def backtest_strategy_realtime(self, hold_days=10, use_stop_loss=True, stop_loss_pct=5, use_trailing_stop=True):
        """
        使用实盘模拟方式回测策略（避免前视偏差）
        :param hold_days: 默认持有天数
        :param use_stop_loss: 是否使用止损
        :param stop_loss_pct: 止损百分比
        :param use_trailing_stop: 是否使用跟踪止损
        :return: 回测结果
        """
        if self.data is None or len(self.data) == 0:
            return "没有数据可供回测"
        
        df = self.data.copy()
        trades = []  # 记录交易
        
        # 模拟实盘交易
        holding = False  # 是否持有股票
        buy_price = 0  # 买入价格
        buy_date = None  # 买入日期
        buy_reason = None  # 买入原因
        highest_price = 0  # 持有期间最高价
        pending_buy_signal = False  # 待执行的买入信号
        pending_buy_reason = None  # 待执行买入的原因
        pending_sell_signal = False  # 待执行的卖出信号
        
        for i in range(2, len(df)):  # 从第3天开始，确保有足够历史数据
            prev_idx = i - 1
            current_date = df['trade_date'].iloc[i]
            current_price = df['close'].iloc[i]
            
            # 先检查是否有待执行的买入或卖出信号
            if pending_buy_signal and not holding:
                holding = True
                buy_price = df['open'].iloc[i]  # 使用开盘价买入
                buy_date = current_date
                highest_price = buy_price
                buy_reason = pending_buy_reason
                
                signal_msg = f"日期 {current_date} 开盘执行底分型买入信号，以 {buy_price:.2f} 买入"
                logger.info(signal_msg)
                
                # 发送通知
                if self.notifier.enabled:
                    title = f"{self.stock_code} 底分型买入信号执行"
                    content = f"""**已执行底分型买入信号**
- 买入日期: {buy_date}
- 买入价格: {buy_price:.2f}
- 买入原因: {', '.join(buy_reason) if isinstance(buy_reason, list) else buy_reason}

**技术指标状态**:
- RSI: {df['rsi'].iloc[i]:.2f}
- MACD: {df['macd'].iloc[i]:.4f}
- 布林带位置: {((current_price - df['bb_lower'].iloc[i]) / (df['bb_upper'].iloc[i] - df['bb_lower'].iloc[i]) * 100):.2f}%
"""
                    self.notifier.send_notification(title, content, "info")
                
                pending_buy_signal = False
                pending_buy_reason = None
            
            elif pending_sell_signal and holding:
                sell_price = df['open'].iloc[i]  # 使用开盘价卖出
                sell_date = current_date
                
                # 计算收益
                profit_pct = (sell_price - buy_price) / buy_price * 100
                
                # 记录交易
                trades.append({
                    'buy_date': buy_date,
                    'buy_price': buy_price,
                    'buy_reason': buy_reason,
                    'sell_date': sell_date,
                    'sell_price': sell_price,
                    'sell_reason': "顶分型",
                    'profit_pct': profit_pct,
                    'hold_days': (pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days
                })
                
                signal_msg = f"日期 {current_date} 开盘执行顶分型卖出信号，以 {sell_price:.2f} 卖出，收益率 {profit_pct:.2f}%"
                logger.info(signal_msg)
                
                # 发送通知
                if self.notifier.enabled:
                    title = f"{self.stock_code} 顶分型卖出信号执行"
                    content = f"""**已执行顶分型卖出信号**
- 卖出日期: {sell_date}
- 卖出价格: {sell_price:.2f}
- 买入价格: {buy_price:.2f}
- 收益率: {profit_pct:.2f}%
- 持有天数: {(pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days}天

**技术指标状态**:
- RSI: {df['rsi'].iloc[i]:.2f}
- MACD: {df['macd'].iloc[i]:.4f}
- 布林带位置: {((current_price - df['bb_lower'].iloc[i]) / (df['bb_upper'].iloc[i] - df['bb_lower'].iloc[i]) * 100):.2f}%
"""
                    level = "info" if profit_pct >= 0 else "warning"
                    self.notifier.send_notification(title, content, level)
                
                # 重置持仓状态
                holding = False
                buy_price = 0
                buy_date = None
                highest_price = 0
                pending_sell_signal = False
            
            # 更新最高价
            if holding and current_price > highest_price:
                highest_price = current_price
            
            # 检查是否产生新的买入信号（非持仓且无待处理信号时）
            if not holding and not pending_buy_signal:
                # 检查前一天是否形成底分型
                if i >= 3:  # 确保有足够的历史数据
                    current_data = df.iloc[:i+1]  # 只使用当前及之前的数据
                    
                    # 检查是否形成底分型
                    if (current_data['low'].iloc[prev_idx-1] > current_data['low'].iloc[prev_idx] and 
                        current_data['low'].iloc[prev_idx+1] > current_data['low'].iloc[prev_idx]):
                        
                        # 计算信号分数
                        score = 0
                        reason = []
                        
                        # 条件1：当前K线收盘价高于开盘价（阳线）
                        if current_data['close'].iloc[prev_idx] > current_data['open'].iloc[prev_idx]:
                            score += 1
                            reason.append("阳线")
                        
                        # 条件2：成交量放大
                        if prev_idx > 0 and current_data['vol'].iloc[prev_idx] > current_data['vol'].iloc[prev_idx-1]:
                            score += 1
                            reason.append("放量")
                        
                        # 条件3：处于下降趋势中（当前价格低于10日均线）
                        if 'ma10' in current_data.columns and current_data['close'].iloc[prev_idx] < current_data['ma10'].iloc[prev_idx]:
                            score += 1
                            reason.append("下降趋势")
                        
                        # 条件4：RSI低位
                        if 'rsi' in current_data.columns and current_data['rsi'].iloc[prev_idx] < 30:
                            score += 2
                            reason.append("RSI低位")
                        
                        # 条件5：布林带下轨支撑
                        if 'bb_lower' in current_data.columns and current_data['low'].iloc[prev_idx] <= current_data['bb_lower'].iloc[prev_idx]:
                            score += 1.5
                            reason.append("布林下轨支撑")
                        
                        # 条件6：MACD零轴以下，但柱状图向上（底部动能反转）
                        if all(col in current_data.columns for col in ['macd', 'macd_hist']) and \
                           current_data['macd'].iloc[prev_idx] < 0 and \
                           prev_idx > 0 and current_data['macd_hist'].iloc[prev_idx] > current_data['macd_hist'].iloc[prev_idx-1]:
                            score += 1.5
                            reason.append("MACD底部反转")
                        
                        # 如果分数达到阈值，则产生买入信号，待下一个交易日执行
                        if score >= 3:
                            pending_buy_signal = True
                            pending_buy_reason = reason
                            pattern_date = current_data['trade_date'].iloc[prev_idx]
                            signal_msg = f"日期 {current_date} 收盘识别到 {pattern_date} 形成底分型，下一交易日开盘买入"
                            logger.info(signal_msg)
                            
                            # 发送微信通知
                            if self.notifier.enabled:
                                title = f"{self.stock_code} 底分型买入信号提醒"
                                content = f"""**识别到底分型买入信号**
- 识别日期: {current_date}
- 形成日期: {pattern_date}
- 建议操作: 明日开盘买入
- 当前价格: {current_price:.2f}
- 信号评分: {score:.1f}分
- 信号详情: {', '.join(reason)}

**技术指标状态**:
- RSI: {current_data['rsi'].iloc[-1]:.2f}
- MACD: {current_data['macd'].iloc[-1]:.4f}
- 布林带位置: {((current_price - current_data['bb_lower'].iloc[-1]) / (current_data['bb_upper'].iloc[-1] - current_data['bb_lower'].iloc[-1]) * 100):.2f}%
"""
                                self.notifier.send_notification(title, content, "info")
            
            # 检查是否产生新的卖出信号（持仓中且无待处理信号时）
            if holding and not pending_sell_signal:
                # 检查前一天是否形成顶分型
                if i >= 3:  # 确保有足够的历史数据
                    current_data = df.iloc[:i+1]  # 只使用当前及之前的数据
                    
                    # 检查是否形成顶分型
                    if (current_data['high'].iloc[prev_idx-1] < current_data['high'].iloc[prev_idx] and 
                        current_data['high'].iloc[prev_idx+1] < current_data['high'].iloc[prev_idx]):
                        
                        # 计算信号分数
                        score = 0
                        
                        # 条件1：当前K线收盘价低于开盘价（阴线）
                        if current_data['close'].iloc[prev_idx] < current_data['open'].iloc[prev_idx]:
                            score += 1
                        
                        # 条件2：成交量放大
                        if prev_idx > 0 and current_data['vol'].iloc[prev_idx] > current_data['vol'].iloc[prev_idx-1]:
                            score += 1
                        
                        # 条件3：处于上升趋势中（当前价格高于10日均线）
                        if 'ma10' in current_data.columns and current_data['close'].iloc[prev_idx] > current_data['ma10'].iloc[prev_idx]:
                            score += 1
                        
                        # 条件4：RSI高位
                        if 'rsi' in current_data.columns and current_data['rsi'].iloc[prev_idx] > 70:
                            score += 2
                        
                        # 条件5：布林带上轨阻力
                        if 'bb_upper' in current_data.columns and current_data['high'].iloc[prev_idx] >= current_data['bb_upper'].iloc[prev_idx]:
                            score += 1.5
                        
                        # 条件6：MACD零轴以上，但柱状图向下（顶部动能减弱）
                        if all(col in current_data.columns for col in ['macd', 'macd_hist']) and \
                           current_data['macd'].iloc[prev_idx] > 0 and \
                           prev_idx > 0 and current_data['macd_hist'].iloc[prev_idx] < current_data['macd_hist'].iloc[prev_idx-1]:
                            score += 1.5
                        
                        # 如果分数达到阈值，确认为顶分型卖出信号，待下一个交易日执行
                        if score >= 3:
                            pending_sell_signal = True
                            pattern_date = current_data['trade_date'].iloc[prev_idx]
                            signal_msg = f"日期 {current_date} 收盘识别到 {pattern_date} 形成顶分型，下一交易日开盘卖出"
                            logger.info(signal_msg)
                            
                            # 发送微信通知
                            if self.notifier.enabled:
                                title = f"{self.stock_code} 顶分型卖出信号提醒"
                                content = f"""**识别到顶分型卖出信号**
- 识别日期: {current_date}
- 形成日期: {pattern_date}
- 建议操作: 明日开盘卖出
- 当前价格: {current_price:.2f}
- 买入价格: {buy_price:.2f}
- 浮动盈亏: {((current_price - buy_price) / buy_price * 100):.2f}%
- 持有天数: {(pd.to_datetime(current_date) - pd.to_datetime(buy_date)).days}天
- 信号详情: 顶分型形成，趋势可能反转

**技术指标状态**:
- RSI: {current_data['rsi'].iloc[-1]:.2f}
- MACD: {current_data['macd'].iloc[-1]:.4f}
- 布林带位置: {((current_price - current_data['bb_lower'].iloc[-1]) / (current_data['bb_upper'].iloc[-1] - current_data['bb_lower'].iloc[-1]) * 100):.2f}%
"""
                                self.notifier.send_notification(title, content, "warning")
            
            # 检查止损条件 - 这些是实时交易执行的，不需要等到下一交易日
            if holding and use_stop_loss and current_price <= buy_price * (1 - stop_loss_pct/100):
                # 立即执行止损
                sell_price = current_price
                sell_date = current_date
                
                # 计算收益
                profit_pct = (sell_price - buy_price) / buy_price * 100
                
                # 记录交易
                trades.append({
                    'buy_date': buy_date,
                    'buy_price': buy_price,
                    'buy_reason': buy_reason,
                    'sell_date': sell_date,
                    'sell_price': sell_price,
                    'sell_reason': f"止损 -{stop_loss_pct}%",
                    'profit_pct': profit_pct,
                    'hold_days': (pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days
                })
                
                signal_msg = f"日期 {current_date} 触发止损信号，以 {sell_price:.2f} 卖出，收益率 {profit_pct:.2f}%"
                logger.info(signal_msg)
                
                # 发送通知
                if self.notifier.enabled:
                    title = f"{self.stock_code} 止损卖出通知"
                    content = f"""**触发止损卖出信号**
- 卖出日期: {sell_date}
- 卖出价格: {sell_price:.2f}
- 买入价格: {buy_price:.2f}
- 亏损比例: {profit_pct:.2f}%
- 持有天数: {(pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days}天
- 止损类型: 固定止损 ({stop_loss_pct}%)

**注意: 此卖出已自动执行，无需手动操作**
"""
                    self.notifier.send_notification(title, content, "error")
                
                # 重置持仓状态
                holding = False
                buy_price = 0
                buy_date = None
                highest_price = 0
                continue
            
            # 检查跟踪止损条件 - 这些是实时交易执行的，不需要等到下一交易日
            if holding and use_trailing_stop and highest_price > buy_price and current_price <= highest_price * 0.95:
                # 立即执行跟踪止损
                sell_price = current_price
                sell_date = current_date
                
                # 计算收益
                profit_pct = (sell_price - buy_price) / buy_price * 100
                
                # 记录交易
                trades.append({
                    'buy_date': buy_date,
                    'buy_price': buy_price,
                    'buy_reason': buy_reason,
                    'sell_date': sell_date,
                    'sell_price': sell_price,
                    'sell_reason': "跟踪止损 -5%",
                    'profit_pct': profit_pct,
                    'hold_days': (pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days
                })
                
                signal_msg = f"日期 {current_date} 触发跟踪止损信号，以 {sell_price:.2f} 卖出，收益率 {profit_pct:.2f}%"
                logger.info(signal_msg)
                
                # 发送通知
                if self.notifier.enabled:
                    title = f"{self.stock_code} 跟踪止损卖出通知"
                    content = f"""**触发跟踪止损卖出信号**
- 卖出日期: {sell_date}
- 卖出价格: {sell_price:.2f}
- 买入价格: {buy_price:.2f}
- 最高价格: {highest_price:.2f}
- 回撤比例: {((highest_price - sell_price) / highest_price * 100):.2f}%
- 收益比例: {profit_pct:.2f}%
- 持有天数: {(pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days}天
- 止损类型: 跟踪止损 (高点回撤5%)

**注意: 此卖出已自动执行，无需手动操作**
"""
                    level = "warning" if profit_pct >= 0 else "error"
                    self.notifier.send_notification(title, content, level)
                
                # 重置持仓状态
                holding = False
                buy_price = 0
                buy_date = None
                highest_price = 0
                continue
            
            # 检查持仓时间是否达到最大持有天数，如果达到则卖出
            if holding and buy_date and hold_days > 0:
                days_held = (pd.to_datetime(current_date) - pd.to_datetime(buy_date)).days
                if days_held >= hold_days:
                    # 执行卖出
                    sell_price = current_price
                    sell_date = current_date
                    
                    # 计算收益
                    profit_pct = (sell_price - buy_price) / buy_price * 100
                    
                    # 记录交易
                    trades.append({
                        'buy_date': buy_date,
                        'buy_price': buy_price,
                        'buy_reason': buy_reason,
                        'sell_date': sell_date,
                        'sell_price': sell_price,
                        'sell_reason': f"持有天数达到 {hold_days} 天",
                        'profit_pct': profit_pct,
                        'hold_days': days_held
                    })
                    
                    logger.info(f"日期 {current_date} 持有天数达到 {hold_days} 天，以 {sell_price:.2f} 卖出，收益率 {profit_pct:.2f}%")
                    
                    # 重置持仓状态
                    holding = False
                    buy_price = 0
                    buy_date = None
                    highest_price = 0
                    continue
        
        # 如果回测结束时仍然持有，则使用最后一天的收盘价卖出
        if holding:
            sell_price = df['close'].iloc[-1]
            sell_date = df['trade_date'].iloc[-1]
            
            # 计算收益
            profit_pct = (sell_price - buy_price) / buy_price * 100
            
            # 记录交易
            trades.append({
                'buy_date': buy_date,
                'buy_price': buy_price,
                'buy_reason': buy_reason,
                'sell_date': sell_date,
                'sell_price': sell_price,
                'sell_reason': "回测结束",
                'profit_pct': profit_pct,
                'hold_days': (pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days
            })
            
            logger.info(f"回测结束，以 {sell_price:.2f} 卖出最后持仓，收益率 {profit_pct:.2f}%")
        
        # 计算回测结果
        if not trades:
            return "回测期间没有产生任何交易"
        
        total_trades = len(trades)
        total_profit_pct = sum(trade['profit_pct'] for trade in trades)
        avg_profit_pct = total_profit_pct / total_trades
        win_trades = sum(1 for trade in trades if trade['profit_pct'] > 0)
        win_rate = win_trades / total_trades if total_trades > 0 else 0
        max_profit_pct = max(trade['profit_pct'] for trade in trades) if trades else 0
        max_loss_pct = min(trade['profit_pct'] for trade in trades) if trades else 0
        avg_hold_days = sum(trade['hold_days'] for trade in trades) / total_trades if total_trades > 0 else 0
        
        return {
            'total_trades': total_trades,
            'total_profit_pct': total_profit_pct,
            'avg_profit_pct': avg_profit_pct,
            'win_rate': win_rate,
            'max_profit_pct': max_profit_pct,
            'max_loss_pct': max_loss_pct,
            'avg_hold_days': avg_hold_days,
            'details': trades
        }

# 运行多个股票监控
def run_multi_monitor():
    """运行多个股票的实时监控"""
    # 加载配置
    config = ConfigManager.load_config()
    monitoring_config = config.get("monitoring", {})
    
    # 获取监控参数
    check_interval = monitoring_config.get("check_interval", 60)
    days_back = monitoring_config.get("days_back", 30)
    watchlist = monitoring_config.get("watchlist", [])
    
    if not watchlist:
        logger.warning("监控列表为空，请添加股票或指数后再启动监控")
        return
    
    # 初始化通知器（默认使用方糖Server酱）
    notifier = ServerChanNotifier()
    
    if not notifier.enabled:
        logger.warning("方糖通知未配置，将无法发送实时信号通知")
        logger.info("请在config.json中设置serverchan_settings.sckey或使用环境变量SERVERCHAN_SCKEY")
        answer = input("是否继续运行监控程序? (y/n): ")
        if answer.lower() != 'y':
            return
    
    # 发送启动通知
    watchlist_str = ", ".join([f"{item.get('name')}({item.get('code')})" for item in watchlist])
    logger.info(f"开始监控以下股票/指数：{watchlist_str}，每 {check_interval} 分钟检查一次")
    
    if notifier.enabled:
        notifier.send_notification(
            f"底分型策略监控启动",
            f"""已开始监控以下股票/指数：
{watchlist_str}

检查间隔: {check_interval}分钟
回溯天数: {days_back}天

发现信号将立即通知。""",
            "info"
        )
    
    # 记录每个股票的最后信号日期
    last_signals = {item["code"]: {"bottom": None, "top": None} for item in watchlist}
    
    try:
        while True:
            current_time = datetime.datetime.now()
            
            # 只在交易时间内运行（9:30-15:00，周一至周五）
            is_trading_hours = (
                9 <= current_time.hour <= 15 and 
                (current_time.hour != 9 or current_time.minute >= 30) and
                (current_time.hour != 15 or current_time.minute == 0) and
                current_time.weekday() < 5
            )
            
            # 是否强制检查（非交易时间也检查一次）
            force_check = current_time.hour == 8 and 0 <= current_time.minute < 10
            
            if is_trading_hours or force_check:
                for stock in watchlist:
                    code = stock.get("code")
                    name = stock.get("name", code)
                    
                    try:
                        # 计算时间范围
                        end_date = current_time.strftime('%Y%m%d')
                        start_date = (current_time - datetime.timedelta(days=days_back)).strftime('%Y%m%d')
                        
                        # 创建策略实例，使用方糖通知
                        strategy = BottomPatternStrategy(code, start_date, end_date, notifier)
                        
                        # 获取数据
                        df = strategy.get_data()
                        if df.empty:
                            logger.warning(f"未获取到 {name}({code}) 的数据，可能不是交易日或代码错误")
                            continue
                        
                        # 识别底分型
                        bottom_patterns = strategy.identify_bottom_pattern()
                        
                        # 检查是否有新的底分型
                        if bottom_patterns and (
                            last_signals[code]["bottom"] is None or 
                            bottom_patterns[-1]['date'] != last_signals[code]["bottom"]
                        ):
                            last_pattern = bottom_patterns[-1]
                            last_signals[code]["bottom"] = last_pattern['date']
                            
                            # 检查是否是最近的信号(最近3天内)
                            pattern_date = pd.to_datetime(last_pattern['date'])
                            now = pd.to_datetime(current_time.strftime('%Y%m%d'))
                            days_diff = (now - pattern_date).days
                            
                            if days_diff <= 3:  # 只提醒3天内的信号
                                logger.info(f"{name}({code}) 发现新底分型: {last_pattern['date']}, 评分: {last_pattern['score']:.1f}")
                                
                                # 生成图表
                                chart_buffer = strategy.generate_chart()
                                
                                # 发送方糖通知
                                if notifier.enabled:
                                    title = f"{name}({code}) 底分型买入信号"
                                    content = f"""**识别到底分型买入信号**
- 形成日期: {last_pattern['date']}
- 信号价格: {last_pattern['price']:.2f}
- 信号评分: {last_pattern['score']:.1f}分
- 信号详情: {', '.join(last_pattern['reason'])}

**交易建议**:
- 操作: 建议买入 {name}({code})
- 时机: 建议在次日开盘时买入
- 止损位: {last_pattern['low']:.2f}下方
"""
                                    notifier.send_notification(title, content, "info")
                                    
                                    # 可以保存图表到本地文件
                                    if chart_buffer:
                                        chart_path = f"{code}_{last_pattern['date']}_bottom.png"
                                        with open(chart_path, 'wb') as f:
                                            f.write(chart_buffer.getvalue())
                                        logger.info(f"已保存图表到 {chart_path}")
                        
                        # 识别顶分型
                        top_patterns = strategy.identify_top_pattern()
                        
                        # 检查是否有新的顶分型
                        if top_patterns and (
                            last_signals[code]["top"] is None or 
                            top_patterns[-1]['date'] != last_signals[code]["top"]
                        ):
                            last_pattern = top_patterns[-1]
                            last_signals[code]["top"] = last_pattern['date']
                            
                            # 检查是否是最近的信号(最近3天内)
                            pattern_date = pd.to_datetime(last_pattern['date'])
                            now = pd.to_datetime(current_time.strftime('%Y%m%d'))
                            days_diff = (now - pattern_date).days
                            
                            if days_diff <= 3:  # 只提醒3天内的信号
                                logger.info(f"{name}({code}) 发现新顶分型: {last_pattern['date']}, 评分: {last_pattern['score']:.1f}")
                                
                                # 生成图表
                                chart_buffer = strategy.generate_chart()
                                
                                # 发送方糖通知
                                if notifier.enabled:
                                    title = f"{name}({code}) 顶分型卖出信号"
                                    content = f"""**识别到顶分型卖出信号**
- 形成日期: {last_pattern['date']}
- 信号价格: {last_pattern['price']:.2f}
- 信号评分: {last_pattern['score']:.1f}分
- 信号详情: {', '.join(last_pattern['reason'])}

**交易建议**:
- 操作: 建议卖出 {name}({code})
- 时机: 建议在次日开盘时卖出
- 注意: 市场顶部信号形成，短期可能回调
"""
                                    notifier.send_notification(title, content, "warning")
                                    
                                    # 可以保存图表到本地文件
                                    if chart_buffer:
                                        chart_path = f"{code}_{last_pattern['date']}_top.png"
                                        with open(chart_path, 'wb') as f:
                                            f.write(chart_buffer.getvalue())
                                        logger.info(f"已保存图表到 {chart_path}")
                        
                        # 每个股票处理后暂停，避免API请求过快
                        time.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"{name}({code}) 监控过程中发生错误: {e}")
                
                # 所有股票检查完成后，输出下次检查时间
                next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=check_interval)
                logger.info(f"下次检查时间: {next_check_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 睡眠到下次检查
            time.sleep(min(check_interval * 60, 300))  # 最多等待5分钟，也可以被中断
            
    except KeyboardInterrupt:
        logger.info("收到中断信号，监控程序结束")
        if notifier.enabled:
            notifier.send_notification(
                "底分型策略监控停止",
                "监控程序已被手动停止。",
                "warning"
            )
    except Exception as e:
        logger.error(f"监控主程序异常: {e}")
        if notifier.enabled:
            notifier.send_notification(
                "底分型策略监控异常",
                f"监控程序发生错误: {str(e)}\n请检查日志并重启程序。",
                "error"
            )

def manage_watchlist():
    """管理自选股监控列表"""
    config = ConfigManager.load_config()
    watchlist = config.get("monitoring", {}).get("watchlist", [])
    
    while True:
        print("\n==== 自选股监控列表管理 ====")
        print("当前监控列表:")
        
        if not watchlist:
            print("暂无监控股票/指数")
        else:
            for i, item in enumerate(watchlist, 1):
                print(f"{i}. {item.get('name', '')}({item.get('code', '')})")
        
        print("\n操作选项:")
        print("1. 添加新的监控股票/指数")
        print("2. 删除监控股票/指数")
        print("3. 返回主菜单")
        
        choice = input("\n请选择操作 (1-3): ")
        
        if choice == '1':
            code = input("请输入股票/指数代码: ")
            if not code:
                print("代码不能为空")
                continue
                
            name = input(f"请输入 {code} 的名称 (可选): ") or code
            
            stock_type = input("请输入类型 (stock/index，默认stock): ").lower() or "stock"
            if stock_type not in ["stock", "index"]:
                stock_type = "stock"
            
            # 更新配置
            config = ConfigManager.add_watchlist_item(code, name, stock_type)
            watchlist = config.get("monitoring", {}).get("watchlist", [])
            print(f"已添加 {name}({code}) 到监控列表")
            
        elif choice == '2':
            if not watchlist:
                print("监控列表为空，无法删除")
                continue
                
            index = input("请输入要删除的序号或代码: ")
            
            try:
                # 尝试作为索引处理
                idx = int(index) - 1
                if 0 <= idx < len(watchlist):
                    code = watchlist[idx].get("code")
                    config = ConfigManager.remove_watchlist_item(code)
                    watchlist = config.get("monitoring", {}).get("watchlist", [])
                    print(f"已删除监控项")
                else:
                    print("序号超出范围")
            except ValueError:
                # 作为代码处理
                config = ConfigManager.remove_watchlist_item(index)
                watchlist = config.get("monitoring", {}).get("watchlist", [])
        
        elif choice == '3':
            break
        
        else:
            print("无效选择，请重新输入")

def manage_settings():
    """管理系统设置"""
    config = ConfigManager.load_config()
    
    while True:
        print("\n==== 系统设置管理 ====")
        
        # 显示当前Tushare设置
        ts_token = config.get("api_settings", {}).get("tushare_token", "")
        print(f"Tushare Token: {'已设置' if ts_token else '未设置'}")
        
        # 显示当前方糖设置
        serverchan_config = config.get("serverchan_settings", {})
        serverchan_status = bool(serverchan_config.get("sckey"))
        print(f"方糖SCKEY: {'已设置' if serverchan_status else '未设置'}")
        
        # 显示当前微信设置（保留但不建议使用）
        wechat_config = config.get("wechat_settings", {})
        wechat_status = all([
            wechat_config.get("corp_id"),
            wechat_config.get("corp_secret"),
            wechat_config.get("agent_id")
        ])
        print(f"企业微信配置: {'已完成' if wechat_status else '未完成'} (不建议使用)")
        
        # 显示当前监控设置
        monitoring_config = config.get("monitoring", {})
        print(f"检查间隔: {monitoring_config.get('check_interval', 60)}分钟")
        print(f"回溯天数: {monitoring_config.get('days_back', 30)}天")
        
        print("\n操作选项:")
        print("1. 设置Tushare Token")
        print("2. 设置方糖SCKEY")
        print("3. 设置检查间隔和回溯天数")
        print("4. 测试方糖通知")
        print("5. 返回主菜单")
        
        choice = input("\n请选择操作 (1-5): ")
        
        if choice == '1':
            token = input("请输入Tushare Token: ")
            if token:
                ConfigManager.update_config("api_settings.tushare_token", token)
                print("Tushare Token 已更新")
                # 重新加载配置
                config = ConfigManager.load_config()
                # 初始化Tushare
                initialize_tushare()
            else:
                print("输入为空，取消操作")
        
        elif choice == '2':
            sckey = input("请输入方糖SCKEY: ")
            if sckey:
                ConfigManager.update_config("serverchan_settings.sckey", sckey)
                print("方糖SCKEY已更新")
                # 重新加载配置
                config = ConfigManager.load_config()
            else:
                print("输入为空，取消操作")
        
        elif choice == '3':
            try:
                interval = int(input(f"请输入检查间隔(分钟，默认60): ") or 60)
                days = int(input(f"请输入回溯天数(默认30): ") or 30)
                
                if interval < 1:
                    print("检查间隔必须大于0")
                    continue
                
                if days < 10:
                    print("回溯天数至少为10天")
                    continue
                
                ConfigManager.update_config("monitoring.check_interval", interval)
                ConfigManager.update_config("monitoring.days_back", days)
                print(f"监控设置已更新: 检查间隔={interval}分钟, 回溯天数={days}天")
                # 重新加载配置
                config = ConfigManager.load_config()
            except ValueError:
                print("输入无效，必须是整数")
        
        elif choice == '4':
            notifier = ServerChanNotifier()
            if notifier.enabled:
                success = notifier.send_notification(
                    "测试通知",
                    """这是一条测试通知消息。
如果您收到这条消息，说明方糖Server酱通知配置成功！

您可以开始使用底分型策略监控系统了。""",
                    "info"
                )
                
                if success:
                    print("测试通知发送成功，请检查您的微信")
                else:
                    print("测试通知发送失败，请检查方糖SCKEY是否正确")
            else:
                print("方糖SCKEY尚未配置，无法发送测试通知，请先设置SCKEY")
        
        elif choice == '5':
            break
        
        else:
            print("无效选择，请重新输入")

def display_welcome():
    """显示欢迎信息"""
    # 确保配置文件存在
    ConfigManager.load_config()
    
    # 初始化Tushare API
    initialize_tushare()
    
    # 打印欢迎信息
    print("""
=====================================================
   底分型策略微信通知系统 v1.1
   
   本程序监控股票/指数，在发现底分型买入信号或顶分型
   卖出信号时通过方糖Server酱发送通知，帮助交易者把握交易时机
=====================================================
""")

def display_menu():
    """显示主菜单"""
    print("\n==== 主菜单 ====")
    print("1. 启动自选股监控")
    print("2. 管理自选股监控列表")
    print("3. 系统设置")
    print("4. 退出程序")

def setup_and_run():
    """设置并运行程序"""
    display_welcome()
    
    # 检测是否在服务模式下运行（无法接收用户输入的环境）
    import os
    # 如果存在环境变量或特殊文件，表示是服务模式
    is_service_mode = os.environ.get('RUN_AS_SERVICE') == '1' or os.path.exists('/run/systemd/system')
    
    if is_service_mode:
        logger.info("检测到以服务模式运行，自动启动监控...")
        # 自动选择选项1：启动自选股监控
        run_multi_monitor()  # 使用原函数名
        return
    
    # 交互式菜单模式
    while True:
        display_menu()
        try:
            choice = input("\n请选择操作 (1-4): ")
            
            if choice == '1':
                run_multi_monitor()  # 使用原函数名
            elif choice == '2':
                manage_watchlist()
            elif choice == '3':
                manage_settings()  # 使用原函数名
            elif choice == '4':
                logger.info("程序已退出")
                print("谢谢使用，再见！")
                break
            else:
                print("无效的选择，请重试。")
        except (KeyboardInterrupt, EOFError):
            logger.info("程序被用户中断")
            print("\n程序已被中断，退出...")
            break
        except Exception as e:
            logger.error(f"发生未知错误: {str(e)}")
            print(f"发生错误: {str(e)}")


if __name__ == "__main__":
    setup_and_run()
