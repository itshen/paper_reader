# Time & Calculator MCP

一个基于 MCP (Model Context Protocol) 的时间查询和基础计算服务，带有 Web 管理界面和完整的认证机制。

## 功能

### 🕐 时间工具

| 工具 | 功能 |
|------|------|
| `get_current_time` | 获取当前时间（支持多时区） |
| `convert_timezone` | 时区转换 |
| `date_calculate` | 日期计算（加减天/周/月） |
| `date_diff` | 计算日期差值 |
| `list_timezones` | 列出可用时区 |

### 🔢 计算工具

| 工具 | 功能 |
|------|------|
| `calculate` | 数学表达式计算 |
| `percentage` | 百分比计算 |
| `unit_convert` | 单位换算 |
| `random_number` | 生成随机数 |

### 🔐 认证功能

- 管理员登录（用户名/密码）
- Session 会话管理
- API Token 管理（供 MCP 客户端使用）
- 密码修改

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行

```bash
python3.11 server.py
```

### 3. 访问

- **Web 界面**: http://localhost:8765
- **管理后台**: http://localhost:8765/admin
- **MCP 端点**: http://localhost:8765/mcp

### 4. 默认账号

首次启动时，系统会创建默认管理员账号：

- 用户名：`admin`
- 密码：`admin123`（或查看控制台输出的随机密码）

**请登录后立即在管理页面修改密码！**

## 项目结构

```
MCP_Template/
├── server.py           # 服务器入口（Web + MCP）
├── tools.py            # 工具实现
├── auth.py             # 认证模块
├── models.py           # 数据模型
├── config.yaml         # 配置文件
├── requirements.txt    # 依赖列表
├── README.md           # 说明文档
├── templates/          # HTML 模板
│   ├── index.html      # 工具测试页面
│   ├── login.html      # 登录页面
│   └── admin.html      # 管理页面
└── static/             # 静态资源
    ├── css/
    │   └── style.css
    └── js/
        └── main.js
```

## 配置说明

### config.yaml

```yaml
# 服务器配置
server:
  name: "Time & Calculator MCP"
  port: 8765

# 认证配置
auth:
  default_password: "admin123"    # 默认密码
  salt: "your_salt_here"          # 密码加盐

# 存储配置
storage:
  data_dir: "./data"
```

## MCP 客户端配置

### 1. 创建 API Token

1. 访问管理页面：http://localhost:8765/admin
2. 在「API Token 管理」中创建新 Token
3. 复制生成的 Token

### 2. 配置 Cursor / Claude Desktop

```json
{
  "mcpServers": {
    "time-calc": {
      "url": "http://localhost:8765/mcp",
      "headers": {
        "Authorization": "Bearer mcp_xxxxxxxx..."
      }
    }
  }
}
```

## 使用示例

### 时间查询

```
get_current_time()                    → 北京时间（默认）
get_current_time("纽约")               → 纽约时间
convert_timezone("14:30", "北京", "纽约") → 时区转换
date_calculate("today", days=7)        → 7 天后
date_diff("today", "2025-12-31")       → 距离年底多少天
```

### 计算

```
calculate("sqrt(16) + 2^3")            → 12
percentage(100, 20, "increase")        → 120
unit_convert(25, "℃", "℉")             → 77°F
random_number(1, 100, 5)               → 5 个随机数
```

## 支持的时区

| 时区 | 别名 | UTC 偏移 |
|------|------|---------|
| Asia/Shanghai | 北京、上海、中国 | UTC+8 |
| Asia/Tokyo | 东京、日本 | UTC+9 |
| America/New_York | 纽约 | UTC-5 |
| America/Los_Angeles | 洛杉矶 | UTC-8 |
| Europe/London | 伦敦 | UTC+0 |
| Europe/Paris | 巴黎 | UTC+1 |

## 支持的单位

- **长度**: km, m, cm, mm, mi, yd, ft, in, 千米, 米, 厘米, 毫米
- **重量**: kg, g, mg, lb, oz, 公斤, 斤, 两, 克
- **温度**: ℃, ℉, K, 摄氏度, 华氏度, 开尔文
- **数据**: B, KB, MB, GB, TB

## License

MIT License

Copyright (c) 2025 Miyang Tech (Zhuhai Hengqin) Co., Ltd.
