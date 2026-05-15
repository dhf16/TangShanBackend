# 右侧模块接口说明

Base URL:

```text
http://127.0.0.1:5000/api
```

线上或他人本机测试时，把 `127.0.0.1:5000` 换成实际后端地址即可。

所有业务接口默认使用：

```http
Content-Type: application/json
```

## 一、统一响应格式

成功：

```json
{
  "code": 0,
  "success": true,
  "message": "ok",
  "data": {},
  "timestamp": "2026-05-14T10:00:00+08:00"
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
  "timestamp": "2026-05-14T10:00:00+08:00"
}
```

## 二、公共请求参数

除详情接口外，大部分接口都支持以下参数。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 开始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | 是 | 结束时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| countyId | string | 否 | 区县/供电单位 ID |
| snapshotDate | string | 否 | 快照日期，精确匹配 |
| snapshotStartDate | string | 否 | 快照开始日期 |
| snapshotEndDate | string | 否 | 快照结束日期 |
| page | number | 列表接口可传 | 页码，默认 `1` |
| perPage | number | 列表接口可传 | 每页数量，默认 `20`，范围 `1-500` |

时间筛选口径：

```sql
ou.begin_time >= beginTime
AND ou.begin_time <= endTime
```

如果同时传入 `snapshotDate` 和 `snapshotStartDate/snapshotEndDate`，优先使用 `snapshotDate`。

## 三、健康检查

```http
GET /api/health
```

完整测试地址：

```text
GET http://127.0.0.1:5000/api/health
```

返回示例：

```json
{
  "status": "ok"
}
```

## 四、右侧总览

```http
POST /api/right-panel/overview
```

用于一次性获取右侧总览数据，包括县区告警灯、故障定位汇总、停电范围汇总。

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59"
}
```

返回 `data` 主要字段：

| 字段 | 说明 |
| --- | --- |
| countyWarnings | 县区告警灯列表 |
| faultLocation | 电力故障定位汇总 |
| outageScope | 停电范围评估汇总 |

## 五、电力故障定位汇总

```http
POST /api/fault/summary
```

用于右侧“电力故障定位”图表统计。

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59"
}
```

返回 `data` 主要字段：

| 字段 | 说明 |
| --- | --- |
| highImpact.count | 高影响数量，影响用户数大于 5000 |
| mediumImpact.count | 中影响数量，影响用户数 1000-5000 |
| lowImpact.count | 低影响数量，影响用户数小于 1000 |
| modes.line | 线路维度统计 |
| modes.feeder | 兼容旧字段，和 `line` 口径一致 |
| modes.substation | 变电站维度统计 |

`modes.*` 中常见字段：

| 字段 | 说明 |
| --- | --- |
| key | 维度 key |
| dimension | 标准维度 |
| total | 当前维度统计数量 |
| matchedEvents | 当前维度可匹配的停电事件数量 |
| bars | `danger/warning/safe` 图表数据 |
| colorBars | `red/yellow/green` 图表数据 |

## 六、电力故障定位事件列表

```http
POST /api/fault/event-list
```

用于新版右侧“电力故障定位”模块。前端切换线路、变电站、设备维度时调用此接口。

请求示例，线路维度：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "dimension": "line",
  "page": 1,
  "perPage": 10
}
```

请求示例，设备维度：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "dimension": "equipment",
  "page": 1,
  "perPage": 10
}
```

额外参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| dimension | string | 否 | `line`、`feeder`、`substation`、`equipment`，默认 `line` |
| keyword | string | 否 | 匹配停电编号或区县名称 |
| outageNature | string | 否 | 停电性质，可传 `planned`、`fault`、`other`、`01`、`02`、`03` |

返回 `data` 主要字段：

| 字段 | 说明 |
| --- | --- |
| summary | 当前筛选条件下的事件统计 |
| total | 总条数 |
| page | 当前页 |
| perPage | 每页数量 |
| dimension | 实际查询维度 |
| list | 事件列表 |

`list` 单项主要字段：

| 字段 | 说明 |
| --- | --- |
| outageNumber | 停电事件编号 |
| countyId / countyName | 区县 ID / 区县名称 |
| affectedUsers | 影响用户数 |
| affectedEquipment | 影响设备数 |
| outageNature / outageNatureCode | 停电性质 |
| isRestored | 是否已复电 |
| beginTime / endTime | 停电开始/结束时间 |
| feederId / feederName | 主馈线 ID / 名称 |
| feederIds / feederNames | 当前事件匹配到的馈线 ID / 名称列表 |
| substationId / substationName | 变电站 ID / 名称 |
| maintGroupName | 供电所/运维班组 |
| equipmentIds / equipmentNames | 当前事件涉及设备 ID / 名称列表 |
| matchStatus | `equipment_feeder_matched` 或 `equipment_only` |

当前馈线查询逻辑：

```text
outage_user_full.equipment_id
-> equipment_feeder.equipment_id
-> equipment_feeder.feeder_id
-> feeder.feeder_id
```

如果能匹配到馈线，`matchStatus = equipment_feeder_matched`；如果只能拿到停电事件设备，`matchStatus = equipment_only`。

## 七、故障设备列表兼容接口

```http
POST /api/fault/equipment-list
```

这是旧版兼容接口，返回结构和停电事件列表类似。新版优先使用：

```http
POST /api/fault/event-list
```

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 10
}
```

## 八、停电范围评估汇总

```http
POST /api/outage-scope/summary
```

用于右侧“停电范围评估”汇总统计。

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59"
}
```

返回 `data` 主要字段：

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

## 九、停电范围事件列表

```http
POST /api/outage-scope/event-list
```

用于停电范围评估模块的通用停电事件列表。

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 10
}
```

带筛选示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "keyword": "路北",
  "outageNature": "fault",
  "page": 1,
  "perPage": 10
}
```

返回结构同 `/api/fault/event-list` 的列表结构，但此接口不使用 `dimension` 过滤。

## 十、停电范围链路列表

```http
POST /api/outage-scope/chains
```

用于右侧“停电范围评估”的链路卡片列表，对应前端展示：

```text
停电事件编号
馈线 -> 变电站 -> 供电所
重要用户 / 敏感用户 / 普通用户影响数量
```

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 10
}
```

返回 `data.list` 单项主要字段：

| 字段 | 说明 |
| --- | --- |
| outageNumber | 停电事件编号 |
| countyName | 区县/供电单位名称 |
| feederName / rdtFeederName | 主馈线名称 |
| feederIds / feederNames | 当前事件匹配到的馈线 ID / 名称列表 |
| substationName / rdtSubsName | 变电站名称 |
| maintGroupName | 供电所/运维班组 |
| equipmentIds / equipmentNames | 当前事件涉及设备 ID / 名称列表 |
| importantUsers | 重要用户列表 |
| sensitiveUsers | 敏感用户列表 |
| importantUserText | 重要用户展示文本 |
| sensitiveUserText | 敏感用户展示文本 |
| normalUserCount | 普通用户影响数量 |
| matchStatus | `equipment_feeder_matched` 或 `equipment_only` |

已验证示例数据中，`/api/outage-scope/chains` 可返回 `total = 1939`，部分事件可以匹配到馈线：

```json
{
  "outageNumber": "CMS20250630040514",
  "countyName": "固安县供电公司",
  "feederIds": ["01DKX-9230"],
  "feederNames": ["213知南路"],
  "equipmentIds": ["b0f6e127e98af6df86596206710159b0f51f991718"],
  "matchStatus": "equipment_feeder_matched"
}
```

## 十一、右侧停电事件详情

```http
POST /api/right-panel/outage-event-detail
```

用于根据停电事件编号查询单个事件详情。

请求示例：

```json
{
  "outageNumber": "CMS20250630040514"
}
```

返回 `data` 主要字段：

| 字段 | 说明 |
| --- | --- |
| outageNumber | 停电事件编号 |
| countyId / countyName | 区县 ID / 名称 |
| affectedUsers / affectedEquipment | 影响用户数 / 影响设备数 |
| outageNature / outageNatureCode | 停电性质 |
| isRestored / status | 是否复电 / 状态 |
| beginTime / endTime | 停电开始/结束时间 |
| feederIds / feederNames | 匹配到的馈线 ID / 名称列表 |
| equipmentIds / equipmentNames | 涉及设备 ID / 名称列表 |
| keyUserCount | 重要用户数 |
| sensitiveUserCount | 敏感用户数 |
| normalUserCount | 普通用户数 |
| matchStatus | 匹配状态 |

## 十二、右侧停电事件列表兼容接口

```http
POST /api/right-panel/outage-events
```

返回结构与 `/api/outage-scope/event-list` 一致，用于右侧模块独立调用。

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 10
}
```

## 十三、右侧停电链路兼容接口

```http
POST /api/right-panel/outage-chains
```

返回结构与 `/api/outage-scope/chains` 一致，用于右侧模块独立调用。

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 10
}
```

## 十四、Apifox 建议测试顺序

1. `GET /api/health`
2. `POST /api/outage-scope/chains`
3. `POST /api/right-panel/outage-event-detail`
4. `POST /api/fault/event-list`，先测 `dimension=equipment`
5. `POST /api/fault/event-list`，再测 `dimension=line`
6. `POST /api/outage-scope/summary`
7. `POST /api/fault/summary`
8. `POST /api/right-panel/overview`

推荐测试时间范围：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 3
}
```

## 十五、注意事项

- `.env` 是本地真实数据库配置文件，不要提交到 GitHub。
- `.env.example` 只放示例配置，不放真实密码。
- 当前右侧链路数据已按 `outage_user_full -> equipment_feeder -> feeder` 对齐。
- 若某条事件无法匹配到馈线，接口不会报错，会返回 `matchStatus = equipment_only`。
- `/api/fault/event-list` 当前功能可用，但在大时间范围下响应可能较慢，后续如前端高频调用建议继续做分页 SQL 优化。
