# 唐山停电分析后端系统

国网唐山供电公司停电事件统计分析后端，基于 Flask + 原生 SQL 构建，提供区域维度的停电用户统计、行业分布、敏感用户分析等 RESTful API 接口，并内置数据采集管道用于从上游接口同步数据。

## 目录

- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [环境变量配置](#环境变量配置)
- [API 接口文档](#api-接口文档)
- [数据采集管道](#数据采集管道)
- [数据库设计](#数据库设计)
- [Token 认证策略](#token-认证策略)
- [部署](#部署)

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | Flask ≥ 3.0 | 工厂模式创建应用 |
| 数据库 | MySQL | PyMySQL 直连，无 ORM |
| 连接池 | DBUtils ≥ 3.1 | PooledDB 管理连接 |
| 加密 | gmssl ≥ 3.2.2 | 国密 SM3 哈希 |
| 缓存 | Redis ≥ 5.0 | Token 缓存 |
| HTTP | requests ≥ 2.31 | 上游数据接口调用 |
| 生产服务器 | gunicorn ≥ 21.2 | WSGI 部署 |

## 项目结构

```
tangshan_backend/
├── run.py                          # 应用入口
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── .flaskenv                       # Flask CLI 配置
├── docs/
│   └── api_county.md               # API 接口详细文档
├── migrations/                     # 数据库迁移（预留）
├── app/
│   ├── __init__.py                 # Flask 应用工厂 (create_app)
│   ├── config.py                   # 多环境配置类
│   ├── extensions.py               # 扩展（当前为空）
│   ├── api/
│   │   ├── __init__.py             # API 蓝图注册 + /health 端点
│   │   └── county.py               # 区县相关路由（4 个接口）
│   ├── common/
│   │   └── response.py             # 统一 JSON 响应封装
│   └── repositories/
│       └── county_repository.py    # 区县数据访问层（原生 SQL）
└── utils/
    └── trade_city_get/
        ├── __init__.py             # 导出公共模块
        ├── db.py                   # 数据库建表 DDL + Upsert 操作
        ├── token_client.py         # 多策略 Token 获取
        ├── sm3_utils.py            # 国密 SM3 哈希工具
        ├── industry_fetcher.py     # 行业数据采集
        ├── region_fetcher.py       # 行政区域数据采集
        ├── outage_fetcher.py       # 停电事件数据采集
        └── seed_equipment.py       # 设备与设备-馈线关系数据采集
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd tangshan_backend

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制环境变量模板并填写实际值
cp .env.example .env
```

最小配置只需填写 MySQL 连接信息：

```ini
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=tangshan_backend
```

### 3. 初始化数据库

通过数据采集脚本自动建表并导入数据（详见 [数据采集管道](#数据采集管道)）。

### 4. 启动服务

```bash
# 开发环境（Flask 内置服务器）
python run.py

# 或使用 Flask CLI
flask run
```

服务默认运行在 `http://127.0.0.1:5000`。

验证服务是否正常：

```bash
curl http://127.0.0.1:5000/api/health
# 返回: {"code":0,"success":true,"message":"ok","data":{"status":"ok"}}
```

## 环境变量配置

### 基础配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SECRET_KEY` | `dev-secret-key` | Flask 密钥，生产环境必须修改 |
| `MYSQL_HOST` | `127.0.0.1` | MySQL 主机地址 |
| `MYSQL_PORT` | `3306` | MySQL 端口 |
| `MYSQL_USER` | `root` | MySQL 用户名 |
| `MYSQL_PASSWORD` | 空 | MySQL 密码 |
| `MYSQL_DATABASE` | `tangshan_backend` | 数据库名 |
| `MYSQL_USER_SCORE_TABLE` | `outage_user_full` | 用户停电评分主表名 |

### 上游 API 配置

| 变量 | 说明 |
|------|------|
| `API_USER_DETAIL_URL` | 停电用户明细接口地址 |
| `API_OUTAGE_LIST_URL` | 停电事件列表接口地址 |
| `API_OUTAGE_DETAIL_URL` | 停电事件详情接口地址 |
| `API_START_DATE` | 数据采集起始日期 |
| `API_END_DATE` | 数据采集结束日期 |
| `API_PER_PAGE` | 每页数据量（默认 300） |
| `API_MAX_PAGES` | 最大采集页数（默认 50） |

### Token 认证配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TOKEN_STRATEGY` | `none` | Token 策略，可选: `none` / `esb` / `oauth2` / `redis` / `static` |
| `TOKEN_HEADER_NAME` | `x-token` | Token 请求头名称 |
| `TOKEN_HEADER_PREFIX` | 空 | Token 前缀（如 `Bearer`） |

详细策略配置请参考 `.env.example`。

## API 接口文档

除健康检查外，业务接口均为 **POST** 方法，请求和响应均为 **JSON** 格式，基础路径为 `/api`。

### 统一响应格式

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {},
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/county/list` | 获取区县列表 |
| POST | `/api/county/stats` | 区县用户统计（重点/敏感/普通用户数） |
| POST | `/api/county/detail-stats` | 区县详细统计（行业分布、停电性质占比） |
| POST | `/api/county/user-list` | 用户列表（分页、搜索、筛选） |
| POST | `/api/county/user-outage-stats` | 用户停电次数统计（分页、搜索、筛选） |
| POST | `/api/county/trend` | 区县时间趋势 |
| POST | `/api/county/outage-freq` | 停电次数分布 |
| POST | `/api/county/equipment-stats` | 设备影响统计 |
| POST | `/api/county/equipment-list` | 设备影响列表 |
| POST | `/api/county/equipment-page` | 设备影响分页查询 |
| POST | `/api/county/equipment-detail` | 设备详情 |
| POST | `/api/county/user-detail` | 用户停电详情 |
| POST | `/api/county/user-outage-detail` | 用户停电时间线 |

详细的请求参数和响应字段说明请参阅 [docs/api_county.md](docs/api_county.md)。

## 数据采集管道

`utils/trade_city_get/` 目录下包含四个独立的采集脚本，用于从上游 API 拉取数据并写入 MySQL。

### 行业数据采集

```bash
python -m utils.trade_city_get.industry_fetcher --start 2025-01-01 --end 2026-04-30
```

同步行业/贸易分类数据到 `trade_industry` 表。

### 行政区域数据采集

```bash
python -m utils.trade_city_get.region_fetcher --start 2025-01-01 --end 2026-04-30
```

同步城市 → 区县 → 维护组的层级数据到 `city`、`county`、`maint_group` 表。

### 停电事件数据采集

```bash
python -m utils.trade_city_get.outage_fetcher --start 2025-01-01 --end 2026-04-30
```

同步变电站、馈线、设备及设备-馈线关系等停电维度数据。脚本会确保相关维度表可用；API 主查询表 `outage_user_full` 需要由用户停电明细 ETL 写入后，业务接口才会返回真实统计数据。

### 设备数据采集

```bash
python -m utils.trade_city_get.seed_equipment --pages 10 --months 6
```

同步设备和设备-馈线关系数据到 `equipment`、`equipment_feeder` 表。

### 通用参数

| 参数 | 说明 |
|------|------|
| `--start` | 起始日期（YYYY-MM-DD），默认取 `API_START_DATE` 环境变量 |
| `--end` | 结束日期（YYYY-MM-DD），默认取 `API_END_DATE` 环境变量 |
| `--pages` | 最大采集页数（仅 `seed_equipment`） |
| `--months` | 回溯月数（仅 `seed_equipment`） |

## 数据库设计

项目使用原生 SQL，所有建表语句定义在 `utils/trade_city_get/db.py` 中。

### 维度表

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| `city` | 城市信息 | `city_id`, `city_name` |
| `county` | 区县信息 | `county_id`, `county_name`, `city_id` |
| `maint_group` | 维护班组 | `maint_group_id`, `maint_group_name`, `county_id` |
| `trade_industry` | 行业/贸易分类 | `trade_type`, `trade_name`, `category_code`, `user_count` |
| `substation` | 变电站 | `subs_id`, `subs_name`, `city_id`, `county_id` |
| `feeder` | 馈线（供电线路） | `feeder_id`, `feeder_name`, `subs_id`, `county_id` |
| `equipment` | 设备 | `equipment_id`, `equipment_name`, `equipment_type`, `county_id` |
| `equipment_feeder` | 设备-馈线映射 | `equipment_id`, `feeder_id`（联合唯一键） |

### 事实表

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| `outage_user_full` | 停电用户明细（主查询表） | `cons_no`, `cons_name`, `outage_number`, `rdt_city_id`, `rdt_county_id`, `trade_type`, `outage_nature`, `is_key_user`, `is_sensitive_user`, `begin_time`, `end_time`, `snapshot_date` |

表名可通过环境变量 `MYSQL_USER_SCORE_TABLE` 自定义。

### 数据流向

```
上游 API
  │
  ├── industry_fetcher  ──→ trade_industry
  ├── region_fetcher    ──→ city / county / maint_group
  ├── outage_fetcher    ──→ substation / feeder / equipment / equipment_feeder
  └── seed_equipment    ──→ equipment / equipment_feeder
                              │
                              ▼
                     Flask API (county_repository)
                              │
                              ▼
                        前端展示
```

## Token 认证策略

系统支持五种 Token 获取策略，通过 `TOKEN_STRATEGY` 环境变量切换：

| 策略 | 说明 |
|------|------|
| `none` | 不携带 Token（默认） |
| `esb` | 企业服务总线认证，使用 SM3 国密签名 |
| `oauth2` | OAuth2 客户端凭证模式 |
| `redis` | 直接从 Redis 读取 Token |
| `static` | 使用静态 Token |

Token 优先从 Redis 缓存读取，缓存未命中时通过对应策略获取新 Token 并写入缓存。

## 部署

### 生产环境启动

```bash
# 设置环境变量
export APP_ENV=production

# 使用 gunicorn 启动
gunicorn "app:create_app()" -b 0.0.0.0:8000 -w 4
```

### 配置检查

生产环境启动时会自动检查：

- `SECRET_KEY` 不能为默认值 `dev-secret-key`
- 必须设置 `MYSQL_HOST`、`MYSQL_USER`、`MYSQL_DATABASE`

### 注意事项

- `.env` 文件已被 `.gitignore` 排除，切勿将包含真实密码的 `.env` 文件提交到版本库
- 生产环境建议使用 HTTPS 反向代理（如 Nginx）
- 数据采集脚本建议通过定时任务（crontab / celery beat）定期执行
