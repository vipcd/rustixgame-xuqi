import asyncio
import requests
import os
import json
import sys
from playwright.async_api import async_playwright

# --- 从环境变量读取敏感信息 ---
TG_TOKEN = os.environ.get("TG_BOT_TOKEN") or os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
# 自动读取 COOKIES_JSON 或 ACCOUNTS_JSON
ACCOUNTS_JSON = os.environ.get("COOKIES_JSON") or os.environ.get("ACCOUNTS_JSON")
PROXY_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:10809")

LOGIN_URL = "https://my.rustix.me/auth/login"

def send_tg_message(text):
    """发送带 Markdown 格式的 Telegram 消息"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("警告: TG_TOKEN 或 TG_CHAT_ID 未设置，跳过消息发送。")
        return
        
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    formatted_text = f"*✅ rustix.me服务器自动重启通知*\n\n{text}"
    payload = {"chat_id": TG_CHAT_ID, "text": formatted_text, "parse_mode": "Markdown"}
    
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
    try:
        resp = requests.post(url, json=payload, proxies=proxies, timeout=10)
        if resp.status_code != 200 and proxies:
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"发送 TG 消息失败: {e}")

async def process_account(account):
    """处理单个账户的逻辑"""
    user_identifier = account.get('user') or account.get('username') or account.get('user_name', '未知账号')
    password = account.get('pwd') or account.get('password', '')

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
            print(f"🌐 启用代理路由: {PROXY_URL}")

        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="zh-CN"
        )
        page = await context.new_page()

        print(f"\n>>> 开始处理账户: {user_identifier}")
        
        try:
            await page.goto(LOGIN_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            page_content = await page.content()
            if "Access denied" in page_content:
                raise PermissionError("Access denied: 节点 IP 已被站点拦截，请尝试更换 NODE_LINK 订阅节点。")

            # 1. 登录
            await page.wait_for_selector('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[1]/div/input', timeout=20000)
            await page.fill('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[1]/div/input', user_identifier)
            await page.fill('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[2]/div[2]/div/div/input', password)
            await page.click('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[4]/button')

            # 2. 进入管理页
            await page.wait_for_selector('section', timeout=30000)
            await page.click('//*[@id="app"]/div[2]/div/div[3]/div[4]/section/div/div[1]/div[3]/div/div/div[2]/a')
            print("已进入管理页面，等待加载状态...")

            # 3. 智能等待控制台
            print("🔍 正在等待控制台面板加载...")
            try:
                await page.wait_for_selector('text=Стоп', timeout=25000)
            except Exception as e:
                print("❌ 页面加载超时，没看到控制台按钮。正在保存错误截图...")
                await page.screenshot(path="error_page_load.png")
                raise e
            
            # 4. 检查服务器运行状态
            await asyncio.sleep(2)
            page_text = await page.locator('body').inner_text()
            page_text_lower = page_text.lower()
            
            if "включён" in page_text_lower or "включен" in page_text_lower or "online" in page_text_lower or "running" in page_text_lower:
                print("🎉 服务器当前状态：运行中 (Online/Включён)")
                send_tg_message(f"👤 账户: `{user_identifier}`\n状态: *Online*\n操作: 无需重启。")
            else:
                print("⚠️ 当前状态不是运行中，准备点击 🔄 Рестарт 按钮重启...")
                try:
                    await page.locator('text=Рестарт').first.click()
                    print("✅ 已成功点击 Рестарт 按钮")
                except Exception as e:
                    print(f"❌ 点击重启按钮失败: {e}")
                    await page.screenshot(path="error_click_restart.png")
                    raise e
                
                # 确认弹窗
                confirm_btn = "//button[contains(text(), '确认') or contains(text(), 'Yes') or contains(text(), 'Да')]"
                if await page.query_selector(confirm_btn):
                    await page.click(confirm_btn)
                    print("✅ 已点击弹窗确认")
                
                print("⏳ 等待 2 分钟让服务器缓一缓...")
                await asyncio.sleep(120)
                
                page_text_new = await page.locator('body').inner_text()
                page_text_new_lower = page_text_new.lower()
                if "включён" in page_text_new_lower or "включен" in page_text_new_lower or "online" in page_text_new_lower or "running" in page_text_new_lower:
                    send_tg_message(f"👤 账户: `{user_identifier}`\n服务器重启成功 ✅\n状态: *Online*")
                else:
                    send_tg_message(f"👤 账户: `{user_identifier}`\n服务器重启后状态异常 ⚠️\n请手动登录检查。")

            print(f"账户 {user_identifier} 操作完成。")

        except Exception as e:
            print(f"处理账户 {user_identifier} 报错: {e}")
            raise e
        finally:
            await browser.close()

async def main():
    accounts = []
    if ACCOUNTS_JSON:
        try:
            accounts = json.loads(ACCOUNTS_JSON)
        except Exception as e:
            print(f"⚠️ 解析 JSON 配置失败: {e}")

    if not accounts:
        user = os.environ.get("RUSTIX_USERNAME")
        pwd = os.environ.get("RUSTIX_PASSWORD")
        if user and pwd:
            accounts = [{"user": user, "pwd": pwd}]
        else:
            print("错误: 未找到有效账号数据，请检查 Secrets 配置。")
            sys.exit(1)
            
    try:
        for account in accounts:
            await process_account(account)
        send_tg_message("所有账户操作完毕。 🎉")
    except Exception as e:
        print(f"脚本运行错误: {str(e)}")
        send_tg_message(f"⚠️ 脚本运行出现错误，请检查 GitHub Actions 日志。\n错误详情: `{str(e)}`")

if __name__ == "__main__":
    asyncio.run(main())
