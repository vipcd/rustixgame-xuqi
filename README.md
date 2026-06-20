# Rustix Auto-Restart Bot

这是一个基于 **Playwright** 开发的自动化脚本，用于定期监控并重启 [rustix.me](https://my.rustix.me/) 平台上的服务器。该脚本支持多账户管理，并集成 Telegram 实时通知，完美适配 GitHub Actions 定时任务。

## 🚀 功能特性

- **多账户自动化**：支持一次性处理多个账号的服务器重启任务。
- **智能监控**：自动检测服务器状态，只有非 `Online` 状态时才执行重启，避免资源浪费。
- **实时通知**：通过 Telegram Bot 实时推送重启结果、错误报告。
- **云端运行**：通过 GitHub Actions 实现 24/7 全自动运行，无需本地挂机。
- **安全可靠**：利用 GitHub Secrets 存储凭据，开源无泄露风险。

## ⚙️ 如何部署

### 1. 准备工作
- 确保你拥有一个 Telegram Bot Token 和你的 Chat ID。
- 将脚本部署到你的 GitHub 仓库中。
### 2. fork 本仓库
### 4. 配置 GitHub Secrets
在你的仓库页面，进入 **Settings -> Secrets and variables -> Actions**，添加以下三个变量：

| Secret 名称 | 说明 | 示例值 |
| :--- | :--- | :--- |
| `TG_TOKEN` | 你的 Telegram Bot Token | `xxx` |
| `TG_CHAT_ID` | 你的 Telegram 用户 ID | `xxxxx` |
| `ACCOUNTS_JSON` | 账号密码列表 (JSON 格式) | `[{"user":"A@mail.com","pwd":"123"},{"user":"B@mail.com","pwd":"456"}]` |

## ！！ 注意  这里的账户是你的登录邮箱，密码是面板密码不是登录账号的密码。
### 面板密码在 https://rustix.me/me/settings 中重置，重置后面板密码会发到你的邮箱。
![reset](https://github.com/zhisibi/rustixreautostart/blob/main/passwdreset.jpg)
