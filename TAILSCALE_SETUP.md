# Tailscale 上手指南

> 目标：以后在学校/外出时，手机或笔记本能安全访问家里/宿舍 Mac 上的 Trade Review，子网其他人完全扫不到端口。

---

## 一句话解释

Tailscale 在你的设备之间建一个**加密私有网络**（基于 WireGuard 协议，速度快）。

- 学校同子网的其他同学：**根本看不见你服务的端口**
- 你自己的 Mac / iPhone / iPad：像在同一个局域网里一样互通
- 数据包**点对点加密**传输，不经过 Tailscale 的服务器
- **个人免费**，最多 100 台设备 / 3 个用户

---

## 📦 第一步：Mac 安装（5 分钟）

### 方式 A：App Store（推荐，最简单）

1. 打开 **App Store**，搜 "Tailscale"
2. 点"获取"安装
3. 应用启动后点 **Log in**
4. 用 **Google / Apple / Microsoft / GitHub** 账号任选一个登录（推荐 Apple，后面手机直接 iCloud 继承）
5. 看到菜单栏出现一个 Tailscale 小图标，**实心** = 已连接

### 方式 B：Homebrew（如果你更喜欢命令行）

```bash
brew install --cask tailscale
open -a Tailscale
# 然后在应用里登录
```

---

## ✅ 第二步：验证装好了

打开终端：

```bash
tailscale status
```

看到类似：

```
100.64.1.5    your-mac        you@example.com  macOS   active; direct
```

**`100.64.1.5`** 就是你 Mac 的 Tailscale 私网 IP（每台设备不同）。记住这个 IP 范围 —— 以 `100.` 开头就是 Tailscale 专用私网。

再试一条：

```bash
tailscale ip -4
# 应该输出：100.64.1.5（或类似的 100.x.x.x）
```

如果**任何一条命令报 "tailscale: command not found"**：

```bash
# App 版的 CLI 没放在 PATH，手动加：
echo 'export PATH="/Applications/Tailscale.app/Contents/MacOS:$PATH"' >> ~/.zshrc
source ~/.zshrc
tailscale ip -4
```

---

## 🚀 第三步：用 Tailscale 模式启动 Trade Review

```bash
cd /path/to/trade_review
./start.sh --tailscale
```

启动脚本会自动检测 Tailscale IP 并绑定到那里。你会看到类似：

```
✅ Tailscale 已连接，本机 Tailscale IP：100.64.1.5
   服务将只在 Tailscale 虚拟网卡监听，子网其他人无法访问

主 URL：  http://100.64.1.5:8090/#token=<24-char-random>
```

**在 Mac 浏览器打开这条 URL 一次**（第一次 Token 就存进去了）。

---

## 🛡 第四步：快速验证安全性（可选但建议）

在启动 Tailscale 模式的状态下：

```bash
# 1. 学校 Wi-Fi IP 应该访问不到（说明服务没暴露给同子网）
LAN=$(ipconfig getifaddr en0)
curl -s --max-time 3 "http://$LAN:8090/" -o /dev/null -w "HTTP %{http_code}  exit=%{exitcode}\n"
# 期望：exit=7（拒绝）

# 2. Tailscale IP 应该能通
TS=$(tailscale ip -4 | head -1)
curl -s "http://$TS:8090/api/health"
# 期望：{"status":"ok"}
```

第一条连接被拒绝 = 学校 Wi-Fi 同子网任何人都扫不到你的服务。

---

## 📱 第五步：以后手机要用时

等你真的想用手机再做这一步：

1. iPhone App Store 搜 **Tailscale**，安装
2. 打开 App，登录 **同一个账号**（这一步关键）
3. 允许安装 VPN 配置文件（iOS 会弹窗提示）
4. 看到"Connected"状态即可
5. Safari 打开 `http://100.64.1.5:8090/#token=...`（就是启动脚本打印的那条）
6. 一次输入 Token 后，之后直接打开 `http://100.64.1.5:8090` 即可
7. **添加到主屏幕**（Safari 分享 → 添加到主屏幕），以后像打开 App

### 重要：在学校时 iOS Tailscale 的开关

在 iPhone 上，Tailscale 图标是一个**全局 VPN 开关**：

- **打开**：能访问 Mac 上的 Trade Review，同时**所有**流量**不会**经过 Tailscale（Tailscale 默认只代理 `100.x.x.x` 的流量，其他网站正常走 4G/Wi-Fi）
- **关闭**：访问不到 Mac，但其他网络正常

所以**日常保持开着**没问题，不影响你用微信、刷 B 站。

---

## ❓ 常见问题

**Q: Tailscale 公司会看到我的数据吗？**
A: 不会。它只是帮两台设备互相找到对方（NAT 穿透），真正的数据包在你的两台设备间 **WireGuard 端到端加密传输**。即使 Tailscale 服务器全部关闭，已建立的连接也能继续工作。

**Q: 免费版够用吗？**
A: 个人用**永远免费**。限制是 100 台设备 + 3 个用户，对单人来说用一辈子都用不完。

**Q: 会占用 CPU / 电池吗？**
A: 基本感知不到。WireGuard 是内核级实现，Mac 上除非传大文件，否则 CPU 占用几乎为 0。iPhone 上 Tailscale 一直开，一天额外耗电 < 2%。

**Q: 学校 Wi-Fi 封了 VPN 怎么办？**
A: Tailscale 默认端口 UDP 41641，大多数校园网不会封。如果真封了，它会自动回退到 HTTPS over port 443 中继，几乎任何网络都能穿透。

**Q: Mac 重启后 Tailscale 还在吗？**
A: 在。装好后默认开机自启，你不用管。

**Q: 想关掉 Tailscale？**
A: 菜单栏点 Tailscale 图标 → Disconnect。想彻底删除：App 版在 App 里退出登录，brew 版 `brew uninstall tailscale`。

---

## 🎯 TL;DR

```bash
# 1. 装 Tailscale（一次）
brew install --cask tailscale
open -a Tailscale  # 在 App 里登录

# 2. 以后每次启动
cd /path/to/trade_review
./start.sh --tailscale

# 3. 浏览器打开启动脚本打印的 URL
```

完成。
