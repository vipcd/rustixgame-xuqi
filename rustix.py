import os
import time
import requests
from seleniumbase import Driver

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
PROXY_URL = os.getenv("PROXY_URL", "")
RUSTIX_USERNAME = os.getenv("RUSTIX_USERNAME", "")
RUSTIX_PASSWORD = os.getenv("RUSTIX_PASSWORD", "")

def get_target_url():
    """自动获取面板 URL，优先读取 RUSTIX_URL，若空则自动尝试从 API_KEY 中提取网址"""
    url = (os.getenv("RUSTIX_URL") or "").strip()
    api_key = (os.getenv("API_KEY") or "").strip()

    if not url and (api_key.startswith("http://") or api_key.startswith("https://") or "." in api_key):
        url = api_key

    if not url or "your-rustix-domain.com" in url:
        raise ValueError(
            "未检测到面板域名！请检查 GitHub 仓库 Settings -> Secrets 中是否配置了 RUSTIX_URL 或将面板网址填入 API_KEY"
        )

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    return url.rstrip('/')

def send_telegram_msg(message: str):
    """通过 Telegram 机器人发送纯文本推送通知（避免 Markdown 解析异常）"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送")
        return
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message
    }
    
    proxies = None
    if PROXY_URL:
        proxies = {"http": PROXY_URL, "https": PROXY_URL}

    try:
        resp = requests.post(url, json=payload, proxies=proxies, timeout=10)
        if resp.status_code == 200:
            print("🟢 Telegram 通知发送成功")
        else:
            print(f"🔴 Telegram 发送失败: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")

def main():
    print("🚀 启动 Rustix 自动化控制流程...")
    
    try:
        target_url = get_target_url()
        print(f"🌐 目标站点 URL: {target_url}")
    except Exception as e:
        err_msg = f"💥 配置校验错误: {str(e)}"
        print(err_msg)
        send_telegram_msg(err_msg)
        return

    driver_kwargs = {"uc": True, "headless": True}
    if PROXY_URL:
        driver_kwargs["proxy"] = PROXY_URL
        print(f"🌐 浏览器网络代理已生效: {PROXY_URL}")

    driver = Driver(**driver_kwargs)
    
    try:
        print(f"🌐 正在访问目标站点: {target_url}")
        driver.uc_open_with_reconnect(target_url, reconnect_time=6)
        
        time.sleep(3)
        if "Just a moment" in driver.page_source or "Cloudflare" in driver.page_source:
            print("🛡️ 检测到 Cloudflare 屏障，执行物理模拟点击...")
            try:
                driver.uc_gui_click_captcha()
            except Exception as e:
                print(f"⚠️ 点击模拟触发异常或已自动通过: {e}")
            time.sleep(6)

        if RUSTIX_USERNAME and RUSTIX_PASSWORD:
            print("🔑 尝试执行账号登录...")
            if driver.is_element_visible("input[name='username']"):
                driver.type("input[name='username']", RUSTIX_USERNAME)
                driver.type("input[name='password']", RUSTIX_PASSWORD)
                driver.click("button[type='submit']")
                time.sleep(5)

        current_page = driver.current_url
        print(f"📍 当前已加载页面: {current_page}")

        driver.save_screenshot("server_status.png")
        print("📸 页面截图已保存为 server_status.png")

        print("🍪 提取浏览器 Cookie 与 User-Agent 上下文...")
        selenium_cookies = driver.get_cookies()
        user_agent = driver.execute_script("return navigator.userAgent;")
        
        session = requests.Session()
        if PROXY_URL:
            session.proxies = {"http": PROXY_URL, "https": PROXY_URL}

        for cookie in selenium_cookies:
            session.cookies.set(cookie['name'], cookie['value'])
            
        session.headers.update({
            "User-Agent": user_agent,
            "Referer": current_page,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest"
        })

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
            send_telegram_msg(f"✅ Rustix 续期/重启操作成功\n\n状态码: {response.status_code}\n返回数据: {res_data}")
        else:
            print(f"❌ API 执行失败，响应内容: {response.text[:300]}")
            send_telegram_msg(f"❌ Rustix 操作失败\n\n状态码: {response.status_code}\n响应内容: {response.text[:200]}")

    except Exception as e:
        error_info = f"💥 脚本运行过程中发生异常: {str(e)}"
        print(error_info)
        try:
            driver.save_screenshot("error_status.png")
            print("📸 异常状态截图已保存为 error_status.png")
        except Exception:
            pass
        send_telegram_msg(f"💥 Rustix 自动化脚本报错\n\n{str(e)}")
        
    finally:
        driver.quit()
        print("🏁 浏览器实例已关闭，任务结束。")

if __name__ == "__main__":
    main()
