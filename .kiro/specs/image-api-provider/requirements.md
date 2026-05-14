# Requirements Document

## Introduction

本功能为 AI 伴侣项目新增 image-api 图片生成提供商，接入本地部署的 Images API 服务（基于 Jimeng 即梦平台），同时新增图生图（image-to-image）能力。每个用户可上传一张"底图"（AI 伴侣大头照），图生图调用时自动使用该底图作为参考，确保 AI 伴侣生成的图片保持外观一致性。若用户未上传底图，则使用系统预设的兜底图片。

## Glossary

- **Image_API_Provider**: 新增的图片生成提供商，通过 HTTP 调用本地 Images API 服务（端口 18081），支持文生图和图生图
- **Image_API_Service**: 本地部署的统一图片生成 API 服务，封装 Jimeng 等平台，提供 OpenAI 兼容格式接口
- **Base_Image**: 用户上传的底图文件，作为图生图的参考图片，用于保持 AI 伴侣外观一致性，每用户最多一张
- **Fallback_Image**: 系统预设的兜底图片，当用户未上传底图时使用
- **Image_Generation_Manager**: 现有的图像生成管理器，负责提供商选择、自动降级等逻辑
- **User_Data_Manager**: 现有的用户数据文件管理器，管理每个用户的个人数据文件夹
- **Text_To_Image**: 文生图功能，根据文本提示词生成图片
- **Image_To_Image**: 图生图功能，基于参考图片和提示词生成新图片

## Requirements

### Requirement 1: Image-API 提供商注册与配置

**User Story:** As a 系统管理员, I want to 在配置文件中添加 image-api 提供商配置, so that 系统可以通过本地 Images API 服务生成图片。

#### Acceptance Criteria

1. THE Image_Generation_Manager SHALL support "image_api" as a valid provider name for primary or fallback provider selection
2. WHEN "image_api" is specified as the provider, THE Image_Generation_Manager SHALL create an Image_API_Provider instance using the `image_api` section of the ImageGenerationConfig
3. THE Image_API_Provider configuration SHALL include the following fields with defaults: api_base ("http://127.0.0.1:18081"), api_key (empty string ""), model ("jimeng-5.0"), timeout (120 seconds), ratio ("1:1"), resolution ("2k"), and sample_strength (0.5)
4. THE Image_API_Provider SHALL accept sample_strength values in the range 0.0 to 1.0 inclusive
5. IF "image_api" is specified as the provider and the Image_API_Provider cannot be instantiated due to invalid configuration, THEN THE Image_Generation_Manager SHALL raise a ValueError indicating the configuration error

### Requirement 2: Image-API 文生图功能

**User Story:** As a 用户, I want to 通过 image-api 提供商生成图片, so that 我的 AI 伴侣可以使用 Jimeng 模型生成高质量图片。

#### Acceptance Criteria

1. WHEN a text prompt is provided, THE Image_API_Provider SHALL send a POST request to {api_base}/v1/images/generations with the configured model, prompt, ratio, resolution, and response_format parameters within the configured timeout period
2. WHEN the api_key is configured and non-empty, THE Image_API_Provider SHALL include the "x-api-key" header in the request; WHEN the api_key is empty or not configured, THE Image_API_Provider SHALL omit the "x-api-key" header
3. WHEN the Image_API_Service returns an HTTP 200 response with a data array containing a url field, THE Image_API_Provider SHALL download the image from the URL within the configured timeout and return it as JPEG binary data
4. WHEN the Image_API_Service returns an HTTP 200 response with a data array containing a b64_json field, THE Image_API_Provider SHALL decode the Base64 data and return it as JPEG binary data
5. IF the Image_API_Service returns a non-200 HTTP status code, THEN THE Image_API_Provider SHALL log the error status code and response body and return None
6. IF a network error or timeout occurs during the request or image download, THEN THE Image_API_Provider SHALL log the error details and return None

### Requirement 3: Image-API 图生图功能

**User Story:** As a 用户, I want to 使用图生图功能生成图片, so that AI 伴侣发送的图片能保持外观一致性。

#### Acceptance Criteria

1. WHEN a prompt and reference image array containing 1 to 10 images are provided, THE Image_API_Provider SHALL send a POST request to {api_base}/v1/images/compositions with model, prompt, images array, ratio (default "1:1"), resolution (default "2k"), and sample_strength (range 0.1 to 1.0, default 0.5) parameters
2. THE Image_API_Provider SHALL support reference images as HTTP/HTTPS URLs or Base64 Data URL format (data:image/{type};base64,{data})
3. WHEN the Image_API_Service returns an HTTP 200 response containing a data array with at least one element, THE Image_API_Provider SHALL download the image from the url field or decode the b64_json field and return the result as JPEG binary data
4. IF the composition request returns a non-200 HTTP status, a network timeout, or an empty data array, THEN THE Image_API_Provider SHALL log the error details and return None
5. WHEN the Image_API_Service returns an async task response with a task_id, THE Image_API_Provider SHALL poll GET {api_base}/v1/images/generations/{task_id} at a configured interval until the task status indicates success or failure, subject to the configured timeout

### Requirement 4: 用户底图管理

**User Story:** As a 用户, I want to 上传一张底图作为 AI 伴侣的大头照, so that 图生图时能保持 AI 伴侣外观一致。

#### Acceptance Criteria

1. THE User_Data_Manager SHALL support a "base_image" subdirectory within each user's data folder for storing the user's base image
2. WHEN a user uploads a base image in JPEG, PNG, or WebP format with file size not exceeding 5 MB, THE system SHALL save the image file to the user's base_image directory
3. WHEN a user uploads a new base image and one already exists, THE system SHALL replace the existing base image with the new one (maximum one base image per user)
4. IF a user uploads a file that is not in JPEG, PNG, or WebP format, THEN THE system SHALL reject the upload and return an error message indicating the unsupported format
5. WHEN a user requests to view their current base image, THE system SHALL return the base image file data along with metadata including filename, file size in bytes, image format, and last-modified timestamp
6. IF a user requests to view or delete their base image and no base image exists, THEN THE system SHALL return an indication that no base image is currently stored
7. WHEN a user requests to delete their base image, THE system SHALL remove the file from the base_image directory

### Requirement 5: 图生图底图选择逻辑

**User Story:** As a 系统, I want to 在图生图调用时自动选择合适的底图, so that 每次生成的图片都能保持 AI 伴侣外观一致。

#### Acceptance Criteria

1. WHEN image-to-image generation is triggered for a user, THE system SHALL check the user's base_image directory for an existing image file (JPEG, PNG, or WebP) and use it if found
2. WHEN the user has an uploaded base image, THE system SHALL read the image file, determine its MIME type from the file extension, and convert it to Base64 Data URL format (e.g., `data:image/<type>;base64,<encoded_data>`) for the API call
3. WHEN the user does not have an uploaded base image, THE system SHALL use the system fallback image instead
4. THE system fallback image SHALL be stored at a path specified in the application configuration file (default: backend/data/default_base_image.jpg)
5. IF neither user base image nor system fallback image exists, THEN THE system SHALL log a warning and fall back to text-to-image generation with the same prompt instead
6. IF the selected base image file exists but cannot be read or exceeds 10 MB in size, THEN THE system SHALL log a warning and fall back to text-to-image generation with the same prompt instead
7. WHEN converting the base image to Base64 Data URL, THE system SHALL complete the file read and encoding within 5 seconds, or fall back to text-to-image generation

### Requirement 6: 底图上传 API 接口

**User Story:** As a 前端开发者, I want to 有 REST API 接口管理用户底图, so that 前端可以实现底图上传和管理功能。

#### Acceptance Criteria

1. THE system SHALL provide a POST /api/image-gen/base-image/upload endpoint that accepts multipart file upload for the base image in JPEG, PNG, or WEBP format, limited to one base image per user where a new upload replaces the existing base image
2. THE system SHALL provide a GET /api/image-gen/base-image endpoint that returns the current user's base image data (Base64 encoded) and metadata including file name, file size in bytes, MIME type, and upload timestamp
3. THE system SHALL provide a DELETE /api/image-gen/base-image endpoint that removes the current user's base image
4. IF an unauthenticated request is received on any base-image endpoint, THEN THE system SHALL return a 401 status code
5. IF an upload request contains a file format other than JPEG, PNG, or WEBP, THEN THE system SHALL return a 400 status code with an error message indicating the supported formats
6. IF an upload request exceeds 5MB file size, THEN THE system SHALL return a 400 status code with an error message indicating the maximum allowed size
7. IF a GET or DELETE request is made and the current user has no base image stored, THEN THE system SHALL return a 404 status code with an error message indicating no base image exists

### Requirement 7: Jimeng 模型选择

**User Story:** As a 系统管理员, I want to 在 jimeng-4.5、jimeng-4.6、jimeng-5.0 之间选择模型, so that 可以根据需求平衡质量和成本。

#### Acceptance Criteria

1. THE Image_API_Provider configuration SHALL support model values limited to "jimeng-4.5", "jimeng-4.6", and "jimeng-5.0", with "jimeng-4.5" as the default when no model value is specified
2. WHEN the configured model is one of "jimeng-4.5", "jimeng-4.6", or "jimeng-5.0", THE Image_API_Provider SHALL include the configured model string as the `model` field in the API request sent to the Image_API_Service without transformation
3. IF the configured model value is not one of the supported values ("jimeng-4.5", "jimeng-4.6", "jimeng-5.0"), THEN THE Image_API_Provider SHALL reject the configuration and retain the previously valid model value
4. THE Image_API_Provider SHALL register providers through a provider-name-to-class mapping, so that adding a new provider requires only adding an entry to the mapping and a corresponding provider class without modifying existing provider classes

### Requirement 8: 图生图触发集成

**User Story:** As a 用户, I want to AI 伴侣在发送图片时自动使用图生图功能, so that 生成的图片能保持 AI 伴侣的外观特征。

#### Acceptance Criteria

1. WHEN image generation is triggered and the provider is "image_api" and a valid user_id is provided, THE Image_Generation_Manager SHALL retrieve the user's base image via the base image selection logic (Requirement 5) and call the image-to-image method with that base image and the prompt
2. WHEN image generation is triggered and the provider is not "image_api", THE Image_Generation_Manager SHALL continue using the existing text-to-image flow without requiring a user_id
3. WHEN the Image_Generation_Manager generate method is called, THE Image_Generation_Manager SHALL accept an optional user_id parameter; IF user_id is not provided or is None, THEN THE Image_Generation_Manager SHALL use the text-to-image flow even when the provider is "image_api"
4. IF the image-to-image call returns None or raises an exception, THEN THE Image_Generation_Manager SHALL fall back to text-to-image generation using the same provider and the same prompt before attempting the fallback_provider
5. IF both the image-to-image fallback to text-to-image and the fallback_provider fail, THEN THE Image_Generation_Manager SHALL return None

### Requirement 9: 连接测试

**User Story:** As a 系统管理员, I want to 测试 image-api 服务的连接状态, so that 可以确认服务是否正常运行。

#### Acceptance Criteria

1. WHEN a connection test is requested, THE Image_API_Provider SHALL send a GET request to {api_base}/ping with a connection timeout of 10 seconds and a total request timeout of 25 seconds
2. WHEN the ping endpoint returns HTTP status 200 with a JSON body containing {"ok": true}, THE Image_API_Provider SHALL report the connection as successful
3. IF the ping request fails due to a network error, timeout, non-200 HTTP status code, non-JSON response body, or a JSON response that does not contain the field "ok" with value true, THEN THE Image_API_Provider SHALL report the connection as failed
4. IF the api_key is configured, THEN THE Image_API_Provider SHALL include the api_key in the x-api-key request header when sending the ping request
