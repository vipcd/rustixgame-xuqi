import os
import time
import requests
from urllib.parse import urlparse
from seleniumbase import Driver

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
PROXY_URL = os.getenv("PROXY_URL", "http://127.0.0.1:10809")
RUSTIX_USERNAME = os.getenv("RUSTIX_USERNAME", "")
RUSTIX_PASSWORD = os.getenv("RUSTIX_PASSWORD", "")

# 伪装 Windows 桌面版 Chrome User-Agent，抹去 Linux Headless 特征
WIN_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

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
    """发送 Telegram 通知"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送")
        return
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message}
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

    try:
        resp = requests.post(url, json=payload, proxies=proxies, timeout=10)
        if resp.status_code != 200 and proxies:
            resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("🟢 Telegram 通知发送成功")
        else:
            print(f"🔴 Telegram 发送失败: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")

def main():
    print("🚀 启动 Rustix 自动化控制流程（Chrome UC 伪装模式）...")
    
    try:
        origin_url, target_url, api_url = parse_urls()
        print(f"🌐 面板主页: {target_url}")
        print(f"📡 目标 API 地址: {api_url}")
    except Exception as e:
        err_msg = f"💥 配置校验错误: {str(e)}"
        print(err_msg)
        send_telegram_msg(err_msg)
        return

    # 重新配置 Chrome 防检测参数
    driver_kwargs = {
        "browser": "chrome",
        "uc": True,
        "headless": True,
        "agent": WIN_USER_AGENT,
        "disable_csp": True,
    }
    
    if PROXY_URL:
        driver_kwargs["proxy"] = PROXY_URL
        print(f"🌐 启用代理: {PROXY_URL}")

    driver = Driver(**driver_kwargs)
    
    try:
        print(f"🌐 正在通过 Chrome UC 打开目标站点: {target_url}")
        driver.uc_open_with_reconnect(target_url, reconnect_time=8)
        time.sleep(5)

        page_source = driver.page_source

        # 检查是否依然被 Access denied 拦截
        if "Access denied" in page_source:
            raise PermissionError("【Access denied】当前代理节点 IP 已被站点/Cloudflare 标记黑名单。请在 parse_node.py 中更换节点，或更新 NODE_LINK 订阅。")

        if "ERR_CONNECTION_CLOSED" in page_source or "This site can’t be reached" in page_source:
            raise ConnectionError("代理节点连接异常或连不上目标站点")

        if "Just a moment" in page_source or "Cloudflare" in page_source or "Verify you are human" in page_source:
            print("🛡️ 检测到 Cloudflare 验证屏障，触发模拟人手点击...")
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

        print("📡 在 Chrome 内部直接注入 JS fetch 发送 API 请求...")
        
        js_script = """
        const callback = arguments[arguments.length - 1];
        const targetApi = arguments[0];

        fetch(targetApi, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/plain, */*'
            }
        })
        .then(async (response) => {
            const text = await response.text();
            callback({ status: response.status, body: text });
        })
        .catch((err) => {
            callback({ error: err.toString() });
        });
        """

        driver.set_script_timeout(20)
        res = driver.execute_async_script(js_script, api_url)

        if "error" in res:
            print(f"❌ 浏览器内部 Fetch 执行出错: {res['error']}")
            send_telegram_msg(f"❌ Rustix 操作失败（Fetch 异常）\n\n错误信息: {res['error']}")
        else:
            status_code = res.get("status")
            body = res.get("body", "")
            print(f"🔍 API 响应状态码: {status_code}")
            print(f"🔍 API 响应内容: {body[:300]}")

            if status_code == 200:
                print("✅ API 执行成功")
                send_telegram_msg(f"✅ Rustix 操作成功\n\n状态码: {status_code}\n返回数据: {body}")
            else:
                print(f"❌ API 执行失败: {status_code}")
                send_telegram_msg(f"❌ Rustix 操作失败\n\n状态码: {status_code}\n响应内容: {body[:200]}")

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
