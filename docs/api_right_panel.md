# 右侧模块 API 说明

Base URL: `http://{host}:5000/api`

本文件说明右侧模块相关接口，主要覆盖：

- 电力故障定位
- 停电范围评估
- 停电事件列表与详情
- 右侧模块总览

所有业务接口默认使用 `POST` + `JSON`，请求头：

```http
Content-Type: application/json
```

## 统一响应格式

成功：

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {},
  "timestamp": "2026-05-10T00:00:00+08:00"
}
```

失败：

```json
{
  "code": 400,
  "success": false,
  "message": "beginTime and endTime are required",
  "data": null,
  "errors": [
    {
      "message": "beginTime and endTime are required",
      "code": 400
    }
  ],
  "timestamp": "2026-05-10T00:00:00+08:00"
}
```

## 公共请求参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 开始时间，格式 `YYYY-MM-DD HH:mm:ss` 或 `YYYY-MM-DD` |
| endTime | string | 是 | 结束时间，格式 `YYYY-MM-DD HH:mm:ss` 或 `YYYY-MM-DD` |
| countyId | string | 否 | 区县/供电单位 ID |
| snapshotDate | string | 否 | 快照日期，精确匹配 |
| snapshotStartDate | string | 否 | 快照开始日期 |
| snapshotEndDate | string | 否 | 快照结束日期 |
| page | number | 列表接口必填 | 页码，从 1 开始 |
| perPage | number | 列表接口必填 | 每页数量，范围 1-500 |

说明：

- 时间筛选逻辑与左侧模块保持一致：`begin_time >= beginTime` 且 `begin_time <= endTime`。
- `snapshotDate` 与 `snapshotStartDate/snapshotEndDate` 同时传入时，优先使用 `snapshotDate`。

## 1. 健康检查

```http
GET /api/health
```

用于确认后端服务是否启动。

## 2. 电力故障定位汇总

```http
POST /api/fault/summary
```

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

返回 `data` 说明：

| 字段 | 说明 |
| --- | --- |
| highImpact | 高影响数量，影响用户数大于 5000 |
| mediumImpact | 中影响数量，影响用户数 1000-5000 |
| lowImpact | 低影响数量，影响用户数小于 1000 |
| modes.feeder | 按馈线统计 |
| modes.substation | 按变电站统计 |

## 3. 停电范围汇总

```http
POST /api/outage-scope/summary
```

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

返回 `data` 说明：

| 字段 | 说明 |
| --- | --- |
| totalEvents | 停电事件总数 |
| activeEvents | 未复电事件数 |
| totalEquipments | 影响设备数 |
| totalUsers | 影响用户数 |
| restoredEvents | 已复电事件数 |
| unrestoredEvents | 未复电事件数 |
| affectedEquipment | 影响设备数 |
| affectedUsers | 影响用户数 |

## 4. 停电事件列表

```http
POST /api/outage-scope/event-list
```

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "page": 1,
  "perPage": 10
}
```

带筛选请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "page": 1,
  "perPage": 10,
  "countyId": "1100F3DE239B6FADE050007F01006CBE",
  "keyword": "路北",
  "outageNature": "fault"
}
```

额外参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| keyword | string | 否 | 匹配停电编号或区县名称 |
| outageNature | string | 否 | 停电性质，可传 `planned`、`fault`、`other`、`01`、`02`、`03` |

返回 `data` 说明：

| 字段 | 说明 |
| --- | --- |
| summary | 停电事件统计 |
| total | 总条数 |
| page | 当前页 |
| perPage | 每页数量 |
| list | 停电事件列表 |

## 5. 停电范围链路详情

```http
POST /api/outage-scope/chains
```

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "page": 1,
  "perPage": 10
}
```

返回列表字段说明：

| 字段 | 说明 |
| --- | --- |
| outageNumber | 停电事件编号 |
| countyName | 区县/供电单位名称 |
| rdtFeederName | 馈线名称 |
| rdtSubsName | 变电站名称 |
| maintGroupName | 运维班组/供电所名称 |
| importantUsers | 重要用户列表 |
| sensitiveUsers | 敏感用户列表 |
| normalUserCount | 普通用户影响数量 |

## 6. 停电事件详情

```http
POST /api/right-panel/outage-event-detail
```

请求示例：

```json
{
  "outageNumber": "CMS20250630040525"
}
```

返回 `data` 为单个停电事件详情，包含停电编号、区县、开始时间、结束时间、停电性质、复电状态、馈线、变电站、运维班组和用户数量等信息。

## 7. 右侧模块总览

```http
POST /api/right-panel/overview
```

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59"
}
```

返回 `data` 说明：

| 字段 | 说明 |
| --- | --- |
| countyWarnings | 区县预警灯数据 |
| faultLocation | 电力故障定位汇总 |
| outageScope | 停电范围汇总 |

## 8. 右侧停电事件列表

```http
POST /api/right-panel/outage-events
```

该接口与 `/api/outage-scope/event-list` 返回结构一致，用于右侧模块独立调用。

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-04-30 23:59:59",
  "page": 1,
  "perPage": 10
}
```

## 测试建议顺序

1. `GET /api/health`
2. `POST /api/outage-scope/summary`
3. `POST /api/outage-scope/event-list`
4. `POST /api/fault/summary`
5. `POST /api/outage-scope/chains`
6. `POST /api/right-panel/outage-event-detail`
7. `POST /api/right-panel/overview`
