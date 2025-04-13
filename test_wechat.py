#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试企业微信通知功能
"""
import os
import json
import time
import requests

def send_wechat_message():
    # 从配置文件读取企业微信配置
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        
        wechat_config = config.get("wechat_settings", {})
        corp_id = wechat_config.get("corp_id")
        corp_secret = wechat_config.get("corp_secret")
        agent_id = wechat_config.get("agent_id")
        
        if not all([corp_id, corp_secret, agent_id]):
            print("企业微信配置不完整!")
            return False
        
        print(f"企业微信配置信息：")
        print(f"- Corp ID: {corp_id}")
        print(f"- Secret: {corp_secret[:5]}...{corp_secret[-5:]}")
        print(f"- Agent ID: {agent_id}")
        
        # 获取访问令牌
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={corp_secret}"
        token_response = requests.get(token_url)
        token_data = token_response.json()
        
        if token_data.get("errcode") != 0:
            print(f"获取token失败: {token_data}")
            return False
        
        access_token = token_data.get("access_token")
        print(f"成功获取访问令牌!")
        
        # 发送消息
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        message = {
            "touser": "@all",
            "msgtype": "markdown",
            "agentid": agent_id,
            "markdown": {
                "content": """# <font color="#10aeff">测试通知</font>
**这是一条测试消息**
- 如果您收到此消息，说明企业微信通知配置成功
- 您可以正常使用底分型策略微信通知系统

*发送时间: {}*
""".format(time.strftime("%Y-%m-%d %H:%M:%S"))
            }
        }
        
        send_response = requests.post(send_url, json=message)
        send_data = send_response.json()
        
        if send_data.get("errcode") == 0:
            print("消息发送成功!")
            return True
        else:
            print(f"消息发送失败: {send_data}")
            return False
            
    except Exception as e:
        print(f"发送通知时出错: {e}")
        return False

if __name__ == "__main__":
    print("正在测试企业微信通知功能...")
    result = send_wechat_message()
    if result:
        print("测试成功，您应该已经收到了微信通知!")
    else:
        print("测试失败，请检查配置和网络连接。")
