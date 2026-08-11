import os
import time
import requests
from seleniumbase import Driver

# 1. 环境变量读取（支持本地调试与 GitHub Secrets）
RUSTIX_URL = os.getenv("RUSTIX_URL", "https://your-rustix-domain.com")  # 替换为实际 Rustix 域名
RUSTIX_USERNAME = os.getenv("RUSTIX_USERNAME", "")
RUSTIX_PASSWORD = os.getenv("RUSTIX_PASSWORD", "")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

def send_telegram_msg(message: str):
    """通过 Telegram 机器人发送推送通知"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送")
        return
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("🟢 Telegram 通知发送成功")
        else:
            print(f"🔴 Telegram 发送失败: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")

def main():
    print("🚀 启动 Rustix 自动化控制流程...")
    
    # 2. 初始化 SeleniumBase 防检测浏览器
    driver = Driver(uc=True, headless=True)
    
    try:
        target_url = RUSTIX_URL.rstrip('/')
        print(f"🌐 正在访问目标站点: {target_url}")
        driver.uc_open_with_reconnect(target_url, reconnect_time=6)
        
        # 3. 处理 Cloudflare 验证码挑战
        time.sleep(3)
        if "Just a moment" in driver.page_source or "Cloudflare" in driver.page_source:
            print("🛡️ 检测到 Cloudflare 屏障，执行物理模拟点击...")
            try:
                driver.uc_gui_click_captcha()
            except Exception as e:
                print(f"⚠️ 点击模拟触发异常或已自动通过: {e}")
            
            # 等待 Cloudflare 注入 Cookie 并完成跳转
            time.sleep(6)

        # 4. 执行登录流程（如果存在登录表单）
        if RUSTIX_USERNAME and RUSTIX_PASSWORD:
            print("🔑 尝试执行账号登录...")
            if driver.is_element_visible("input[name='username']"):
                driver.type("input[name='username']", RUSTIX_USERNAME)
                driver.type("input[name='password']", RUSTIX_PASSWORD)
                driver.click("button[type='submit']")
                time.sleep(5)

        current_page = driver.current_url
        print(f"📍 当前已加载页面: {current_page}")

        # 5. 核心修复：提取 Selenium 浏览器中的 Cookie 与 User-Agent，构建 Python Request Session
        print("🍪 提取浏览器 Cookie 与 User-Agent 上下文...")
        selenium_cookies = driver.get_cookies()
        user_agent = driver.execute_script("return navigator.userAgent;")
        
        session = requests.Session()
        for cookie in selenium_cookies:
            session.cookies.set(cookie['name'], cookie['value'])
            
        session.headers.update({
            "User-Agent": user_agent,
            "Referer": current_page,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest"
        })

        # 6. 使用 Python 原生 Requests 替代浏览器 JS fetch() 发起 API 操作
        # ⚠️ 请根据 Rustix 实际 API 端点调整 URL 路径（如 /api/server/renew 或 /api/restart）
        api_url = f"{target_url}/api/server/renew"
        print(f"📡 正在通过 Python Session 请求 API: {api_url}")
        
        response = session.post(api_url, timeout=15)
        print(f"🔍 API 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                res_data = response.json()
            except Exception:
                res_data = response.text
            print(f"✅ API 执行成功: {res_data}")
            send_telegram_msg(f"✅ *Rustix 续期/重启操作成功*\n\n*状态码*: `{response.status_code}`\n*返回数据*: `{res_data}`")
        else:
            print(f"❌ API 执行失败，响应内容: {response.text[:300]}")
            send_telegram_msg(f"❌ *Rustix 操作失败*\n\n*状态码*: `{response.status_code}`\n*响应内容*: `{response.text[:200]}`")

    except Exception as e:
        error_info = f"💥 脚本运行过程中发生异常: {str(e)}"
        print(error_info)
        send_telegram_msg(f"💥 *Rustix 自动化脚本报错*\n\n`{str(e)}`")
        
    finally:
        driver.quit()
        print("🏁 浏览器实例已关闭，任务结束。")

if __name__ == "__main__":
    main()
