import tushare as ts
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime
import time
import requests
import json
import os

# 自定义技术指标计算函数，替代talib
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

# 微信通知功能
class WeChatNotifier:
    def __init__(self, corp_id=None, corp_secret=None, agent_id=None):
        """
        初始化微信通知器
        :param corp_id: 企业微信企业ID
        :param corp_secret: 企业微信应用Secret
        :param agent_id: 企业微信应用ID
        """
        # 尝试从环境变量读取配置
        self.corp_id = corp_id or os.environ.get('WECHAT_CORP_ID')
        self.corp_secret = corp_secret or os.environ.get('WECHAT_CORP_SECRET')
        self.agent_id = agent_id or os.environ.get('WECHAT_AGENT_ID')
        self.token = None
        self.token_expires_time = 0
        
        # 检查配置是否完整
        self.enabled = all([self.corp_id, self.corp_secret, self.agent_id])
        if not self.enabled:
            print("警告: 微信通知未配置完整，将不会发送通知。请设置环境变量或在初始化时提供参数。")
    
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
                print(f"获取微信token失败: {response_json}")
                return None
        except Exception as e:
            print(f"获取微信token异常: {e}")
            return None
    
    def send_notification(self, title, content, level="info"):
        """
        发送微信通知
        :param title: 通知标题
        :param content: 通知内容
        :param level: 通知级别(info/warning/error)对应不同的文本颜色
        """
        if not self.enabled:
            print(f"微信通知未启用，消息未发送: {title}\n{content}")
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
                print(f"微信通知发送成功: {title}")
                return True
            else:
                print(f"微信通知发送失败: {response_json}")
                return False
        except Exception as e:
            print(f"微信通知发送异常: {e}")
            return False

# 设置Tushare token（需要替换为您自己的token）
# 请在tushare网站注册并获取token：https://tushare.pro/register?reg=7
ts.set_token('d2c5df3dfe8ad080573b92e7f29617f4d295edfe509688a2084cdab4')
pro = ts.pro_api()

class BottomPatternStrategy:
    def __init__(self, stock_code, start_date, end_date, wechat_notifier=None):
        self.stock_code = stock_code
        self.start_date = start_date
        self.end_date = end_date
        self.data = None
        self.bottom_results = []  # 改名为bottom_results
        self.top_results = []  # 新增顶分型结果列表
        # 添加微信通知器
        self.wechat = wechat_notifier or WeChatNotifier()
    
    def get_data(self):
        """获取股票数据"""
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
                df = pro.index_daily(ts_code=code, start_date=self.start_date, end_date=self.end_date)
            else:
                # 获取股票日线数据
                df = pro.daily(ts_code=code, start_date=self.start_date, end_date=self.end_date)
            
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
            print(f"获取数据失败: {e}")
            return pd.DataFrame()
    
    def identify_bottom_pattern(self):
        """识别底分型形态，使用增强条件"""
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
        """识别顶分型形态，使用增强条件"""
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
    
    def backtest_strategy_realtime(self, hold_days=10, use_stop_loss=True, stop_loss_pct=5, use_trailing_stop=True):
        """回测底分型买入、顶分型卖出策略效果，包含止损机制，避免前视偏差"""
        if self.data is None:
            self.get_data()
        
        df = self.data.copy()
        trades = []
        
        # 记录当前的持仓状态
        holding = False
        buy_price = 0
        buy_date = ''
        buy_reason = []
        highest_price = 0  # 用于跟踪止损
        
        # 记录识别到的信号，在下一个交易日执行
        pending_buy_signal = False
        pending_buy_reason = []
        pending_sell_signal = False
        pending_sell_reason = ""
        
        # 按日期顺序逐日检查
        for i in range(2, len(df)):
            current_date = df['trade_date'].iloc[i]
            current_price = df['close'].iloc[i]
            current_high = df['high'].iloc[i]
            
            # 更新持仓中的最高价
            if holding and current_high > highest_price:
                highest_price = current_high
            
            # 执行待处理的买入信号
            if pending_buy_signal and not holding:
                buy_price = df['open'].iloc[i]  # 以开盘价买入
                buy_date = current_date
                buy_reason = pending_buy_reason
                holding = True
                highest_price = buy_price  # 初始化最高价
                print(f"日期 {current_date} 开盘执行底分型买入信号，以 {buy_price:.2f} 买入")
                pending_buy_signal = False
            
            # 执行待处理的卖出信号
            if pending_sell_signal and holding:
                sell_price = df['open'].iloc[i]  # 以开盘价卖出
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
                    'sell_reason': pending_sell_reason,
                    'profit_pct': profit_pct,
                    'hold_days': (pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days
                })
                
                print(f"日期 {current_date} 开盘执行{pending_sell_reason}卖出信号，以 {sell_price:.2f} 卖出，收益率 {profit_pct:.2f}%")
                
                # 重置持仓状态
                holding = False
                pending_sell_signal = False
            
            # 只使用截至当前日期的数据检测底分型和顶分型
            current_data = df.iloc[:i+1].copy()  # 包含当前日期的所有历史数据
            
            # 检查是否可以产生新的买入信号（未持仓且无待处理信号时）
            if not holding and not pending_buy_signal and i >= 2:
                prev_idx = i - 1  # 前一天的索引
                # 检查前一天的K线是否形成底分型（不使用未来数据）
                is_bottom = (current_data['low'].iloc[prev_idx] < current_data['low'].iloc[prev_idx-1] and 
                             current_data['low'].iloc[prev_idx] < current_data['low'].iloc[prev_idx+1])
                
                if is_bottom:
                    # 计算底分型评分
                    score = 0
                    reason = []
                    
                    # 条件1：当前K线收盘价高于开盘价（阳线）
                    if current_data['close'].iloc[prev_idx] > current_data['open'].iloc[prev_idx]:
                        score += 1
                        reason.append("阳线")
                    
                    # 条件2：成交量放大
                    if current_data['vol'].iloc[prev_idx] > current_data['vol'].iloc[prev_idx-1]:
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
                       current_data['macd_hist'].iloc[prev_idx] > current_data['macd_hist'].iloc[prev_idx-1]:
                        score += 1.5
                        reason.append("MACD底部反转")
                    
                    # 如果分数达到阈值，则产生买入信号，待下一个交易日执行
                    if score >= 3:
                        pending_buy_signal = True
                        pending_buy_reason = reason
                        pattern_date = current_data['trade_date'].iloc[prev_idx]
                        signal_msg = f"日期 {current_date} 收盘识别到 {pattern_date} 形成底分型，下一交易日开盘买入"
                        print(signal_msg)
                        
                        # 发送微信通知
                        if self.wechat.enabled:
                            title = f"🔔 底分型买入信号提醒 ({self.stock_code})"
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
                            self.wechat.send_notification(title, content, "info")
            
            # 检查是否产生新的卖出信号（持仓中且无待处理信号时）
            if holding and not pending_sell_signal:
                sell_reason_text = None
                
                # 检查前一日是否形成顶分型
                if i >= 2:
                    prev_idx = i - 1
                    is_top = (current_data['high'].iloc[prev_idx] > current_data['high'].iloc[prev_idx-1] and 
                             current_data['high'].iloc[prev_idx] > current_data['high'].iloc[prev_idx+1])
                    
                    if is_top:
                        # 计算顶分型评分
                        score = 0
                        
                        # 条件1：当前K线收盘价低于开盘价（阴线）
                        if current_data['close'].iloc[prev_idx] < current_data['open'].iloc[prev_idx]:
                            score += 1
                        
                        # 条件2：成交量放大
                        if current_data['vol'].iloc[prev_idx] > current_data['vol'].iloc[prev_idx-1]:
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
                           current_data['macd_hist'].iloc[prev_idx] < current_data['macd_hist'].iloc[prev_idx-1]:
                            score += 1.5
                        
                        # 如果分数达到阈值，确认为顶分型卖出信号，待下一个交易日执行
                        if score >= 3:
                            sell_reason_text = "顶分型"
                            pattern_date = current_data['trade_date'].iloc[prev_idx]
                            signal_msg = f"日期 {current_date} 收盘识别到 {pattern_date} 形成顶分型，下一交易日开盘卖出"
                            print(signal_msg)
                            
                            # 发送微信通知
                            if self.wechat.enabled:
                                title = f"⚠️ 顶分型卖出信号提醒 ({self.stock_code})"
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
                                self.wechat.send_notification(title, content, "warning")
                
                # 检查止损条件 - 这些是实时交易执行的，不需要等到下一交易日
                if use_stop_loss and current_price <= buy_price * (1 - stop_loss_pct/100):
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
                    print(signal_msg)
                    
                    # 发送微信通知
                    if self.wechat.enabled:
                        title = f"🚨 止损卖出通知 ({self.stock_code})"
                        content = f"""**触发止损卖出信号**
- 卖出日期: {sell_date}
- 卖出价格: {sell_price:.2f}
- 买入价格: {buy_price:.2f}
- 亏损比例: {profit_pct:.2f}%
- 持有天数: {(pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days}天
- 止损类型: 固定止损 ({stop_loss_pct}%)

**注意: 此卖出已自动执行，无需手动操作**
"""
                        self.wechat.send_notification(title, content, "error")
                    
                    # 重置持仓状态
                    holding = False
                    continue
                
                # 检查跟踪止损条件 - 这些是实时交易执行的，不需要等到下一交易日
                if use_trailing_stop and highest_price > buy_price and current_price <= highest_price * 0.95:
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
                    print(signal_msg)
                    
                    # 发送微信通知
                    if self.wechat.enabled:
                        title = f"🚨 跟踪止损卖出通知 ({self.stock_code})"
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
                    self.wechat.send_notification(title, content, level)
                    
                    # 重置持仓状态
                    holding = False
                    continue
                
                # 如果有顶分型卖出信号，设置待处理标志
                if sell_reason_text:
                    pending_sell_signal = True
                    pending_sell_reason = sell_reason_text
        
        # 如果最后还在持仓，使用最后一天的收盘价平仓
        if holding and len(df) > 0:
            sell_price = df['close'].iloc[-1]
            sell_date = df['trade_date'].iloc[-1]
            
            profit_pct = (sell_price - buy_price) / buy_price * 100
            
            trades.append({
                'buy_date': buy_date,
                'buy_price': buy_price,
                'buy_reason': buy_reason,
                'sell_date': sell_date,
                'sell_price': sell_price,
                'sell_reason': '回测结束',
                'profit_pct': profit_pct,
                'hold_days': (pd.to_datetime(sell_date) - pd.to_datetime(buy_date)).days
            })
        
        if trades:
            avg_profit = sum(t['profit_pct'] for t in trades) / len(trades)
            win_rate = sum(1 for t in trades if t['profit_pct'] > 0) / len(trades)
            
            return {
                'total_trades': len(trades),
                'avg_profit_pct': avg_profit,
                'win_rate': win_rate,
                'total_profit_pct': sum(t['profit_pct'] for t in trades),
                'max_profit_pct': max(t['profit_pct'] for t in trades) if trades else 0,
                'max_loss_pct': min(t['profit_pct'] for t in trades) if trades else 0,
                'avg_hold_days': sum(t['hold_days'] for t in trades) / len(trades) if trades else 0,
                'details': trades
            }
        else:
            return "没有足够的交易信号进行回测"
    
    def check_recent_pattern(self, start_date, end_date):
        """检查特定日期范围内是否有底分型"""
        if self.data is None:
            self.get_data()
        
        # 筛选日期范围内的数据
        df = self.data.copy()
        filtered_df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        
        if filtered_df.empty:
            return "所选日期范围内没有数据"
        
        print(f"\n检查日期范围 {start_date} 至 {end_date} 的分型情况")
        
        # 显示该范围的数据
        print(f"该范围内有 {len(filtered_df)} 条数据")
        print("日期\t\t开盘\t\t最高\t\t最低\t\t收盘\t\t涨跌幅")
        for i, row in filtered_df.iterrows():
            pct_chg = row.get('pct_chg', (row['close'] / row['open'] - 1) * 100)
            print(f"{row['trade_date']}\t{row['open']:.2f}\t\t{row['high']:.2f}\t\t{row['low']:.2f}\t\t{row['close']:.2f}\t\t{pct_chg:.2f}%")
        
        # 查找底分型
        bottom_patterns = []
        for pattern in self.bottom_results:
            if start_date <= pattern['date'] <= end_date:
                bottom_patterns.append(pattern)
        
        # 检查是否有底分型的征兆
        has_potential_bottom = False
        potential_reason = []
        
        # 检查条件1: 是否有连续下跌后的止跌迹象
        if len(filtered_df) >= 3:
            last_3days = filtered_df.iloc[-3:]
            if all(last_3days['close'].diff().fillna(0).iloc[1:] < 0):  # 连续下跌
                if last_3days['close'].iloc[-1] > last_3days['open'].iloc[-1]:  # 最后一天收阳
                    has_potential_bottom = True
                    potential_reason.append("连续下跌后收阳")
        
        # 检查条件2: RSI是否处于超卖区域
        if 'rsi' in filtered_df.columns and len(filtered_df) > 0:
            last_rsi = filtered_df['rsi'].iloc[-1]
            if last_rsi < 30:
                has_potential_bottom = True
                potential_reason.append(f"RSI超卖({last_rsi:.2f})")
        
        # 检查条件3: 布林带下轨支撑
        if all(col in filtered_df.columns for col in ['bb_lower']) and len(filtered_df) > 0:
            last_price = filtered_df['close'].iloc[-1]
            last_bb_lower = filtered_df['bb_lower'].iloc[-1]
            if last_price <= last_bb_lower * 1.02:  # 接近或触及下轨
                has_potential_bottom = True
                potential_reason.append("布林带下轨支撑")
        
        # 输出分析结果
        if bottom_patterns:
            print(f"\n在所选日期范围内发现 {len(bottom_patterns)} 个底分型:")
            for i, p in enumerate(bottom_patterns):
                reasons = ', '.join(p['reason']) if 'reason' in p else ''
                print(f"{i+1}. 日期: {p['date']}, 价格: {p['price']:.2f}, 最低点: {p['low']:.2f}, 原因: {reasons}")
            return bottom_patterns
        elif has_potential_bottom:
            print(f"\n该范围内没有完全符合条件的底分型，但有底部征兆:")
            for reason in potential_reason:
                print(f"- {reason}")
            return "有底部征兆"
        else:
            print("\n该范围内没有发现底分型，也没有明显的底部征兆")
            return "无底分型"
    
    def plot_patterns(self):
        """绘制底分型和顶分型形态图，添加布林带显示"""
        if self.data is None:
            return "没有数据可绘制"
        
        if not self.bottom_results:
            self.identify_bottom_pattern()
            
        if not self.top_results:
            self.identify_top_pattern()
            
        if not self.bottom_results and not self.top_results:
            return "没有识别到任何分型"
        
        df = self.data.copy()
        
        # 设置通用字体，避免中文显示问题
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'Songti SC', 'PingFang HK', 'Apple Color Emoji', 'sans-serif']
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['axes.unicode_minus'] = False  # 解决坐标轴负号显示问题
        
        plt.figure(figsize=(14, 8))
        
        # 绘制主图
        plt.subplot(2, 1, 1)
        plt.plot(df.index, df['close'], label='收盘价', color='black', linewidth=1.5)
        plt.plot(df.index, df['ma5'], label='5日均线', linestyle='--', color='blue', linewidth=1)
        plt.plot(df.index, df['ma10'], label='10日均线', linestyle='-.', color='purple', linewidth=1)
        plt.plot(df.index, df['ma20'], label='20日均线', linestyle=':', color='green', linewidth=1)
        
        # 添加布林带
        if 'bb_upper' in df.columns and 'bb_middle' in df.columns and 'bb_lower' in df.columns:
            plt.plot(df.index, df['bb_upper'], label='布林上轨', color='red', alpha=0.6, linewidth=1)
            plt.plot(df.index, df['bb_middle'], label='布林中轨', color='gray', alpha=0.6, linewidth=1)
            plt.plot(df.index, df['bb_lower'], label='布林下轨', color='green', alpha=0.6, linewidth=1)
            
            # 给布林带填充颜色
            plt.fill_between(df.index, df['bb_upper'], df['bb_lower'], color='lightskyblue', alpha=0.15)
        
        # 标记底分型点位
        for pattern in self.bottom_results:
            pattern_idx = df[df['trade_date'] == pattern['date']].index[0]
            plt.scatter(pattern_idx, df['low'].iloc[pattern_idx], color='red', s=100, marker='^', 
                       label='底分型' if pattern == self.bottom_results[0] else "")
        
        # 标记顶分型点位
        for pattern in self.top_results:
            pattern_idx = df[df['trade_date'] == pattern['date']].index[0]
            plt.scatter(pattern_idx, df['high'].iloc[pattern_idx], color='green', s=100, marker='v', 
                       label='顶分型' if pattern == self.top_results[0] else "")
        
        plt.title(f"{self.stock_code} 分型识别结果", fontsize=15)
        plt.ylabel('价格', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend(loc='best')
        
        # 绘制MACD子图
        if 'macd' in df.columns and 'macd_signal' in df.columns and 'macd_hist' in df.columns:
            plt.subplot(2, 1, 2)
            
            # 绘制MACD柱状图
            plt.bar(df.index, df['macd_hist'], color=['red' if x > 0 else 'green' for x in df['macd_hist']], 
                    label='MACD柱状', alpha=0.7)
            
            # 绘制MACD线和信号线
            plt.plot(df.index, df['macd'], label='MACD线', color='blue', linewidth=1)
            plt.plot(df.index, df['macd_signal'], label='信号线', color='red', linewidth=1)
            
            # 添加0轴线
            plt.axhline(y=0, color='black', linestyle='-', alpha=0.3)
            
            plt.title("MACD指标", fontsize=12)
            plt.ylabel('值', fontsize=10)
            plt.grid(True, alpha=0.3)
            plt.legend(loc='best')
        
        plt.xlabel('日期', fontsize=12)
        plt.tight_layout()
        plt.show()
        
        # 添加布林带解释图
        self.explain_bollinger_bands()

    def explain_bollinger_bands(self):
        """解释布林带的交易逻辑"""
        # 设置通用字体，避免中文显示问题
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'Songti SC', 'PingFang HK', 'Apple Color Emoji', 'sans-serif']
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建示例数据
        x = np.arange(100)
        price = 100 + 15 * np.sin(x/10) + np.random.randn(100) * 3
        
        # 计算布林带
        window = 20
        middle_band = np.convolve(price, np.ones(window)/window, mode='same')
        std = np.array([np.std(price[max(0, i-window):i+1]) for i in range(len(price))])
        upper_band = middle_band + 2 * std
        lower_band = middle_band - 2 * std
        
        # 创建两个子图
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # 上面的图: 价格和布林带的关系
        ax1.plot(x, price, label='价格', color='black')
        ax1.plot(x, middle_band, label='中轨 (20日均线)', color='blue', linestyle='--')
        ax1.plot(x, upper_band, label='上轨 (中轨+2σ)', color='red')
        ax1.plot(x, lower_band, label='下轨 (中轨-2σ)', color='green')
        
        # 填充布林带区域
        ax1.fill_between(x, upper_band, lower_band, color='lightskyblue', alpha=0.2)
        
        # 标记买入点和卖出点
        buy_points = []
        sell_points = []
        
        for i in range(5, len(price)-1):
            # 价格触及下轨后反弹
            if price[i-1] <= lower_band[i-1] and price[i] > price[i-1]:
                buy_points.append(i)
            
            # 价格触及上轨后回落
            if price[i-1] >= upper_band[i-1] and price[i] < price[i-1]:
                sell_points.append(i)
        
        # 绘制买入和卖出点
        for bp in buy_points[:4]:  # 只展示前4个
            ax1.scatter(bp, price[bp], color='red', s=100, marker='^')
            ax1.annotate('买入', xy=(bp, price[bp]), xytext=(bp+1, price[bp]-3), 
                         arrowprops=dict(arrowstyle='->'))
        
        for sp in sell_points[:4]:  # 只展示前4个
            ax1.scatter(sp, price[sp], color='green', s=100, marker='v')
            ax1.annotate('卖出', xy=(sp, price[sp]), xytext=(sp+1, price[sp]+3), 
                         arrowprops=dict(arrowstyle='->'))
        
        ax1.set_title('布林带基本用法图解', fontsize=15)
        ax1.set_ylabel('价格', fontsize=12)
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # 下面的图: 展示带宽变化
        bandwidth = (upper_band - lower_band) / middle_band * 100  # 带宽百分比
        
        # 绘制带宽
        ax2.plot(x, bandwidth, label='布林带宽(%)', color='purple')
        ax2.axhline(y=np.percentile(bandwidth, 10), color='green', linestyle='--', 
                    label='低波动区间 (10%分位)')
        ax2.axhline(y=np.percentile(bandwidth, 90), color='red', linestyle='--', 
                    label='高波动区间 (90%分位)')
        
        # 标记带宽挤压区域
        squeeze_points = []
        for i in range(20, len(bandwidth)-1):
            if (bandwidth[i] < np.percentile(bandwidth, 10) and 
                bandwidth[i+1] > bandwidth[i]):
                squeeze_points.append(i)
        
        # 标记带宽扩张区域
        expansion_points = []
        for i in range(20, len(bandwidth)-1):
            if (bandwidth[i] > np.percentile(bandwidth, 90) and 
                bandwidth[i+1] < bandwidth[i]):
                expansion_points.append(i)
        
        # 标记挤压点和扩张点
        for sp in squeeze_points[:3]:
            ax2.scatter(sp, bandwidth[sp], color='blue', s=100, marker='o')
            ax2.annotate('带宽挤压\n(突破信号)', xy=(sp, bandwidth[sp]), 
                         xytext=(sp+5, bandwidth[sp]+2),
                         arrowprops=dict(arrowstyle='->'))
            
            # 同时在价格图上标记
            ax1.axvline(x=sp, color='blue', linestyle=':', alpha=0.5)
            ax1.text(sp+1, np.max(price), '带宽挤压', color='blue')
        
        for ep in expansion_points[:3]:
            ax2.scatter(ep, bandwidth[ep], color='orange', s=100, marker='o')
            ax2.annotate('带宽扩张\n(趋势确认)', xy=(ep, bandwidth[ep]), 
                         xytext=(ep+5, bandwidth[ep]-5),
                         arrowprops=dict(arrowstyle='->'))
            
            # 同时在价格图上标记
            ax1.axvline(x=ep, color='orange', linestyle=':', alpha=0.5)
            ax1.text(ep+1, np.min(price), '带宽扩张', color='orange')
        
        ax2.set_title('布林带宽变化与市场波动关系', fontsize=15)
        ax2.set_xlabel('时间', fontsize=12)
        ax2.set_ylabel('带宽百分比', fontsize=12)
        ax2.legend(loc='upper right')
        ax2.grid(True, alpha=0.3)
        
        # 添加文本说明
        plt.figtext(0.05, 0.01, """布林带交易策略详解:
        
1. 布林带组成: 中轨(20日均线)、上轨(中轨+2倍标准差)、下轨(中轨-2倍标准差)
2. 基本交易信号:
   - 买入信号: 价格触及或跌破下轨后反弹(底部确认)
   - 卖出信号: 价格触及或突破上轨后回落(顶部确认)

3. 高级应用:
   - 带宽挤压: 表示波动率降低，市场蓄势，常出现在行情爆发前，可提前布局
   - 带宽扩张: 表示波动率增加，趋势确立，可顺势操作
   - W底形态: 价格两次触及下轨形成W形，第二个低点高于第一个低点，强力买入信号
   - M顶形态: 价格两次触及上轨形成M形，第二个高点低于第一个高点，强力卖出信号

4. 本策略关键点:
   - 结合底分型+布林下轨支撑+RSI超卖，形成更可靠的买入信号
   - 结合顶分型+布林上轨阻力+RSI超买，形成更可靠的卖出信号
   - 在震荡行情中效果更佳，强趋势中应谨慎使用""", 
        fontsize=10, ha='left')
        
        plt.tight_layout(rect=[0, 0.05, 1, 0.97])  # 为底部说明文字留出空间
        plt.show()

def run_live_monitor(stock_code='399300', days_back=30, check_interval=60):
    """
    实时监控市场，发送买卖信号
    :param stock_code: 股票或指数代码
    :param days_back: 回溯多少天的数据进行分析
    :param check_interval: 检查间隔，单位为分钟
    """
    wechat = WeChatNotifier()
    
    if not wechat.enabled:
        print("微信通知未配置，将无法发送实时信号通知")
        print("请设置以下环境变量:")
        print("WECHAT_CORP_ID: 企业微信企业ID")
        print("WECHAT_CORP_SECRET: 企业微信应用Secret")
        print("WECHAT_AGENT_ID: 企业微信应用ID")
        answer = input("是否继续运行监控程序? (y/n): ")
        if answer.lower() != 'y':
            return
    
    print(f"开始监控 {stock_code}，每 {check_interval} 分钟检查一次")
    
    # 发送启动通知
    if wechat.enabled:
        wechat.send_notification(
            f"🔄 底分型策略监控启动 ({stock_code})",
            f"已开始监控 {stock_code}，将每 {check_interval} 分钟检查一次市场数据，发现信号将立即通知。",
            "info"
        )
    
    # 记录最后一次发现的信号，避免重复提醒
    last_bottom_date = None
    last_top_date = None
    
    while True:
        try:
            # 计算时间范围
            end_date = datetime.datetime.now().strftime('%Y%m%d')
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime('%Y%m%d')
            
            # 创建策略实例
            strategy = BottomPatternStrategy(stock_code, start_date, end_date, wechat)
            
            # 获取数据
            df = strategy.get_data()
            if df.empty:
                print(f"未获取到 {stock_code} 的数据，请检查代码是否正确")
                time.sleep(check_interval * 60)
                continue
                
            # 识别底分型
            bottom_patterns = strategy.identify_bottom_pattern()
            
            # 检查是否有新的底分型
            if bottom_patterns and bottom_patterns[-1]['date'] != last_bottom_date:
                last_pattern = bottom_patterns[-1]
                last_bottom_date = last_pattern['date']
                
                # 检查是否是最近的信号(最近3天内)
                pattern_date = pd.to_datetime(last_pattern['date'])
                now = pd.to_datetime(datetime.datetime.now().strftime('%Y%m%d'))
                days_diff = (now - pattern_date).days
                
                if days_diff <= 3:  # 只提醒3天内的信号
                    print(f"发现新底分型: {last_pattern['date']}, 评分: {last_pattern['score']:.1f}")
                    
                    # 发送微信通知
                    if wechat.enabled:
                        title = f"🔔 底分型买入信号 ({stock_code})"
                        content = f"""**识别到底分型买入信号**
- 形成日期: {last_pattern['date']}
- 信号价格: {last_pattern['price']:.2f}
- 信号评分: {last_pattern['score']:.1f}分
- 信号详情: {', '.join(last_pattern['reason'])}

**交易建议**:
- 操作: 买入 {stock_code}
- 时机: 建议在次日开盘时买入
- 止损位: {last_pattern['low']:.2f}下方
"""
                        wechat.send_notification(title, content, "info")
            
            # 识别顶分型
            top_patterns = strategy.identify_top_pattern()
            
            # 检查是否有新的顶分型
            if top_patterns and top_patterns[-1]['date'] != last_top_date:
                last_pattern = top_patterns[-1]
                last_top_date = last_pattern['date']
                
                # 检查是否是最近的信号(最近3天内)
                pattern_date = pd.to_datetime(last_pattern['date'])
                now = pd.to_datetime(datetime.datetime.now().strftime('%Y%m%d'))
                days_diff = (now - pattern_date).days
                
                if days_diff <= 3:  # 只提醒3天内的信号
                    print(f"发现新顶分型: {last_pattern['date']}, 评分: {last_pattern['score']:.1f}")
                    
                    # 发送微信通知
                    if wechat.enabled:
                        title = f"⚠️ 顶分型卖出信号 ({stock_code})"
                        content = f"""**识别到顶分型卖出信号**
- 形成日期: {last_pattern['date']}
- 信号价格: {last_pattern['price']:.2f}
- 信号评分: {last_pattern['score']:.1f}分
- 信号详情: {', '.join(last_pattern['reason'])}

**交易建议**:
- 操作: 卖出 {stock_code}
- 时机: 建议在次日开盘时卖出
- 注意: 市场顶部信号形成，短期可能回调
"""
                        wechat.send_notification(title, content, "warning")
            
            # 休息一段时间再检查
            next_check_time = datetime.datetime.now() + datetime.timedelta(minutes=check_interval)
            print(f"下次检查时间: {next_check_time.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(check_interval * 60)
            
        except Exception as e:
            print(f"监控过程中发生错误: {e}")
            if wechat.enabled:
                wechat.send_notification(
                    f"❌ 底分型策略监控异常 ({stock_code})",
                    f"监控过程中发生错误: {str(e)}\n将在{check_interval}分钟后重试。",
                    "error"
                )
            time.sleep(check_interval * 60)

if __name__ == "__main__":
    # 参数设置
    stock_code = '399300'  # 沪深300指数
    
    # 使用更新的回测周期：2024年9月1日到2025年4月13日
    start_date = '20240901'
    end_date = '20250413'
    
    # 创建微信通知器
    wechat = WeChatNotifier()
    if not wechat.enabled:
        print("提示: 微信通知未配置，将不会发送通知。")
        print("如需启用通知，请设置以下环境变量:")
        print("WECHAT_CORP_ID: 企业微信企业ID")
        print("WECHAT_CORP_SECRET: 企业微信应用Secret")
        print("WECHAT_AGENT_ID: 企业微信应用ID")
    
    print(f"分析沪深300指数，区间: {start_date} 至 {end_date}")
    
    # 创建策略实例
    strategy = BottomPatternStrategy(stock_code, start_date, end_date, wechat)
    
    # 获取数据
    df = strategy.get_data()
    print(f"获取到 {len(df)} 条数据")
    
    # 检查数据日期是否有效
    if not df.empty:
        print(f"数据范围: {df['trade_date'].min()} 至 {df['trade_date'].max()}")
    
    # 使用避免前视偏差的回测函数
    print("\n使用实盘模拟回测 (避免前视偏差):")
    results_realtime = strategy.backtest_strategy_realtime(use_stop_loss=True, stop_loss_pct=5, use_trailing_stop=True)
    
    if isinstance(results_realtime, dict):
        print(f"\n实盘模拟回测结果:")
        print(f"交易次数: {results_realtime['total_trades']}")
        print(f"平均收益率: {results_realtime['avg_profit_pct']:.2f}%")
        print(f"总收益率: {results_realtime['total_profit_pct']:.2f}%")
        print(f"最大单笔收益: {results_realtime['max_profit_pct']:.2f}%")
        print(f"最大单笔亏损: {results_realtime['max_loss_pct']:.2f}%")
        print(f"胜率: {results_realtime['win_rate']*100:.2f}%")
        print(f"平均持仓天数: {results_realtime['avg_hold_days']:.1f}天")
        
        # 输出详细交易记录
        print("\n实盘模拟交易详情:")
        for i, trade in enumerate(results_realtime['details']):
            buy_reasons = ', '.join(trade['buy_reason']) if isinstance(trade['buy_reason'], list) else trade['buy_reason']
            print(f"{i+1}. 买入: {trade['buy_date']}({trade['buy_price']:.2f}), 原因: {buy_reasons}")
            print(f"   卖出: {trade['sell_date']}({trade['sell_price']:.2f}), 原因: {trade['sell_reason']}")
            print(f"   结果: {trade['profit_pct']:.2f}%, 持仓: {trade['hold_days']}天")
    else:
        print(results_realtime)
    
    # 查看特定日期范围是否有底分型
    specific_start_date = '20250405'
    specific_end_date = '20250413'
    print(f"\n特别分析 {specific_start_date} 至 {specific_end_date} 期间的底分型趋势:")
    strategy.check_recent_pattern(specific_start_date, specific_end_date)
    
    # 提示用户是否启动实时监控
    print("\n是否启动实时监控模式? 该模式会定期检查最新数据并发送信号通知")
    choice = input("请输入选择 (y/n): ")
    if choice.lower() == 'y':
        run_live_monitor(stock_code, days_back=30, check_interval=60)
