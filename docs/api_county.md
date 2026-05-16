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

查询区县级别的用户分类统计，同时可用于渲染柱状图。有三种用法：
- **不传 countyId 和 cityId**：返回所有区县的汇总 + 各区县明细（含百分比）
- **传 cityId**：返回该城市下各区县的汇总 + 各区县明细（含百分比）
- **传 countyId**：返回该区县的汇总统计 + 该区县下运维班组的分布明细（含百分比）

> `countyId` 和 `cityId` 互斥，只能传其中一个。

```
POST /api/county/stats
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| countyId | string | 否 | 区县 ID，传入则返回该区县统计 + 运维班组分布。与 cityId 互斥 |
| cityId | string | 否 | 城市 ID，传入则只返回该城市下各区县统计。与 countyId 互斥 |
| snapshotDate | string | 否 | 数据快照日期，格式 `YYYY-MM-DD`，精确匹配某一天的数据 |
| snapshotStartDate | string | 否 | 快照日期范围起点，与 snapshotDate 互斥 |
| snapshotEndDate | string | 否 | 快照日期范围终点，与 snapshotDate 互斥 |

> snapshotDate 与 snapshotStartDate/snapshotEndDate 的关系：传了 snapshotDate 则忽略范围参数；不传 snapshotDate 才使用范围筛选。

### 请求示例

查询所有区县：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

查询指定城市下的区县：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "cityId": "130200"
}
```

查询指定区县（含运维班组分布）：

```json
{
  "beginTime": "2025-01-01",
  "endTime": "2026-04-30",
  "countyId": "130203"
}
```

### 响应示例（不传 countyId / 传 cityId）

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
        "name": "路北区",
        "id": "130202",
        "totalUsers": 500,
        "keyUsers": 80,
        "sensitiveUsers": 100,
        "normalUsers": 320,
        "keyPercentage": 14.5,
        "sensitivePercentage": 18.2
      },
      {
        "name": "路南区",
        "id": "130203",
        "totalUsers": 400,
        "keyUsers": 60,
        "sensitiveUsers": 90,
        "normalUsers": 250,
        "keyPercentage": 10.9,
        "sensitivePercentage": 16.4
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
    "summary": {
      "totalUsers": 400,
      "keyUsers": 60,
      "sensitiveUsers": 90,
      "normalUsers": 250
    },
    "list": [
      {
        "name": "运维一班",
        "id": "MG001",
        "keyUsers": 30,
        "sensitiveUsers": 40,
        "keyPercentage": 16.7,
        "sensitivePercentage": 22.2
      },
      {
        "name": "运维二班",
        "id": "MG002",
        "keyUsers": 20,
        "sensitiveUsers": 25,
        "keyPercentage": 11.1,
        "sensitivePercentage": 13.9
      }
    ]
  },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.summary | object | 汇总统计 |
| data.summary.totalUsers | int | 用户总数 |
| data.summary.keyUsers | int | 关键用户数 |
| data.summary.sensitiveUsers | int | 敏感用户数 |
| data.summary.normalUsers | int | 普通用户数 |
| data.list | array | 分布明细。不传 countyId 时按区县分组，传 countyId 时按运维班组分组 |
| data.list[].name | string | 分组名称（区县名称或运维班组名称） |
| data.list[].id | string | 分组 ID（区县 ID 或运维班组 ID） |
| data.list[].totalUsers | int | 该分组用户总数（仅按区县分组时返回） |
| data.list[].keyUsers | int | 该分组关键用户数 |
| data.list[].sensitiveUsers | int | 该分组敏感用户数 |
| data.list[].normalUsers | int | 该分组普通用户数（仅按区县分组时返回） |
| data.list[].keyPercentage | float | 该分组重点用户占 keyUsers + sensitiveUsers 总和的百分比，保留一位小数 |
| data.list[].sensitivePercentage | float | 该分组敏感用户占 keyUsers + sensitiveUsers 总和的百分比，保留一位小数 |

> **注意**：一个用户可以同时是重点用户和敏感用户，因此 keyUsers 和 sensitiveUsers 可能存在重叠。

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
| userLevel | string | 否 | 用户等级筛选，可选值：`all`、`key`、`sensitive`、`key_sensitive`（重点+敏感用户）。不传或传 `all` 表示不筛选 |
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
        "outageNumber": "OT20250101001",
        "isKeyUser": true,
        "isSensitiveUser": false
      },
      {
        "consNo": "9876543210",
        "consName": "路南医院",
        "countyName": "路南区",
        "tradeName": "一般工商业",
        "outageNature": "2",
        "outageNumber": "OT20250101002",
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
| data.list[].outageNumber | string | 停电编号 |
| data.list[].isKeyUser | bool | 是否关键用户 |
| data.list[].isSensitiveUser | bool | 是否敏感用户 |

---

## 4.5 用户停电统计（按用户去重）

按用户编号去重，统计每个用户在指定时间范围内的停电次数，支持关键词搜索和停电次数筛选。

```
POST /api/county/user-outage-stats
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| countyId | string | 否 | 区县 ID，不传则查全部区县 |
| keyword | string | 否 | 搜索关键词，匹配用户名称、用户编号 |
| outageCount | string | 否 | 停电次数筛选，可选值：`1`、`2`、`3+`（3次及以上）。不传表示不按停电次数筛选 |
| page | int | 否 | 页码，默认 1，最小 1 |
| perPage | int | 否 | 每页条数，默认 20，范围 1-500 |

### 请求示例

查询全部用户的停电统计：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "page": 1,
  "perPage": 20
}
```

按停电次数筛选（停电3次及以上的用户）：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "outageCount": "3+",
  "page": 1,
  "perPage": 10
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
    "total": 85,
    "page": 1,
    "perPage": 20,
    "list": [
      {
        "consNo": "1234567890",
        "consName": "唐山钢铁有限公司",
        "countyName": "路南区",
        "tradeName": "大工业",
        "outageCount": 3
      },
      {
        "consNo": "9876543210",
        "consName": "路南医院",
        "countyName": "路北区",
        "tradeName": "一般工商业",
        "outageCount": 1
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
| data.list | array | 用户停电统计列表，按停电次数降序 |
| data.list[].consNo | string | 用户编号 |
| data.list[].consName | string | 用户名称 |
| data.list[].countyName | string | 所属区县名称 |
| data.list[].tradeName | string | 所属行业名称 |
| data.list[].outageCount | int | 停电次数 |

---

## 5. 区县时间趋势

查询指定时间范围内重点用户和敏感用户的时间分布趋势，用于渲染折线图。接口将时间范围均分为 6 个时间段，统计每个时间段内的重点用户和敏感用户数量。无数据的时间段自动返回 0，保证始终返回 6 个数据点。

```
POST /api/county/trend
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| countyId | string | 否 | 区县 ID，不传则统计全部区县 |

### 分段规则

接口自动将 `[beginTime, endTime]` 均分为 6 个时间段，每个时间段的结束时间作为折线图 X 轴坐标。

**示例**：`beginTime = 2025-01-01 21:31:00`，`endTime = 2025-01-01 21:34:00`（共 3 分钟）：

| 段 | 时间范围 | X 轴标签（timePoint） |
|----|---------|---------------------|
| 1 | 21:31:00 ~ 21:31:30 | 2025-01-01 21:31:30 |
| 2 | 21:31:30 ~ 21:32:00 | 2025-01-01 21:32:00 |
| 3 | 21:32:00 ~ 21:32:30 | 2025-01-01 21:32:30 |
| 4 | 21:32:30 ~ 21:33:00 | 2025-01-01 21:33:00 |
| 5 | 21:33:00 ~ 21:33:30 | 2025-01-01 21:33:30 |
| 6 | 21:33:30 ~ 21:34:00 | 2025-01-01 21:34:00 |

### 请求示例

短时间范围（分钟级）：

```json
{
  "beginTime": "2025-01-01 21:31:00",
  "endTime": "2025-01-01 21:34:00",
  "countyId": "130202"
}
```

长时间范围（月级）：

```json
{
  "beginTime": "2025-01-01",
  "endTime": "2025-06-30"
}
```

### 响应示例

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "points": [
      {"timePoint": "2025-01-01 21:31:30", "keyUsers": 3, "sensitiveUsers": 5},
      {"timePoint": "2025-01-01 21:32:00", "keyUsers": 0, "sensitiveUsers": 0},
      {"timePoint": "2025-01-01 21:32:30", "keyUsers": 1, "sensitiveUsers": 2},
      {"timePoint": "2025-01-01 21:33:00", "keyUsers": 4, "sensitiveUsers": 1},
      {"timePoint": "2025-01-01 21:33:30", "keyUsers": 0, "sensitiveUsers": 0},
      {"timePoint": "2025-01-01 21:34:00", "keyUsers": 2, "sensitiveUsers": 3}
    ]
  },
  "timestamp": "2026-05-08T14:30:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.points | array | 时间趋势数据点，固定 6 个 |
| data.points[].timePoint | string | 时间段结束时间，格式 `YYYY-MM-DD HH:mm:ss` |
| data.points[].keyUsers | int | 该时间段内重点用户数量 |
| data.points[].sensitiveUsers | int | 该时间段内敏感用户数量 |

---

## 6. 停电次数分布

查询指定时间范围内重点用户和敏感用户按停电次数的分布，用于渲染环状图。分别统计停电 1 次、2 次、3 次及以上的用户数量和占比。

```
POST /api/county/outage-freq
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| countyId | string | 否 | 区县 ID，不传则统计全部区县 |

### 请求示例

统计全部区县：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

统计指定区县：

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
    "keyUsers": {
      "total": 142,
      "distribution": [
        { "label": "停电1次", "count": 112, "percentage": 78.9 },
        { "label": "停电2次", "count": 20, "percentage": 14.1 },
        { "label": "停电3次及以上", "count": 10, "percentage": 7.0 }
      ]
    },
    "sensitiveUsers": {
      "total": 85,
      "distribution": [
        { "label": "停电1次", "count": 60, "percentage": 70.6 },
        { "label": "停电2次", "count": 15, "percentage": 17.6 },
        { "label": "停电3次及以上", "count": 10, "percentage": 11.8 }
      ]
    }
  },
  "timestamp": "2026-05-11T10:00:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.keyUsers | object | 重点用户停电次数分布 |
| data.keyUsers.total | int | 重点用户总数（停电1次 + 停电2次 + 停电3次及以上） |
| data.keyUsers.distribution | array | 分布明细，固定 3 项 |
| data.keyUsers.distribution[].label | string | 档位标签：`停电1次`、`停电2次`、`停电3次及以上` |
| data.keyUsers.distribution[].count | int | 该档位用户数 |
| data.keyUsers.distribution[].percentage | float | 该档位占该类型用户总数的百分比，保留一位小数 |
| data.sensitiveUsers | object | 敏感用户停电次数分布，结构同 keyUsers |

### 统计逻辑

1. 按 `cons_no`（用户编号）分组，统计每个用户在时间范围内的停电记录数
2. 将停电次数分为三个桶：1 次、2 次、3 次及以上
3. 分别对 `is_key_user = 1` 和 `is_sensitive_user = 1` 各独立统计一次
4. 一个用户可以同时是重点用户和敏感用户，两部分独立计算

---

## 7. 设备影响统计

查询指定时间范围内停电影响的设备数量、敏感用户数量、重点用户数量，以及影响重点用户 ≥20 的设备故障占比。

```
POST /api/county/equipment-stats
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| cityId | string | 否 | 城市 ID，传入则只统计该城市。与 countyId 互斥 |
| countyId | string | 否 | 区县 ID，传入则只统计该区县。与 cityId 互斥 |

### 请求示例

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

指定城市：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
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
    "equipmentCount": 1280,
    "sensitiveUsers": 350,
    "keyUsers": 200,
    "highImpactEquipmentCount": 45,
    "highImpactPercentage": 3.5
  },
  "timestamp": "2026-05-12T10:00:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.equipmentCount | int | 停电影响的设备数量（去重） |
| data.sensitiveUsers | int | 停电涉及的敏感用户数量（去重） |
| data.keyUsers | int | 停电涉及的重点用户数量（去重） |
| data.highImpactEquipmentCount | int | 影响重点用户 ≥20 的设备数量 |
| data.highImpactPercentage | float | 影响重点用户 ≥20 的设备占总停电设备的百分比，保留一位小数 |

---

## 8. 设备影响明细

查询指定时间范围内每台停电设备的影响情况，返回设备编号、名称、影响的重点用户数、敏感用户数、停电事件数。

```
POST /api/county/equipment-list
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| cityId | string | 否 | 城市 ID，传入则只统计该城市。与 countyId 互斥 |
| countyId | string | 否 | 区县 ID，传入则只统计该区县。与 cityId 互斥 |
| top | int | 否 | 返回前 N 条数据（按 keyUsers 降序），不传则返回全部 |

### 请求示例

查询全部设备：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

查询 Top 10：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "top": 10
}
```

指定城市：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
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
        "equipmentId": "EQ001",
        "equipmentName": "10kV某某开关",
        "keyUsers": 35,
        "sensitiveUsers": 12,
        "outageCount": 8
      },
      {
        "equipmentId": "EQ002",
        "equipmentName": "10kV某某变压器",
        "keyUsers": 22,
        "sensitiveUsers": 5,
        "outageCount": 3
      }
    ]
  },
  "timestamp": "2026-05-12T10:00:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.list | array | 设备影响列表，按 keyUsers 降序、outageCount 降序 |
| data.list[].equipmentId | string | 设备编号 |
| data.list[].equipmentName | string | 设备名称 |
| data.list[].keyUsers | int | 该设备影响的重点用户数量（去重） |
| data.list[].sensitiveUsers | int | 该设备影响的敏感用户数量（去重） |
| data.list[].outageCount | int | 该设备关联的停电事件数量（去重） |

---

## 9. 设备影响分页查询

分页查询指定时间范围内每台停电设备的影响情况。与 [设备影响明细](#8-设备影响明细) 的区别：支持分页、不含停电事件数（性能更优）。

```
POST /api/county/equipment-page
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| cityId | string | 否 | 城市 ID，传入则只统计该城市。与 countyId 互斥 |
| countyId | string | 否 | 区县 ID，传入则只统计该区县。与 cityId 互斥 |
| page | int | 否 | 页码，默认 1，最小 1 |
| perPage | int | 否 | 每页条数，默认 20，范围 1-500 |

### 请求示例

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "page": 1,
  "perPage": 20
}
```

### 响应示例

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "total": 2431,
    "page": 1,
    "perPage": 20,
    "list": [
      {
        "equipmentId": "EQ001",
        "equipmentName": "10kV某某开关",
        "keyUsers": 35,
        "sensitiveUsers": 12
      },
      {
        "equipmentId": "EQ002",
        "equipmentName": "10kV某某变压器",
        "keyUsers": 22,
        "sensitiveUsers": 5
      }
    ]
  },
  "timestamp": "2026-05-12T10:00:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.total | int | 符合条件的设备总数（去重） |
| data.page | int | 当前页码 |
| data.perPage | int | 每页条数 |
| data.list | array | 设备列表，按 keyUsers 降序 |
| data.list[].equipmentId | string | 设备编号 |
| data.list[].equipmentName | string | 设备名称 |
| data.list[].keyUsers | int | 该设备影响的重点用户数量（去重） |
| data.list[].sensitiveUsers | int | 该设备影响的敏感用户数量（去重） |

---

## 10. 设备详情

根据设备编号查询该设备的停电影响详情，包括受影响的重点用户列表和敏感用户列表。

```
POST /api/county/equipment-detail
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| equipmentId | string | **是** | 设备编号 |

### 请求示例

```json
{
  "equipmentId": "EQ001"
}
```

### 响应示例

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "equipmentId": "EQ001",
    "equipmentName": "10kV某某开关",
    "equipmentType": "01",
    "keyUserCount": 35,
    "sensitiveUserCount": 12,
    "keyUsers": [
      {
        "consNo": "1234567890",
        "consName": "唐山钢铁有限公司",
        "tradeName": "大工业",
        "countyName": "路北区",
        "consAddr": "唐山市路北区某某路1号",
        "consTypeName": "大工业",
        "voltLevel": "10kV"
      }
    ],
    "sensitiveUsers": [
      {
        "consNo": "9876543210",
        "consName": "路北医院",
        "tradeName": "一般工商业",
        "countyName": "路北区",
        "consAddr": "唐山市路北区某某路2号",
        "consTypeName": "一般工商业",
        "voltLevel": "380V"
      }
    ]
  },
  "timestamp": "2026-05-12T10:00:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.equipmentId | string | 设备编号 |
| data.equipmentName | string | 设备名称 |
| data.equipmentType | string | 设备类型 |
| data.keyUserCount | int | 影响的重点用户数量（去重） |
| data.sensitiveUserCount | int | 影响的敏感用户数量（去重） |
| data.keyUsers | array | 重点用户列表 |
| data.keyUsers[].consNo | string | 用户编号 |
| data.keyUsers[].consName | string | 用户名称 |
| data.keyUsers[].tradeName | string | 行业名称 |
| data.keyUsers[].countyName | string | 所属区县 |
| data.keyUsers[].consAddr | string | 用户地址 |
| data.keyUsers[].consTypeName | string | 用户类型名称 |
| data.keyUsers[].voltLevel | string | 电压等级 |
| data.sensitiveUsers | array | 敏感用户列表，字段同 keyUsers |

> 一个用户可以同时是重点用户和敏感用户，因此可能同时出现在 keyUsers 和 sensitiveUsers 中。

---

## 11. 用户停电详情

根据停电编号 + 用户编号查询该用户某次停电的详细信息。

```
POST /api/county/user-detail
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| consNo | string | **是** | 用户编号 |
| outageNumber | string | **是** | 停电编号 |

### 请求示例

```json
{
  "consNo": "1234567890",
  "outageNumber": "OT20250101001"
}
```

### 响应示例

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {
    "consNo": "1234567890",
    "consName": "唐山钢铁有限公司",
    "consAddr": "唐山市路北区某某路1号",
    "outageNature": "1",
    "equipmentName": "10kV某某开关",
    "tgName": "某某台区",
    "tradeName": "大工业"
  },
  "timestamp": "2026-05-12T10:00:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.consNo | string | 用户编号 |
| data.consName | string | 用户名称 |
| data.consAddr | string | 用户地址 |
| data.outageNature | string | 停电性质 |
| data.equipmentName | string | 设备名称 |
| data.tgName | string | 台区名称 |
| data.tradeName | string | 行业名称 |

---

## 12. 用户停电时间线

根据用户编号查询该用户在指定时间范围内的所有停电事件，返回用户基本信息及每次停电的开始/复电时间。

```
POST /api/county/user-outage-detail
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| beginTime | string | **是** | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | **是** | 查询截止时间，格式同上 |
| consNo | string | **是** | 用户编号 |
| countyId | string | 否 | 区县 ID，不传则不限制区县 |

### 请求示例

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "consNo": "1234567890"
}
```

带区县筛选：

```json
{
  "beginTime": "2025-01-01",
  "endTime": "2026-04-30",
  "consNo": "1234567890",
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
    "consNo": "1234567890",
    "consName": "唐山钢铁有限公司",
    "countyName": "路南区",
    "tradeName": "大工业",
    "consAddr": "唐山市路南区某某路123号",
    "outageCount": 3,
    "outages": [
      { "beginTime": "2025-03-15 14:00:00", "endTime": "2025-03-15 16:30:00" },
      { "beginTime": "2025-02-01 08:00:00", "endTime": "" },
      { "beginTime": "2025-01-01 10:00:00", "endTime": "2025-01-01 12:00:00" }
    ]
  },
  "timestamp": "2026-05-12T10:00:00+08:00"
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| data.consNo | string | 用户编号 |
| data.consName | string | 用户名称 |
| data.countyName | string | 所属区县名称 |
| data.tradeName | string | 所属行业名称 |
| data.consAddr | string | 用户地址 |
| data.outageCount | int | 停电次数 |
| data.outages | array | 停电事件列表，按开始时间降序 |
| data.outages[].beginTime | string | 停电开始时间 |
| data.outages[].endTime | string | 复电时间，为空字符串表示尚未复电 |

---

## 参数校验规则

| 场景 | 错误信息 | HTTP 状态码 |
|------|---------|------------|
| beginTime 或 endTime 缺失 | `beginTime and endTime are required` | 400 |
| beginTime 或 endTime 格式错误 | `beginTime format must be YYYY-MM-DD or YYYY-MM-DD HH:mm:ss` | 400 |
| userLevel 值不合法 | `userLevel must be one of all/key/sensitive/key_sensitive` | 400 |
| countyId 和 cityId 同时传入 | `countyId and cityId are mutually exclusive` | 400 |
| page 或 perPage 不是整数 | `page and perPage must be integers` | 400 |
| page < 1 | `page must be greater than or equal to 1` | 400 |
| perPage 不在 1-500 范围 | `perPage must be between 1 and 500` | 400 |
| 访问不存在的接口 | `Resource not found` | 404 |
| 使用错误的 HTTP 方法 | `Method not allowed` | 405 |
| 服务端数据库异常 | `Failed to query xxx` | 500 |
