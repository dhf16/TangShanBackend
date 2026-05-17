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

## 二、健康检查

```http
GET /api/health
```

返回示例：

```json
{
  "status": "ok"
}
```

## 三、县区警示灯（模块一）

```http
POST /api/right-panel/county-warnings
```

查询指定城市下各区县在给定时间段内是否存在停电事件，前端根据 `hasOutage` 渲染红绿灯。

请求参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 查询起始时间，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm:ss` |
| endTime | string | 是 | 查询截止时间，格式同上 |
| cityId | string | 否 | 地市 ID，限定查询哪座城市下属的区县；不传时默认唐山市 ID `1100F3DE22316FADE050007F01006CBE` |

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59"
}
```

带 cityId 示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "cityId": "1100F3DE22316FADE050007F01006CBE"
}
```

返回 `data` 结构（数组）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| countyName | string | 区县/供电单位名称 |
| hasOutage | bool | 该区县是否存在停电事件，`true` 渲染红灯，`false` 渲染绿灯 |

判断逻辑：`outage_user_full` 表中该区县在 `beginTime` ~ `endTime` 内是否存在记录（`COUNT > 0`），不考虑复电状态。

返回示例：

```json
{
  "code": 0,
  "success": true,
  "data": [
    { "countyName": "滦州市供电公司", "hasOutage": true },
    { "countyName": "遵化市供电公司", "hasOutage": true },
    { "countyName": "国网唐山供电公司运维检修部", "hasOutage": false }
  ]
}
```

## 四、电力故障定位（模块二）

```http
POST /api/right-panel/fault-location
```

按维度（馈线/变电站）统计故障分布，前端切换按钮传入不同 `dimension`，后端返回对应维度统计。

请求参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 查询起始时间 |
| endTime | string | 是 | 查询截止时间 |
| dimension | string | 否 | `"feeder"`（馈线，默认）或 `"substation"`（变电站） |
| cityId | string | 否 | 地市 ID，不传时默认唐山市；传 countyId 时不传 cityId |
| countyId | string | 否 | 区县 ID，筛选特定区县 |
| dangerThreshold | int | 否 | danger 阈值，影响用户数 > 此值为 danger，默认 `5000` |
| warningThreshold | int | 否 | warning 阈值，影响用户数 >= 此值且 <= dangerThreshold 为 warning，默认 `1000` |

请求示例（馈线维度）：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "dimension": "feeder"
}
```

请求示例（变电站维度）：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "dimension": "substation"
}
```

统计口径：

- 按维度分组，统计每组影响用户数
- `danger`：影响用户数 > dangerThreshold
- `warning`：影响用户数 >= warningThreshold 且 <= dangerThreshold
- `safe`：影响用户数 < warningThreshold

返回 `data` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| total | int | 当前维度下线路/变电站总数 |
| matchedEvents | int | 当前维度匹配到的停电事件数 |
| danger | int | 高影响数量 |
| warning | int | 中影响数量 |
| safe | int | 低影响数量 |

返回示例：

```json
{
  "code": 0,
  "success": true,
  "data": {
    "total": 298,
    "matchedEvents": 754,
    "danger": 0,
    "warning": 12,
    "safe": 286
  }
}
```

## 五、停电范围评估（模块三）

```http
POST /api/right-panel/outage-scope
```

统计时间范围内的停电事件总数、复电情况、影响设备数、影响用户数。

请求参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 查询起始时间 |
| endTime | string | 是 | 查询截止时间 |
| cityId | string | 否 | 地市 ID，不传时默认唐山市；传 countyId 时不传 cityId |
| countyId | string | 否 | 区县 ID，筛选特定区县 |

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59"
}
```

返回 `data` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| totalEvents | int | 停电事件总数（已复电 + 未复电） |
| restoredEvents | int | 已复电事件数 |
| unrestoredEvents | int | 未复电事件数 |
| affectedEquipment | int | 影响设备数 |
| affectedUsers | int | 影响用户数 |

返回示例：

```json
{
  "code": 0,
  "success": true,
  "data": {
    "totalEvents": 1939,
    "restoredEvents": 1939,
    "unrestoredEvents": 0,
    "affectedEquipment": 3585,
    "affectedUsers": 96887
  }
}
```

## 六、停电事件汇总（模块二二级页面-饼图+进度条）

```http
POST /api/right-panel/outage-events-summary
```

返回停电性质饼图数据和复电进度条数据，不分页。

请求参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 查询起始时间 |
| endTime | string | 是 | 查询截止时间 |
| cityId | string | 否 | 地市 ID，不传时默认唐山市；传 countyId 时不传 cityId |
| countyId | string | 否 | 区县 ID，从模块一点击区县时传入 |
| keyword | string | 否 | 搜索关键词，匹配停电编号或区县名称 |
| outageNature | string | 否 | 停电性质筛选：`01` / `02` / `03` |

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59"
}
```

返回 `data` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| totalEvents | int | 事件总数 |
| natureRatio | array | 停电性质占比，前端直接渲染饼图 |
| restoredEvents | int | 已复电事件数 |
| unrestoredEvents | int | 未复电事件数 |
| restoredRate | float | 复电率百分比，如 `83.33` 表示 83.33% |

`natureRatio` 单项：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| code | string | 原始编码：`01`（计划）、`02`（故障）、`03`（其他） |
| value | int | 事件数量 |
| percent | float | 占比百分比，如 `55.56` |

返回示例：

```json
{
  "code": 0,
  "success": true,
  "data": {
    "totalEvents": 180,
    "natureRatio": [
      { "name": "计划停电", "code": "01", "value": 100, "percent": 55.56 },
      { "name": "故障停电", "code": "02", "value": 50, "percent": 27.78 },
      { "name": "其他", "code": "03", "value": 30, "percent": 16.67 }
    ],
    "restoredEvents": 150,
    "unrestoredEvents": 30,
    "restoredRate": 83.33
  }
}
```

## 七、停电事件列表（模块二二级页面-事件表格）

```http
POST /api/right-panel/outage-events
```

返回分页的事件列表表格数据。

请求参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 查询起始时间 |
| endTime | string | 是 | 查询截止时间 |
| cityId | string | 否 | 地市 ID，不传时默认唐山市；传 countyId 时不传 cityId |
| countyId | string | 否 | 区县 ID，从模块一点击区县时传入 |
| keyword | string | 否 | 搜索关键词，匹配停电编号或区县名称 |
| outageNature | string | 否 | 停电性质筛选：`01` / `02` / `03` |
| page | number | 否 | 页码，默认 `1` |
| perPage | number | 否 | 每页数量，默认 `20`，范围 `1-500` |

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 10
}
```

返回 `data` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| total | int | 事件总条数 |
| page | int | 当前页 |
| perPage | int | 每页数量 |
| list | array | 事件列表 |

`list` 单项字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| outageNumber | string | 停电事件编号，点击"详情"时传给 `/outage-event-detail` |
| countyName | string | 区县/供电单位名称 |
| affectedUsers | int | 影响用户数 |
| outageNature | string | 停电性质原始编码：`01`（计划）、`02`（故障）、`03`（其他） |

返回示例：

```json
{
  "code": 0,
  "success": true,
  "data": {
    "total": 180,
    "page": 1,
    "perPage": 10,
    "list": [
      {
        "outageNumber": "CMS20250630040514",
        "countyName": "路北区供电公司",
        "affectedUsers": 76,
        "outageNature": "01"
      }
    ]
  }
}
```

## 八、停电事件详情（二级页面-详情）

```http
POST /api/right-panel/outage-event-detail
```

根据停电事件编号查询单个事件完整详情。

请求参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| outageNumber | string | 是 | 停电事件编号，来自事件列表的 `outageNumber` |

请求示例：

```json
{
  "outageNumber": "CMS20250630040514"
}
```

返回 `data` 主要字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| outageNumber | string | 停电事件编号 |
| countyName | string | 区县名称 |
| affectedUsers | int | 影响用户数 |
| affectedEquipment | int | 影响设备数 |
| outageNature | string | 停电性质原始编码：`01`（计划）、`02`（故障）、`03`（其他） |
| isRestored | bool | 是否已复电，取 `outage_flag` 官方标记，全部用户复电才算 `true` |
| beginTime | string | 停电开始时间 |
| endTime | string | 停电结束时间，未复电时为 `null` |
| feederNames | array | 匹配到的馈线名称列表 |
| substationName | string | 变电站名称 |
| equipmentNames | array | 涉及设备名称列表 |
| keyUserCount | int | 重要用户数 |
| sensitiveUserCount | int | 敏感用户数 |
| normalUserCount | int | 普通用户数 |
| matchStatus | string | `equipment_feeder_matched` 或 `equipment_only` |

`matchStatus` 说明：

| 值 | 说明 |
| --- | --- |
| equipment_feeder_matched | 已通过 `equipment_id -> equipment_feeder -> feeder` 匹配到馈线 |
| equipment_only | 只能从 `outage_user_full` 拿到设备信息，未匹配到馈线 |

## 九、停电链路列表（模块三二级页面）

```http
POST /api/right-panel/outage-chains
```

用于模块三二级页面，返回每个停电事件的链路名称、重要用户、敏感用户、普通用户影响数量。

区域筛选说明：前端选择"全部"时传 `cityId`，选择具体区县时传 `countyId`，两者二选一，都传则 `countyId` 优先。

当前支持的地市 ID：

| cityId | 名称 |
| --- | --- |
| `1100F3DE22316FADE050007F01006CBE` | 国网唐山供电公司 |

唐山市下辖区县 ID：

| countyId | 名称 |
| --- | --- |
| `1100F3DE22CC6FADE050007F01006CBE` | 丰南区供电公司 |
| `1100F3DE23116FADE050007F01006CBE` | 玉田县供电公司 |
| `1100F3DE22DA6FADE050007F01006CBE` | 迁西县供电公司 |
| `1100F3DE23016FADE050007F01006CBE` | 滦南县供电公司 |
| `1100F3DE22A76FADE050007F01006CBE` | 乐亭县供电公司 |
| `1100F3DE22B96FADE050007F01006CBE` | 滦州市供电公司 |
| `1100F3DE22356FADE050007F01006CBE` | 国网唐山供电公司运维检修部 |
| `1100F3DE22926FADE050007F01006CBE` | 路北区供电公司 |
| `1100F3DE22F06FADE050007F01006CBE` | 迁安市供电公司 |
| `1100F3DE22846FADE050007F01006CBE` | 路北供电中心 |
| `1100F3DE22766FADE050007F01006CBE` | 国网丰润区供电公司 |
| `ff80808157e82836015818bf11ed7b52` | 开平配电区运检班 |
| `8af682c977097a990177c8f91bd60066` | 古冶配电运检班 |

请求参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| beginTime | string | 是 | 查询起始时间 |
| endTime | string | 是 | 查询截止时间 |
| cityId | string | 否 | 地市 ID，选择"全部"时传入，如唐山市 `1100F3DE22316FADE050007F01006CBE` |
| countyId | string | 否 | 区县 ID，选择具体区县时传入，见上表 |
| page | number | 否 | 页码，默认 `1` |
| perPage | number | 否 | 每页数量，默认 `20`，范围 `1-500` |

请求示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "page": 1,
  "perPage": 10
}
```

带区域筛选示例：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59",
  "cityId": "1100F3DE22316FADE050007F01006CBE"
}
```

返回 `data` 主要字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| total | int | 链路总条数 |
| page | int | 当前页 |
| perPage | int | 每页数量 |
| list | array | 链路卡片列表 |

`list` 单项字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| outageNumber | string | 停电事件编号，点击"详情"时传给 `/outage-event-detail` |
| feederName | string | 链路名称（馈线） |
| importantUserCount | int | 重要用户数量 |
| importantUsers | array | 重要用户名称列表 |
| sensitiveUserCount | int | 敏感用户数量 |
| sensitiveUsers | array | 敏感用户名称列表 |
| normalUserCount | int | 普通用户影响数量 |

数据来源：`outage_user_full` 表中 `is_key_user = 1` 为重要用户，`is_sensitive_user = 1` 为敏感用户，其余为普通用户。

返回示例：

```json
{
  "code": 0,
  "success": true,
  "data": {
    "total": 50,
    "page": 1,
    "perPage": 10,
    "list": [
      {
        "outageNumber": "CMS20250630040514",
        "feederName": "10kV路北区示范线01",
        "importantUserCount": 1,
        "importantUsers": ["路北区张伟"],
        "sensitiveUserCount": 4,
        "sensitiveUsers": ["路北区人民医院", "路北区通信枢纽站"],
        "normalUserCount": 23
      }
    ]
  }
}
```

## 十、接口总览

| 接口 | 用途 | 页面位置 |
| --- | --- | --- |
| `POST /right-panel/county-warnings` | 区县红绿灯 | 模块一 一级页面 |
| `POST /right-panel/fault-location` | 故障定位统计 | 模块二 一级页面 |
| `POST /right-panel/outage-scope` | 停电范围统计 | 模块三 一级页面 |
| `POST /right-panel/outage-events-summary` | 饼图 + 复电进度条 | 模块二 二级页面 |
| `POST /right-panel/outage-events` | 事件列表（分页） | 模块二 二级页面 |
| `POST /right-panel/outage-event-detail` | 单条事件详情 | 二级页面-详情 |
| `POST /right-panel/outage-chains` | 链路卡片列表 | 模块三 二级页面 |

## 十一、Apifox 测试建议

推荐测试时间范围：

```json
{
  "beginTime": "2025-01-01 00:00:00",
  "endTime": "2026-01-30 00:10:59"
}
```

测试顺序：

1. `GET /api/health`
2. `POST /api/right-panel/county-warnings`
3. `POST /api/right-panel/fault-location`
4. `POST /api/right-panel/outage-scope`
5. `POST /api/right-panel/outage-events-summary`
6. `POST /api/right-panel/outage-events`
7. `POST /api/right-panel/outage-chains`
8. `POST /api/right-panel/outage-event-detail`（从 outage-events 返回的 list 里取 outageNumber）

## 十二、注意事项

- `.env` 是本地真实数据库配置文件，不要提交到 GitHub。
- 当前查询依赖 `outage_user_full` 表，该表无索引，大时间范围查询可能较慢，后续考虑加索引优化。
- 馈线匹配链路：`outage_user_full.equipment_id -> equipment_feeder -> feeder`，未匹配到的返回 `matchStatus = equipment_only`。
