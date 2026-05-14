# Implementation Plan: Image-API Provider

## Overview

为 AI 伴侣项目新增 `image_api` 图片生成提供商，接入本地 Images API 服务（基于 Jimeng 即梦平台）。实现包括：配置模型、Provider 类（文生图+图生图）、用户底图管理服务、REST API 接口、Manager 集成（自动触发图生图+降级链）、连接测试。按依赖顺序：配置 → Provider → 底图服务 → API 接口 → Manager 集成。

## Tasks

- [x] 1. 配置模型与 Provider 注册基础设施
  - [x] 1.1 新增 ImageApiConfig 配置模型并集成到 ImageGenerationConfig
    - 在 `backend/image_gen/config.py` 中新增 `ImageApiConfig` Pydantic 模型，包含字段：api_base (默认 "http://127.0.0.1:18081")、api_key (默认 "")、model (默认 "jimeng-4.5")、timeout (默认 120)、ratio (默认 "1:1")、resolution (默认 "2k")、sample_strength (默认 0.5, ge=0.0, le=1.0)
    - 在 `ImageGenerationConfig` 中新增 `image_api: ImageApiConfig = ImageApiConfig()` 字段
    - 新增 `default_base_image_path: str = "backend/data/default_base_image.jpg"` 字段到 `ImageGenerationConfig`
    - _Requirements: 1.3, 1.4, 5.4, 7.1_

  - [x] 1.2 扩展 BaseImageProvider 接口，新增 generate_with_images 方法
    - 在 `backend/image_gen/base.py` 中为 `BaseImageProvider` 新增 `generate_with_images(self, prompt: str, images: List[str]) -> Optional[bytes]` 方法
    - 默认实现回退到 `self.generate(prompt)`，保持向后兼容
    - _Requirements: 3.1, 8.1_

  - [x] 1.3 重构 Manager 的 _create_provider 为字典映射注册模式
    - 在 `backend/image_gen/manager.py` 中将 `_create_provider` 的 if-else 链重构为 `PROVIDER_MAP` 字典映射
    - 映射格式：`{"modelscope": (ModelScopeProvider, "modelscope"), "yunwu": (YunwuProvider, "yunwu"), "kling_api": (KlingApiProvider, "kling_api"), "image_api": (ImageApiProvider, "image_api")}`
    - 不支持的 provider 名称抛出 ValueError
    - _Requirements: 1.1, 1.2, 1.5, 7.4_

- [x] 2. ImageApiProvider 实现
  - [x] 2.1 创建 ImageApiProvider 类骨架与模型验证
    - 新建 `backend/image_gen/providers/image_api.py`
    - 实现 `ImageApiProvider(BaseImageProvider)` 类，`__init__` 从 config dict 读取配置
    - 实现模型验证：仅接受 "jimeng-4.5"、"jimeng-4.6"、"jimeng-5.0"，无效值拒绝并保留默认值 "jimeng-4.5"
    - 在 `backend/image_gen/providers/__init__.py` 中导出 `ImageApiProvider`
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 2.2 实现文生图 generate 方法
    - 实现 `async def generate(self, prompt: str) -> Optional[bytes]`
    - 构造 POST 请求到 `{api_base}/v1/images/generations`，包含 model、prompt、ratio、resolution、response_format 字段
    - api_key 非空时添加 `x-api-key` header，为空时省略
    - 处理响应：url 字段则下载图片转 JPEG，b64_json 字段则 Base64 解码转 JPEG
    - 非 200 状态码记录日志返回 None；网络错误/超时记录日志返回 None
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.3 实现图生图 generate_with_images 方法
    - 实现 `async def generate_with_images(self, prompt: str, images: List[str]) -> Optional[bytes]`
    - 构造 POST 请求到 `{api_base}/v1/images/compositions`，包含 model、prompt、images、ratio、resolution、sample_strength 字段
    - 支持 images 为 HTTP/HTTPS URL 或 Base64 Data URL 格式
    - 处理响应同文生图（url 下载或 b64_json 解码）
    - 处理异步任务响应：若返回 task_id，轮询 GET `{api_base}/v1/images/generations/{task_id}` 直到成功或超时
    - 非 200/网络错误/空 data 数组记录日志返回 None
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 2.4 实现连接测试 test_connection 方法
    - 实现 `async def test_connection(self) -> bool`
    - 发送 GET 请求到 `{api_base}/ping`，连接超时 10 秒，总超时 25 秒
    - api_key 非空时添加 `x-api-key` header
    - 仅当 HTTP 200 且 JSON body 包含 `{"ok": true}` 时返回 True，其他情况返回 False
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 2.5 编写 ImageApiProvider 属性测试
    - **Property 1: sample_strength validation** — 验证 ImageApiConfig 仅接受 [0.0, 1.0] 范围内的值
    - **Property 2: Text-to-image request construction** — 验证 generate() 构造正确的请求结构
    - **Property 4: Non-200 status returns None** — 验证非 200 状态码返回 None
    - **Property 5: Image-to-image request construction** — 验证 generate_with_images() 构造正确的请求结构
    - **Property 11: Model validation and pass-through** — 验证模型值验证与透传
    - **Property 14: Connection test failure detection** — 验证连接测试失败检测
    - **Validates: Requirements 1.4, 2.1, 2.5, 3.1, 7.1, 7.2, 7.3, 9.3**

  - [ ]* 2.6 编写 ImageApiProvider 单元测试
    - 测试 api_key 为空时不发送 x-api-key header (Req 2.2)
    - 测试 api_key 非空时发送 x-api-key header (Req 2.2)
    - 测试异步任务轮询流程 (Req 3.5)
    - 测试网络超时返回 None (Req 2.6)
    - 测试连接成功场景 (Req 9.1, 9.2)
    - _Requirements: 2.2, 2.6, 3.5, 9.1, 9.2_

- [x] 3. Checkpoint - 确认 Provider 实现
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. BaseImageService 底图管理服务
  - [x] 4.1 创建 BaseImageService 类
    - 新建 `backend/image_gen/base_image_service.py`
    - 实现 `BaseImageService` 类，依赖 `UserDataManager` 实例和 `fallback_image_path` 配置
    - 定义常量：ALLOWED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}，MAX_FILE_SIZE = 5MB，MAX_READ_SIZE = 10MB，READ_TIMEOUT = 5.0s，BASE_IMAGE_DIR = "base_image"
    - _Requirements: 4.1_

  - [x] 4.2 实现底图上传功能
    - 实现 `async def upload_base_image(self, username: str, file_data: bytes, filename: str) -> Dict`
    - 验证文件格式（仅 JPEG/PNG/WebP）和大小（≤5MB）
    - 确保 `base_image` 子目录存在，清除已有文件后保存新文件（每用户最多一张）
    - 返回成功信息含 filename、file_size、mime_type
    - _Requirements: 4.2, 4.3, 4.4_

  - [x] 4.3 实现底图查看与删除功能
    - 实现 `async def get_base_image(self, username: str) -> Optional[Dict]`：返回 Base64 编码图片数据 + 元数据（filename, file_size, mime_type, last_modified）
    - 实现 `async def delete_base_image(self, username: str) -> bool`：删除底图文件
    - 无底图时返回 None / False
    - _Requirements: 4.5, 4.6, 4.7_

  - [x] 4.4 实现底图选择与 Data URL 转换逻辑
    - 实现 `async def get_base_image_data_url(self, username: str) -> Optional[str]`：读取用户底图，转为 `data:image/{type};base64,{data}` 格式
    - 实现 `async def get_effective_base_image_data_url(self, username: str) -> Optional[str]`：优先用户底图，无则用 fallback 图片，都无则返回 None
    - 文件不可读或超过 10MB 时返回 None 并记录警告
    - 编码超时 5 秒时返回 None 并记录警告
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 4.5 编写 BaseImageService 属性测试
    - **Property 6: Base image upload-view round trip** — 验证上传后查看返回相同数据和正确元数据
    - **Property 7: Base image replacement** — 验证多次上传后仅保留最新文件
    - **Property 8: Format validation rejects unsupported formats** — 验证非法格式被拒绝
    - **Property 9: Base image deletion removes file** — 验证删除后目录为空
    - **Property 10: Base image selection and data URL conversion** — 验证 Data URL 格式正确
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.7, 5.1, 5.2**

  - [ ]* 4.6 编写 BaseImageService 单元测试
    - 测试 base_image 目录自动创建 (Req 4.1)
    - 测试无底图时返回 None (Req 4.6)
    - 测试 fallback 图片使用 (Req 5.3)
    - 测试 fallback 图片不存在时返回 None (Req 5.5)
    - 测试文件不可读/超大时回退 (Req 5.6)
    - _Requirements: 4.1, 4.6, 5.3, 5.5, 5.6_

- [x] 5. Checkpoint - 确认底图服务实现
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. REST API 接口实现
  - [x] 6.1 实现底图上传 API 端点
    - 在 `backend/api/image_gen.py` 中新增 `POST /api/image-gen/base-image/upload` 端点
    - 接受 multipart 文件上传，需要用户认证
    - 验证文件格式（JPEG/PNG/WebP）和大小（≤5MB）
    - 调用 `BaseImageService.upload_base_image`
    - 未认证返回 401，格式错误返回 400，大小超限返回 400
    - _Requirements: 6.1, 6.4, 6.5, 6.6_

  - [x] 6.2 实现底图查看和删除 API 端点
    - 新增 `GET /api/image-gen/base-image` 端点：返回 Base64 编码图片 + 元数据（filename, file_size, mime_type, last_modified）
    - 新增 `DELETE /api/image-gen/base-image` 端点：删除用户底图
    - 未认证返回 401，无底图返回 404
    - 定义 `BaseImageUploadResponse` 和 `BaseImageGetResponse` Pydantic 响应模型
    - _Requirements: 6.2, 6.3, 6.4, 6.7_

  - [ ]* 6.3 编写 API 端点单元测试
    - 测试各端点认证检查 (Req 6.4)
    - 测试上传格式验证 (Req 6.5)
    - 测试上传大小限制 (Req 6.6)
    - 测试无底图时 404 响应 (Req 6.7)
    - _Requirements: 6.4, 6.5, 6.6, 6.7_

- [x] 7. ImageGenerationManager 集成
  - [x] 7.1 修改 generate_image 方法支持图生图自动触发
    - 修改 `backend/image_gen/manager.py` 中 `generate_image` 方法签名，新增可选 `user_id: Optional[str] = None` 参数
    - 当 provider 为 "image_api" 且 user_id 有效时：通过 BaseImageService 获取底图 Data URL，调用 `generate_with_images`
    - 当 provider 非 "image_api" 或 user_id 为 None 时：使用现有文生图流程
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 7.2 实现图生图失败降级链
    - I2I 失败（返回 None 或异常）→ 同 provider 文生图 → fallback_provider 文生图 → 返回 None
    - 确保降级链完整：I2I → T2I (same provider) → fallback provider → None
    - _Requirements: 8.4, 8.5_

  - [x] 7.3 初始化 BaseImageService 并注入 Manager
    - 在 Manager `__init__` 中创建 `BaseImageService` 实例（需要 `UserDataManager` 和 `default_base_image_path`）
    - 确保 `Bot` 类或应用启动时正确传递依赖
    - _Requirements: 5.1, 8.1_

  - [ ]* 7.4 编写 Manager 集成属性测试
    - **Property 12: Image-to-image auto-trigger with base image** — 验证有底图时自动调用 generate_with_images
    - **Property 13: I2I failure falls back to T2I** — 验证 I2I 失败后回退到 T2I
    - **Validates: Requirements 8.1, 8.4**

  - [ ]* 7.5 编写 Manager 集成单元测试
    - 测试 provider 注册映射 (Req 1.1, 1.2)
    - 测试无 user_id 时走 T2I 流程 (Req 8.3)
    - 测试所有 provider 失败返回 None (Req 8.5)
    - 测试底图不存在时回退到 T2I (Req 5.5)
    - _Requirements: 1.1, 1.2, 5.5, 8.3, 8.5_

- [x] 8. Checkpoint - 确认集成完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 配置文件与最终集成
  - [x] 9.1 更新 config.yaml 和 config.example.yaml
    - 在 `config.yaml` 和 `config.example.yaml` 的 `image_generation` 部分新增 `image_api` 配置块
    - 新增 `default_base_image_path` 配置项
    - 确保配置示例包含所有字段及注释说明
    - _Requirements: 1.3, 5.4, 7.1_

  - [x] 9.2 放置默认兜底图片文件
    - 在 `backend/data/` 目录放置 `default_base_image.jpg` 占位文件
    - _Requirements: 5.4_

  - [x] 9.3 端到端集成验证
    - 确保 `Bot.generate_image` 正确传递 `user_id` 到 Manager
    - 确保 API `/api/image-gen/generate` 端点传递 `user_id`（已有逻辑）
    - 验证完整调用链：API → Bot → Manager → Provider → Images API Service
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 9.4 编写端到端集成测试
    - 测试：上传底图 → 触发生成 → 验证 I2I 调用使用正确 Data URL
    - 测试：配置更新 → Manager 重新初始化 provider
    - 测试：主 provider 失败 → fallback provider 被调用
    - _Requirements: 8.1, 8.4, 8.5_

- [x] 10. Final Checkpoint - 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- 所有代码使用 Python，测试框架使用 pytest + hypothesis
- Provider 实现参考现有 `YunwuProvider` 的 aiohttp 模式
- 底图服务复用现有 `UserDataManager` 的目录管理能力

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "4.1"] },
    { "id": 3, "tasks": ["2.5", "2.6", "4.2", "4.3"] },
    { "id": 4, "tasks": ["4.4", "6.1"] },
    { "id": 5, "tasks": ["4.5", "4.6", "6.2"] },
    { "id": 6, "tasks": ["6.3", "7.1", "7.3"] },
    { "id": 7, "tasks": ["7.2"] },
    { "id": 8, "tasks": ["7.4", "7.5", "9.1", "9.2"] },
    { "id": 9, "tasks": ["9.3"] },
    { "id": 10, "tasks": ["9.4"] }
  ]
}
```
