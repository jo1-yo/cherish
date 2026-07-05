# Cherish 上线部署手册

架构:
- **前端** — GitHub Pages(已上线:https://cherishthestudio.com)
- **后端** — Render 免费 Web Service(`backend/server.py`,零依赖)
- **数据** — 用户表 + 订单存私有仓库 `jo1-yo/cherish-data`(已建好,空仓库即可);admin 发布的内容(`site-content.json` + 上传的图)由后端直接提交到本仓库,GitHub Pages 约 1 分钟后全站生效
- **邮件** — Resend 发验证码

## 一、创建 GitHub 细粒度 Token(后端写数据用)

1. 打开 https://github.com/settings/personal-access-tokens/new
2. Token name: `cherish-backend` · Expiration: 1 年
3. Repository access → **Only select repositories** → 勾选 `jo1-yo/cherish` 和 `jo1-yo/cherish-data`(私有数据仓库已创建)
4. Permissions → Repository permissions → **Contents: Read and write**
5. Generate,**复制 token**(只显示一次)

## 二、部署到 Render

1. https://render.com → **Sign in with GitHub**(用 jo1-yo 登录)
2. **New +** → **Blueprint** → 选 `jo1-yo/cherish` 仓库(它会自动读到 render.yaml)
3. 填环境变量:
   - `ADMIN_KEY` — 你自己定一个后台密码(别再用 cherish)
   - `GITHUB_TOKEN` — 第一步的 token
   - `RESEND_API_KEY` — 第三步拿到后再填也行(没填时验证码打在 Render Logs 里)
4. **Apply** → 等部署完成 → 打开 `https://cherishthestudio-backend.onrender.com/api/health` 应返回 ok
   - ⚠️ 如果服务名被占用,Render 会给一个别的 URL。两种修法任选:告诉 Claude 改一行前端配置(js/app.js 里的 API_BASE);或临时在浏览器 console 执行 `localStorage.setItem('cherish_api_base','https://新地址')`

## 三、接 Resend(真实邮件)

1. https://resend.com 注册 → **API Keys** → 创建,填到 Render 环境变量 `RESEND_API_KEY`
2. 没验证域名前,只能发到你自己的注册邮箱(测试够用)
3. 正式对外:**Domains** → Add `cherishthestudio.com` → 把页面给出的几条 DNS 记录(MX + 两条 TXT)加到 Squarespace 的 DNS 设置里 → 等验证通过
4. 确认 Render 环境变量 `EMAIL_FROM` 是 `Cherish <hello@cherishthestudio.com>` → Manual Deploy 重启

## 四、验证

- 手机(不连本地)打开 cherishthestudio.com → Sign Up → 收邮件 → 注册成功
- admin.html 用新 ADMIN_KEY 进 → Registered Users 里看到新用户
- 加一件商品下单 → admin 的 Orders 表里出现这单(含客户邮箱、发票明细)
- Homepage 标签改一个词 → Save → 约 1 分钟后任何设备刷新首页都能看到

## 免费额度须知

- Render 免费服务闲置 15 分钟会休眠,下一个请求要等 ~30 秒唤醒(注册页第一下慢是正常的)
- Resend 免费 100 封/天
