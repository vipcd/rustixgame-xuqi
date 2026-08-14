import asyncio
import requests
import os
import json
import sys
from playwright.async_api import async_playwright

# --- 从环境变量读取敏感信息 ---
TG_TOKEN = os.environ.get("TG_BOT_TOKEN") or os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
COOKIES_OR_ACCOUNTS = os.environ.get("COOKIES_JSON") or os.environ.get("ACCOUNTS_JSON")
PROXY_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:10809")

LOGIN_URL = "https://my.rustix.me/auth/login"
CONSOLE_URL = "https://my.rustix.me/console"

def send_tg_message(text):
    """发送 Telegram 消息（彻底直连，不走代理，确保报错 100% 能发出）"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ 警告: TG_TOKEN 或 TG_CHAT_ID 未设置，跳过消息发送。")
        return
        
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    formatted_text = f"*✅ rustix.me服务器自动重启通知*\n\n{text}"
    payload = {"chat_id": TG_CHAT_ID, "text": formatted_text, "parse_mode": "Markdown"}
    
    try:
        # GitHub Actions 环境在海外，直连 TG 速度最快且最稳定
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("🟢 TG 消息发送成功")
        else:
            print(f"🔴 TG 发送失败，状态码: {resp.status_code}, 返回: {resp.text}")
    except Exception as e:
        print(f"❌ 发送 TG 消息异常: {e}")

async def process_with_playwright(raw_data):
    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        }
        if PROXY_URL:
            launch_args["proxy"] = {"server": PROXY_URL}
            print(f"🌐 网页流量启用代理: {PROXY_URL}")

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="zh-CN"
        )
        page = await context.new_page()

        try:
            # 智能判断数据是 Cookie 列表还是 账号密码配置
            is_cookie_format = False
            if isinstance(raw_data, list) and len(raw_data) > 0:
                first_item = raw_data[0]
                if isinstance(first_item, dict) and ("name" in first_item or "domain" in first_item):
                    is_cookie_format = True

            if is_cookie_format:
                print("🍪 检测到格式为标准 Cookie 列表，正在注入 Cookie...")
                await context.add_cookies(raw_data)
                print("🌐 正在通过 Cookie 访问控制台...")
                await page.goto(CONSOLE_URL, timeout=60000, wait_until="domcontentloaded")
            else:
                # 解析账号密码结构
                account = raw_data[0] if isinstance(raw_data, list) else raw_data
                user = (
                    account.get('user') or 
                    account.get('username') or 
                    account.get('email') or 
                    account.get('login') or 
                    "单账号用户"
                )
                pwd = account.get('pwd') or account.get('password') or ""
                
                print(f"\n>>> 开始处理账户: {user}")
                print(f"🌐 正在打开登录页面: {LOGIN_URL}")
                await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                page_content = await page.content()
                if "Access denied" in page_content:
                    raise PermissionError("Access denied: 节点 IP 被拒绝或拉黑，请在 GitHub Secrets 更换 NODE_LINK 订阅。")

                # 模拟填写登录
                await page.wait_for_selector('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[1]/div/input', timeout=20000)
                await page.fill('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[1]/div/input', user)
                await page.fill('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[2]/div[2]/div/div/input', pwd)
                await page.click('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[4]/button')

            # 进入管理页/控制台
            await page.wait_for_selector('section', timeout=30000)
            if not page.url.endswith('/console'):
                try:
                    await page.click('//*[@id="app"]/div[2]/div/div[3]/div[4]/section/div/div[1]/div[3]/div/div/div[2]/a', timeout=10000)
                except Exception:
                    pass

            print("🔍 正在等待控制台面板加载...")
            try:
                await page.wait_for_selector('text=Стоп', timeout=25000)
            except Exception as e:
                print("❌ 页面加载超时，未看到控制台按钮，已截图...")
                await page.screenshot(path="error_page_load.png")
                raise e

            # 检查运行状态
            await asyncio.sleep(2)
            page_text = (await page.locator('body').inner_text()).lower()

            if any(k in page_text for k in ["включён", "включен", "online", "running"]):
                print("🎉 服务器当前状态：运行中 (Online)")
                send_tg_message("👤 Rustix 操作通知\n状态: *Online*\n操作: 服务器当前正常运行，无需重启。")
            else:
                print("⚠️ 当前状态非运行中，正在点击 🔄 Рестарт 按钮...")
                await page.locator('text=Рестарт').first.click()
                
                confirm_btn = "//button[contains(text(), '确认') or contains(text(), 'Yes') or contains(text(), 'Да')]"
                if await page.query_selector(confirm_btn):
                    await page.click(confirm_btn)
                    print("✅ 已点击弹窗确认")

                print("⏳ 等待 2 分钟重启缓冲...")
                await asyncio.sleep(120)

                page_text_new = (await page.locator('body').inner_text()).lower()
                if any(k in page_text_new for k in ["включён", "включен", "online", "running"]):
                    send_tg_message("👤 Rustix 操作通知\n服务器重启成功 ✅\n状态: *Online*")
                else:
                    send_tg_message("👤 Rustix 操作通知\n服务器重启后状态异常 ⚠️\n请手动登录查看。")

        except Exception as e:
            print(f"❌ 运行过程报错: {e}")
            await page.screenshot(path="error_execution.png")
            raise e
        finally:
            await browser.close()

async def main():
    if not COOKIES_OR_ACCOUNTS:
        err = "错误: 未找到 COOKIES_JSON 或 ACCOUNTS_JSON 环境变量！"
        print(err)
        send_tg_message(f"❌ 运行中断: {err}")
        sys.exit(1)

    try:
        raw_data = json.loads(COOKIES_OR_ACCOUNTS)
        await process_with_playwright(raw_data)
        send_tg_message("🎉 Rustix 自动化重启任务执行完毕。")
    except Exception as e:
        err_msg = f"💥 Rustix 运行失败:\n`{str(e)}`"
        print(err_msg)
        send_tg_message(err_msg)

if __name__ == "__main__":
    asyncio.run(main())
