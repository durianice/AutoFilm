# API 文档

## 基础信息

- **基础路径**: `/api`
- **认证方式**: API Token (需要在请求头中包含 Authorization)
- 配置方式见 `config.yaml.example.Settings`

## API 端点

### 1. 状态检查

**GET** `/api/`

检查 API 服务运行状态。

Response
```json
{
    "status": "ok",
    "version": "版本号",
    "message": "API 服务正常运行"
}
```

### 2. 触发 Alist2Strm 任务

**POST** `/api/strm/run`

手动执行 Alist2Strm 任务。

请求示例
```bash
curl --location 'http://127.0.0.1:9001/api/strm/run' \
--header 'Authorization: aabbcc112233' \
--header 'Content-Type: application/json; charset=utf-8' \
--data '{
    "task_id": "test_id"
}'
```

Body
```json
{
    "task_id": "任务ID"
}
```

Response
```json
{
    "status": "success",
    "message": "任务 {task_id} 已提交"
}
```
```json
{
    "status": "warning",
    "message": "任务 {task_id} 正在运行中，跳过本次手动执行"
}
```


### 3. 日志查询

**GET** `/api/logs`

获取日志文件列表或下载特定日志文件。

**查询参数：**
- `filename` (可选): 日志文件名(不需要.log后缀)

**响应类型：**
- 获取日志列表：不传 `filename` 则返回日志文件名列表
- 获取特定日志：根据 `filename` 返回日志文件内容

### 4. 获取任务状态

**GET** `/api/jobs`

获取 `cron` 任务和手动触发的任务。

Response
```json
{
    "cron": ["定时任务列表"],
    "all": ["正在运行的任务ID集合"]
}
```

## 说明

所有 API 请求都需要在请求头中包含有效的 API Token。认证失败将返回 401 状态码。