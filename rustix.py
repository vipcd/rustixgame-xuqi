import asyncio
import requests
import os
import json
import sys
from playwright.async_api import async_playwright

# --- 从环境变量读取敏感信息 ---
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
# 预期的格式: [{"user": "...", "pwd": "..."}, {"user": "...", "pwd": "..."}]
ACCOUNTS_JSON = os.environ.get("ACCOUNTS_JSON")

LOGIN_URL = "https://my.rustix.me/auth/login"

# ============================================================
# ⚠️ 请注意：因为网站更新，下面这三个 XPath 大概率变了，需要你重新获取并替换！
# ============================================================
XPATH_MANAGE_LINK = '//*[@id="app"]/div[2]/div/div[3]/div[4]/section/div/div[1]/div[3]/div/div/div[2]/a'
XPATH_STATUS_TEXT = '//*[@id="app"]/div[2]/div/div[2]/div[2]/div[3]/div/div/div[1]/div[1]/span'
XPATH_RESTART_BTN = '//*[@id="app"]/div[2]/div/div[2]/div[2]/div[3]/div/div/div[2]/button[2]'
# ============================================================

def send_tg_message(text):
    """发送带 Markdown 格式的 Telegram 消息"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("警告: TG_TOKEN 或 TG_CHAT_ID 未设置，跳过消息发送。")
        return
        
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    formatted_text = f"*✅ rustix.me服务器自动重启通知*\n\n{text}"
    payload = {"chat_id": TG_CHAT_ID, "text": formatted_text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"发送 TG 消息失败: {e}")

async def process_account(account):
    """处理单个账户的逻辑"""
    async with async_playwright() as p:
        # 在 GitHub Actions 中建议开启 headless=True
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"\n>>> 开始处理账户: {account['user']}")
        await page.goto(LOGIN_URL)

        # 1. 登录
        await page.fill('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[1]/div/input', account['user'])
        await page.fill('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[2]/div[2]/div/div/input', account['pwd'])
        await page.click('//*[@id="app"]/div[2]/div/div/div[2]/form/div/div[4]/button')

        # 2. 进入管理页
        try:
            await page.wait_for_selector('section', timeout=30000)
            await page.click(XPATH_MANAGE_LINK)
            print("点击了进入管理页面链接，等待页面加载...")
        except Exception as e:
            print(f"❌ 无法点击进入管理页链接: {e}")
            await page.screenshot(path="error_enter_manage.png")
            raise e

        # 3. 智能等待状态元素出现 (代替原本死等30秒的旧逻辑)
        print("🔍 正在定位服务器状态元素...")
        try:
            # 缩短初始强制等待，直接依赖 wait_for_selector
            await asyncio.sleep(5) 
            await page.wait_for_selector(XPATH_STATUS_TEXT, timeout=25000)
            status_text = await page.inner_text(XPATH_STATUS_TEXT)
        except Exception as e:
            print(f"❌ 找不到服务器状态元素，可能网站结构已改变！正在保存错误截图...")
            await page.screenshot(path="error_status_not_found.png")
            raise e
        
        # 4. 获取状态并判断
        if status_text.strip() == "Online":
            send_tg_message(f"👤 账户: `{account['user']}`\n状态: *Online*\n操作: 无需重启。")
        else:
            print(f"当前状态为: {status_text.strip()}，不是 Online，执行重启...")
            try:
                await page.click(XPATH_RESTART_BTN)
            except Exception as e:
                print(f"❌ 点击重启按钮失败: {e}")
                await page.screenshot(path="error_click_restart.png")
                raise e
            
            # 确认弹窗
            confirm_btn = "//button[contains(text(), '确认') or contains(text(), 'Yes')]"
            if await page.query_selector(confirm_btn):
                await page.click(confirm_btn)
            
            # 等待2分钟检查重启结果
            await asyncio.sleep(120)
            status_text_new = await page.inner_text(XPATH_STATUS_TEXT)
            if status_text_new.strip() == "Online":
                send_tg_message(f"👤 账户: `{account['user']}`\n服务器重启成功 ✅\n状态: *Online*")
            else:
                send_tg_message(f"👤 账户: `{account['user']}`\n服务器重启后状态异常 ⚠️\n当前状态: {status_text_new.strip()}")

        print(f"账户 {account['user']} 操作完成。")
        await browser.close()

async def main():
    if not ACCOUNTS_JSON:
        print("错误: 未找到 ACCOUNTS_JSON 环境变量，请检查 GitHub Secrets 配置。")
        sys.exit(1)
        
    try:
        accounts = json.loads(ACCOUNTS_JSON)
        for account in accounts:
            await process_account(account)
        send_tg_message("所有账户操作成功。 🎉")
    except Exception as e:
        print(f"脚本运行错误: {str(e)}")
        send_tg_message(f"⚠️ 脚本运行出现错误，请检查 GitHub Actions 日志。\n错误详情: `{str(e)}`")

if __name__ == "__main__":
    asyncio.run(main())
