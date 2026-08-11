import os
import time
import requests
from urllib.parse import urlparse
from seleniumbase import Driver

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
RUSTIX_USERNAME = os.getenv("RUSTIX_USERNAME", "")
RUSTIX_PASSWORD = os.getenv("RUSTIX_PASSWORD", "")

def parse_urls():
    """解析面板地址与 API 路径"""
    raw_url = (os.getenv("RUSTIX_URL") or os.getenv("API_KEY") or "").strip()
    if not raw_url or "your-rustix-domain.com" in raw_url:
        raise ValueError("未检测到有效 RUSTIX_URL，请检查 GitHub Secrets 配置。")

    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        raw_url = "https://" + raw_url

    parsed = urlparse(raw_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    
    path = parsed.path.rstrip('/')
    if path.endswith('/console'):
        base_path = path[:-8]
    else:
        base_path = path

    api_url = f"{origin}{base_path}/api/server/renew"
    return origin, raw_url, api_url

def send_telegram_msg(message: str):
    """通过 GitHub 节点直连发送 Telegram 机器人推送"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送")
        return
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("🟢 Telegram 通知发送成功")
        else:
            print(f"🔴 Telegram 发送失败: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")

def main():
    print("🚀 启动 Rustix 自动化控制流程（GitHub 直连模式）...")
    
    try:
        origin_url, target_url, api_url = parse_urls()
        print(f"🌐 面板主页: {target_url}")
        print(f"📡 目标 API 地址: {api_url}")
    except Exception as e:
        err_msg = f"💥 配置校验错误: {str(e)}"
        print(err_msg)
        send_telegram_msg(err_msg)
        return

    print("🌐 使用 GitHub Actions 原生网络直连启动浏览器...")
    driver = Driver(uc=True, headless=True)
    
    try:
        print(f"🌐 正在访问目标站点: {target_url}")
        driver.uc_open_with_reconnect(target_url, reconnect_time=6)
        time.sleep(3)

        page_source = driver.page_source
        if "ERR_CONNECTION_CLOSED" in page_source or "This site can’t be reached" in page_source:
            raise ConnectionError("页面加载失败，目标站点拒连")

        if "Just a moment" in page_source or "Cloudflare" in page_source:
            print("🛡️ 检测到 Cloudflare 屏障，执行模拟点击...")
            try:
                driver.uc_gui_click_captcha()
            except Exception as e:
                print(f"⚠️ 点击模拟触发异常: {e}")
            time.sleep(6)

        if RUSTIX_USERNAME and RUSTIX_PASSWORD:
            print("🔑 尝试执行账号登录...")
            if driver.is_element_visible("input[name='username']"):
                driver.type("input[name='username']", RUSTIX_USERNAME)
                driver.type("input[name='password']", RUSTIX_PASSWORD)
                driver.click("button[type='submit']")
                time.sleep(5)

        current_url = driver.current_url
        print(f"📍 当前已加载页面: {current_url}")
        driver.save_screenshot("server_status.png")
        print("📸 页面截图已保存为 server_status.png")

        print("🍪 提取 Cookie 与 User-Agent 上下文...")
        cookies = driver.get_cookies()
        user_agent = driver.execute_script("return navigator.userAgent;")
        
        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'])
            
        session.headers.update({
            "User-Agent": user_agent,
            "Referer": current_url,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest"
        })

        print(f"📡 正在直连请求 API: {api_url}")
        response = session.post(api_url, timeout=15)
        print(f"🔍 API 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                res_data = response.json()
            except Exception:
                res_data = response.text
            print(f"✅ API 执行成功: {res_data}")
            send_telegram_msg(f"✅ Rustix 操作成功\n\n状态码: {response.status_code}\n返回数据: {res_data}")
        else:
            print(f"❌ API 执行失败: {response.status_code} - {response.text[:300]}")
            send_telegram_msg(f"❌ Rustix 操作失败\n\n状态码: {response.status_code}\n响应内容: {response.text[:200]}")

    except Exception as e:
        error_info = f"💥 脚本运行异常: {str(e)}"
        print(error_info)
        try:
            driver.save_screenshot("error_status.png")
            print("📸 异常状态截图已保存为 error_status.png")
        except Exception:
            pass
        send_telegram_msg(f"💥 Rustix 脚本运行报错\n\n{str(e)}")
        
    finally:
        driver.quit()
        print("🏁 任务结束。")

if __name__ == "__main__":
    main()
