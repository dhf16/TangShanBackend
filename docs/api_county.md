# 区县统计模块 API 文档

Base URL: `http://{host}:5000/api`

所有接口统一使用 `POST` + `JSON` 请求体，`Content-Type: application/json`。

---

## 统一响应格式

### 成功响应

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": { ... },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 失败响应

```json
{
  "code": 400,
  "success": false,
  "message": "错误描述",
  "data": null,
  "errors": [
    { "message": "错误描述", "code": 400 }
  ],
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 常见错误码

| HTTP 状态码 | code | 含义 |
|------------|------|------|
| 400 | 400 | 请求参数错误（缺少必填字段、格式不对、值不合法） |
| 404 | 404 | 接口路径不存在 |
| 405 | 405 | 请求方法不允许（如用 GET 访问 POST 接口） |
| 500 | 500 | 服务器内部错误 |

---

## 1. 获取区县列表

查询系统中所有可用的区县，可按地市筛选。

```
POST /api/county/list
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cityId | string | 否 | 地市公司 ID，传入则只返回该地市下的区县 |

### 请求示例

```json
{}
```

或按城市筛选：

```json
{
  "cityId": "130200"
}
```

### 响应示例

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "list": [
      {
        "countyId": "130202",
        "countyName": "路北区",
        "cityId": "130200"
      },
      {
        "countyId": "130203",
        "countyName": "路南区",
        "cityId": "130200"
      }
    ]
  },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.list | array | 区县列表 |
| data.list[].countyId | string | 区县公司 ID |
| data.list[].countyName | string | 区县公司名称 |
| data.list[].cityId | string | 所属地市公司 ID |

---

## 2. 区县统计数据

查询区县级别的用户分类统计。有两种用法：
- **不传 countyId**：返回所有区县的汇总 + 各区县明细
- **传 countyId**：返回指定区县的统计数据

```
POST /api/county/stats
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| countyId | string | 否 | 区县 ID，不传则返回所有区县汇总 |
| snapshotDate | string | 否 | 数据快照日期，格式 `YYYY-MM-DD`，精确匹配某一天的数据 |
| snapshotStartDate | string | 否 | 快照日期范围起点，与 snapshotDate 互斥 |
| snapshotEndDate | string | 否 | 快照日期范围终点，与 snapshotDate 互斥 |

> snapshotDate 与 snapshotStartDate/snapshotEndDate 的关系：传了 snapshotDate 则忽略范围参数；不传 snapshotDate 才使用范围筛选。

### 请求示例

查询所有区县汇总：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

查询指定区县：

```json
{
  "beginTime": "2025-01-01",
  "endTime": "2026-04-30",
  "countyId": "130203"
}
```

### 响应示例（不传 countyId）

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "summary": {
      "totalUsers": 1500,
      "keyUsers": 200,
      "sensitiveUsers": 350,
      "normalUsers": 950
    },
    "list": [
      {
        "countyId": "130202",
        "countyName": "路北区",
        "totalUsers": 500,
        "keyUsers": 80,
        "sensitiveUsers": 100,
        "normalUsers": 320
      },
      {
        "countyId": "130203",
        "countyName": "路南区",
        "totalUsers": 400,
        "keyUsers": 60,
        "sensitiveUsers": 90,
        "normalUsers": 250
      }
    ]
  },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 响应示例（传 countyId）

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "totalUsers": 400,
    "keyUsers": 60,
    "sensitiveUsers": 90,
    "normalUsers": 250
  },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 响应字段说明

**不传 countyId 时：**

| 字段 | 类型 | 说明 |
|------|------|------|
| data.summary | object | 所有区县的汇总统计 |
| data.summary.totalUsers | int | 用户总数 |
| data.summary.keyUsers | int | 关键用户数 |
| data.summary.sensitiveUsers | int | 敏感用户数 |
| data.summary.normalUsers | int | 普通用户数 |
| data.list | array | 各区县统计明细，按 totalUsers 降序 |
| data.list[].countyId | string | 区县 ID |
| data.list[].countyName | string | 区县名称 |
| data.list[].totalUsers | int | 该区县用户总数 |
| data.list[].keyUsers | int | 该区县关键用户数 |
| data.list[].sensitiveUsers | int | 该区县敏感用户数 |
| data.list[].normalUsers | int | 该区县普通用户数 |

**传 countyId 时：**

| 字段 | 类型 | 说明 |
|------|------|------|
| data.totalUsers | int | 用户总数 |
| data.keyUsers | int | 关键用户数 |
| data.sensitiveUsers | int | 敏感用户数 |
| data.normalUsers | int | 普通用户数 |

---

## 3. 区县详细统计

查询指定区县（或全部区县）的详细统计信息，包括按行业分布和停电性质分布。

```
POST /api/county/detail-stats
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| countyId | string | 否 | 区县 ID，不传则统计全部区县 |
| snapshotDate | string | 否 | 数据快照日期 |
| snapshotStartDate | string | 否 | 快照日期范围起点 |
| snapshotEndDate | string | 否 | 快照日期范围终点 |

### 请求示例

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "countyId": "130203"
}
```

### 响应示例

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "summary": {
      "keyUsers": 60,
      "sensitiveUsers": 90,
      "total": 150
    },
    "keyUserByTrade": [
      {
        "tradeType": "01",
        "tradeName": "大工业",
        "userCount": 30
      },
      {
        "tradeType": "02",
        "tradeName": "一般工商业",
        "userCount": 20
      }
    ],
    "sensitiveUserByTrade": [
      {
        "tradeType": "03",
        "tradeName": "居民生活",
        "userCount": 50
      }
    ],
    "outageNatureDistribution": [
      {
        "outageNature": "1",
        "userCount": 80,
        "percentage": 53.3
      },
      {
        "outageNature": "2",
        "userCount": 50,
        "percentage": 33.3
      },
      {
        "outageNature": "3",
        "userCount": 20,
        "percentage": 13.4
      }
    ]
  },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.summary | object | 汇总 |
| data.summary.keyUsers | int | 关键用户总数 |
| data.summary.sensitiveUsers | int | 敏感用户总数 |
| data.summary.total | int | 关键 + 敏感用户合计 |
| data.keyUserByTrade | array | 关键用户按行业分布，按 userCount 降序 |
| data.keyUserByTrade[].tradeType | string | 行业编码 |
| data.keyUserByTrade[].tradeName | string | 行业名称 |
| data.keyUserByTrade[].userCount | int | 该行业用户数 |
| data.sensitiveUserByTrade | array | 敏感用户按行业分布，按 userCount 降序 |
| data.sensitiveUserByTrade[].tradeType | string | 行业编码 |
| data.sensitiveUserByTrade[].tradeName | string | 行业名称 |
| data.sensitiveUserByTrade[].userCount | int | 该行业用户数 |
| data.outageNatureDistribution | array | 关键+敏感用户按停电性质分布，按 userCount 降序 |
| data.outageNatureDistribution[].outageNature | string | 停电性质编码 |
| data.outageNatureDistribution[].userCount | int | 该性质用户数 |
| data.outageNatureDistribution[].percentage | float | 占比百分比，保留一位小数 |

---

## 4. 区县用户列表

分页查询区县下的用户明细，支持关键词搜索和用户等级筛选。

```
POST /api/county/user-list
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| countyId | string | 否 | 区县 ID，不传则查全部区县 |
| keyword | string | 否 | 搜索关键词，匹配用户名称、用户编号、停电编号 |
| userLevel | string | 否 | 用户等级筛选，可选值：`all`、`key`、`sensitive`。不传或传 `all` 表示不筛选 |
| page | int | 否 | 页码，默认 1，最小 1 |
| perPage | int | 否 | 每页条数，默认 20，范围 1-500 |
| snapshotDate | string | 否 | 数据快照日期 |
| snapshotStartDate | string | 否 | 快照日期范围起点 |
| snapshotEndDate | string | 否 | 快照日期范围终点 |

### 请求示例

查询某区县的关键用户，第1页每页5条：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "countyId": "130203",
  "userLevel": "key",
  "page": 1,
  "perPage": 5
}
```

带关键词搜索：

```json
{
  "beginTime": "2025-01-01",
  "endTime": "2026-04-30",
  "keyword": "张",
  "page": 1,
  "perPage": 10
}
```

### 响应示例

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "total": 120,
    "page": 1,
    "perPage": 5,
    "list": [
      {
        "consNo": "1234567890",
        "consName": "唐山钢铁有限公司",
        "countyName": "路南区",
        "tradeName": "大工业",
        "outageNature": "1",
        "isKeyUser": true,
        "isSensitiveUser": false
      },
      {
        "consNo": "9876543210",
        "consName": "路南医院",
        "countyName": "路南区",
        "tradeName": "一般工商业",
        "outageNature": "2",
        "isKeyUser": true,
        "isSensitiveUser": true
      }
    ]
  },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.total | int | 符合条件的总记录数 |
| data.page | int | 当前页码 |
| data.perPage | int | 每页条数 |
| data.list | array | 用户列表 |
| data.list[].consNo | string | 用户编号 |
| data.list[].consName | string | 用户名称 |
| data.list[].countyName | string | 所属区县名称 |
| data.list[].tradeName | string | 所属行业名称 |
| data.list[].outageNature | string | 停电性质编码 |
| data.list[].isKeyUser | bool | 是否关键用户 |
| data.list[].isSensitiveUser | bool | 是否敏感用户 |

---

## 参数校验规则

| 场景 | 错误信息 | HTTP 状态码 |
|------|---------|------------|
| beginTime 或 endTime 缺失 | `beginTime and endTime are required` | 400 |
| beginTime 或 endTime 格式错误 | `beginTime format must be YYYY-MM-DD or YYYY-MM-DD HH:mm:ss` | 400 |
| userLevel 值不合法 | `userLevel must be one of all/key/sensitive` | 400 |
| page 或 perPage 不是整数 | `page and perPage must be integers` | 400 |
| page < 1 | `page must be greater than or equal to 1` | 400 |
| perPage 不在 1-500 范围 | `perPage must be between 1 and 500` | 400 |
| 访问不存在的接口 | `Resource not found` | 404 |
| 使用错误的 HTTP 方法 | `Method not allowed` | 405 |
| 服务端数据库异常 | `Failed to query xxx` | 500 |
