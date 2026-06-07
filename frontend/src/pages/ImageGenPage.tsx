import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Switch,
  Button,
  Space,
  message,
  Select,
  InputNumber,
  Typography,
  Divider,
  Alert,
  Row,
  Col,
  Image,
  Spin,
  Upload,
} from 'antd';
import { PictureOutlined, ExperimentOutlined, UploadOutlined, DeleteOutlined } from '@ant-design/icons';
import { imageGenApi } from '@/services/api';
import { imageGenConfigProxy } from '@/services/configProxy';
import { Link } from 'react-router-dom';

const { Title, Text } = Typography;

interface ModelScopeConfig {
  api_key: string;
  model: string;
  timeout: number;
}

interface YunwuConfig {
  api_key: string;
  api_base: string;
  model: string;
  timeout: number;
}

interface KlingApiConfig {
  api_base: string;
  api_key: string;
  model: string;
  timeout: number;
  size: string;
  poll_interval: number;
  transport: string;
  target_url: string;
  response_format: string;
}

interface ImageApiConfig {
  api_base: string;
  api_key: string;
  model: string;
  timeout: number;
  ratio: string;
  resolution: string;
  sample_strength: number;
  negative_prompt: string;
  intelligent_ratio: boolean;
  response_format: string;
  n: number;
  provider_options: Record<string, any>;
  provider_options_text?: string;
}

interface GptImageConfig {
  api_base: string;
  api_key: string;
  model: string;
  timeout: number;
}

interface GptImageEditsConfig {
  api_base: string;
  api_key: string;
  model: string;
  timeout: number;
  ratio: string;
  resolution: string;
  quality: string;
  background: string;
  moderation: string;
  response_format: string;
}

interface ImageGenConfig {
  enabled: boolean;
  provider: string;
  fallback_provider: string;
  enable_fallback: boolean;
  modelscope: ModelScopeConfig;
  yunwu: YunwuConfig;
  kling_api: KlingApiConfig;
  image_api: ImageApiConfig;
  gpt_image: GptImageConfig;
  gpt_image_edits: GptImageEditsConfig;
  trigger_keywords: string[];
  generating_message: string;
  error_message: string;
  success_message: string;
}

const providerOptions = [
  { value: 'modelscope', label: '魔搭社区' },
  { value: 'yunwu', label: 'yunwu.ai' },
  { value: 'kling_api', label: '本地 kling-api' },
  { value: 'image_api', label: 'Images API (图片/Seedream)' },
  { value: 'gpt_image', label: 'GPT-Image (图生图中转站)' },
  { value: 'gpt_image_edits', label: 'GPT-Image Edits (gpt-image-2)' },
];

const stringifyJsonObject = (value: any) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '';
  return JSON.stringify(value, null, 2);
};

const parseJsonObject = (value?: string) => {
  const text = String(value || '').trim();
  if (!text) return {};
  const parsed = JSON.parse(text);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('provider_options 必须是 JSON 对象');
  }
  return parsed;
};

const ImageGenPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [testImage, setTestImage] = useState<string | null>(null);
  const [config, setConfig] = useState<ImageGenConfig>({
    enabled: true,
    provider: 'modelscope',
    fallback_provider: 'yunwu',
    enable_fallback: true,
    modelscope: {
      api_key: '',
      model: 'Tongyi-MAI/Z-Image-Turbo',
      timeout: 120,
    },
    yunwu: {
      api_key: '',
      api_base: 'https://yunwu.ai/v1',
      model: 'jimeng-4.5',
      timeout: 120,
    },
    kling_api: {
      api_base: 'http://127.0.0.1:18080',
      api_key: '',
      model: 'kling-v2-1',
      timeout: 180,
      size: '1024x1024',
      poll_interval: 3,
      transport: 'web',
      target_url: 'https://klingai.com/app/image/new',
      response_format: 'url',
    },
    image_api: {
      api_base: 'http://127.0.0.1:8006',
      api_key: '',
      model: 'seedream-5.0',
      timeout: 120,
      ratio: '1:1',
      resolution: '2k',
      sample_strength: 0.5,
      negative_prompt: '',
      intelligent_ratio: false,
      response_format: 'url',
      n: 1,
      provider_options: {},
      provider_options_text: '',
    },
    gpt_image: {
      api_base: '',
      api_key: '',
      model: 'gpt-image-2',
      timeout: 180,
    },
    gpt_image_edits: {
      api_base: 'https://jeniya.top',
      api_key: '',
      model: 'gpt-image-2-all',
      timeout: 180,
      ratio: '1:1',
      resolution: '1k',
      quality: '',
      background: '',
      moderation: '',
      response_format: 'url',
    },
    trigger_keywords: ['画', '生成图片', '生图', '绘制'],
    generating_message: '🎨 正在为你生成图片，请稍候...',
    error_message: '😢 图片生成失败：{error}',
    success_message: '✨ 图片已生成完成！',
  });

  const modelscopeModels = [
    'Tongyi-MAI/Z-Image-Turbo',
    'AI-ModelScope/stable-diffusion-v1-5',
    'AI-ModelScope/stable-diffusion-xl-base-1.0',
  ];

  const yunwuModels = ['jimeng-4.5', 'stable-diffusion-xl', 'dall-e-3'];
  const klingModels = ['kling-v2-1'];
  const imageApiModels = [
    // 统一 Seedream
    'seedream-5.0', 'seedream-4.5', 'seedream-4.0',
    // Doubao（豆包）
    'doubao-seedream-5.0-lite', 'doubao-seedream-4.5', 'doubao-seedream-4.0',
    // XYQ（小云雀）
    'xyq-seedream-5.0', 'xyq-seedream-4.5', 'xyq-seedream-4.0',
    // Jimeng（即梦）
    'jimeng-5.0', 'jimeng-4.7', 'jimeng-4.6', 'jimeng-4.5', 'jimeng-4.1', 'jimeng-4.0',
    // Kling（可灵）
    'kling-v3-omni', 'kling-image-o1',
    // Qwen/Wan（通义千问）
    'wan2.7-image', 'qwen-image-2.0', 'qwen-image-1.0-pro', 'qwen-image-1.0',
  ];
  const currentProvider = Form.useWatch('provider', form) || 'modelscope';

  const [baseImage, setBaseImage] = useState<{ image_data?: string; filename?: string; file_size?: number; mime_type?: string; last_modified?: string } | null>(null);
  const [baseImageLoading, setBaseImageLoading] = useState(false);

  useEffect(() => {
    loadConfig();
    loadBaseImage();
  }, []);

  const loadBaseImage = async () => {
    try {
      setBaseImageLoading(true);
      const result = await imageGenApi.getBaseImage();
      setBaseImage(result);
    } catch (error) {
      // 404 means no image, which is fine
      setBaseImage(null);
    } finally {
      setBaseImageLoading(false);
    }
  };

  const loadConfig = async () => {
    try {
      setLoading(true);
      const data = await imageGenConfigProxy.getConfig();
      const merged = {
        ...config,
        ...(data || {}),
        image_api: {
          ...config.image_api,
          ...(data?.image_api || {}),
          provider_options_text: stringifyJsonObject(data?.image_api?.provider_options),
        },
      };
      setConfig(merged);
      form.setFieldsValue(merged);
    } catch (error) {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async (values: ImageGenConfig) => {
    try {
      setLoading(true);
      const payload: ImageGenConfig = {
        ...values,
        image_api: {
          ...values.image_api,
          provider_options: parseJsonObject(values.image_api?.provider_options_text),
        },
      };
      delete payload.image_api.provider_options_text;
      await imageGenConfigProxy.updateConfig(payload);
      message.success('配置保存成功');
      setConfig(payload);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '配置保存失败');
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    try {
      setTestLoading(true);
      const success = await imageGenApi.testImageGenConnection();
      if (success) {
        message.success('连接测试成功');
      } else {
        message.error('连接测试失败');
      }
    } catch (error) {
      message.error('连接测试失败');
    } finally {
      setTestLoading(false);
    }
  };

  const generateTestImage = async () => {
    try {
      setGenerateLoading(true);
      setTestImage(null);
      const result = await imageGenApi.generateImage('一只可爱的小猫咪在花园里玩耍');
      if (result.success && result.image_data) {
        setTestImage(`data:image/jpeg;base64,${result.image_data}`);
        message.success('测试图片生成成功');
      } else {
        message.error(`图片生成失败：${result.message}`);
      }
    } catch (error) {
      message.error('图片生成失败');
    } finally {
      setGenerateLoading(false);
    }
  };

  const handleBaseImageUpload = async (file: File) => {
    try {
      setBaseImageLoading(true);
      await imageGenApi.uploadBaseImage(file);
      message.success('底图上传成功');
      await loadBaseImage();
    } catch (error: any) {
      const detail = error.response?.data?.detail || '上传失败';
      message.error(detail);
    } finally {
      setBaseImageLoading(false);
    }
    return false; // prevent default upload behavior
  };

  const handleBaseImageDelete = async () => {
    try {
      setBaseImageLoading(true);
      await imageGenApi.deleteBaseImage();
      message.success('底图已删除');
      setBaseImage(null);
    } catch (error: any) {
      const detail = error.response?.data?.detail || '删除失败';
      message.error(detail);
    } finally {
      setBaseImageLoading(false);
    }
  };

  const renderProviderFields = () => {
    if (currentProvider === 'modelscope') {
      return (
        <>
          <Divider>魔搭社区配置</Divider>
          <Form.Item
            name={['modelscope', 'api_key']}
            label="API密钥"
            rules={[{ required: true, message: '请输入API密钥' }]}
          >
            <Input.Password placeholder="请输入魔搭社区API密钥" />
          </Form.Item>
          <Form.Item
            name={['modelscope', 'model']}
            label="模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select options={modelscopeModels.map((model) => ({ value: model, label: model }))} />
          </Form.Item>
          <Form.Item name={['modelscope', 'timeout']} label="超时时间（秒）">
            <InputNumber min={30} max={300} style={{ width: '100%' }} />
          </Form.Item>
        </>
      );
    }

    if (currentProvider === 'yunwu') {
      return (
        <>
          <Divider>yunwu.ai 配置</Divider>
          <Form.Item
            name={['yunwu', 'api_key']}
            label="API密钥"
            rules={[{ required: true, message: '请输入API密钥' }]}
          >
            <Input.Password placeholder="请输入 yunwu.ai API密钥" />
          </Form.Item>
          <Form.Item name={['yunwu', 'api_base']} label="API地址">
            <Input placeholder="https://yunwu.ai/v1" />
          </Form.Item>
          <Form.Item
            name={['yunwu', 'model']}
            label="模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select options={yunwuModels.map((model) => ({ value: model, label: model }))} />
          </Form.Item>
          <Form.Item name={['yunwu', 'timeout']} label="超时时间（秒）">
            <InputNumber min={30} max={300} style={{ width: '100%' }} />
          </Form.Item>
        </>
      );
    }

    if (currentProvider === 'image_api') {
      return (
        <>
          <Divider>Image API 配置（即梦/豆包/小云雀/可灵）</Divider>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="接入说明"
            description="连接 Images API 统一服务，支持即梦、豆包、小云雀、可灵、通义千问，以及 Seedream 统一轮询模型。通过切换模型名称选择不同平台。支持文生图和图生图。"
          />
          <Form.Item
            name={['image_api', 'api_base']}
            label="API 地址"
            rules={[{ required: true, message: '请输入 API 地址' }]}
          >
            <Input placeholder="http://127.0.0.1:8006" />
          </Form.Item>
          <Form.Item name={['image_api', 'api_key']} label="API Key">
            <Input.Password placeholder="未开启鉴权可留空" />
          </Form.Item>
          <Form.Item
            name={['image_api', 'model']}
            label="模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select
              options={imageApiModels.map((model) => {
                let label = model;
                if (model.startsWith('doubao-')) label = `🫘 ${model}`;
                else if (model.startsWith('xyq-')) label = `🐦 ${model}`;
                else if (model.startsWith('jimeng-')) label = `✨ ${model}`;
                else if (model.startsWith('kling-')) label = `🎬 ${model}`;
                else if (model.startsWith('seedream-')) label = `统一 ${model}`;
                else if (model.startsWith('qwen-') || model.startsWith('wan')) label = `千问 ${model}`;
                return { value: model, label };
              })}
            />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={['image_api', 'ratio']} label="图片比例">
                <Select
                  options={[
                    { value: '1:1', label: '1:1' },
                    { value: '16:9', label: '16:9' },
                    { value: '9:16', label: '9:16' },
                    { value: '4:3', label: '4:3' },
                    { value: '3:4', label: '3:4' },
                    { value: '3:2', label: '3:2' },
                    { value: '2:3', label: '2:3' },
                    { value: '21:9', label: '21:9' },
                    { value: 'auto', label: 'auto' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['image_api', 'resolution']} label="分辨率">
                <Select
                  options={[
                    { value: '1k', label: '1K' },
                    { value: '2k', label: '2K' },
                    { value: '4k', label: '4K' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['image_api', 'timeout']} label="超时（秒）">
                <InputNumber min={30} max={600} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name={['image_api', 'sample_strength']}
            label="图生图参考强度"
            tooltip="值越大，生成图片越接近参考底图。范围 0.0-1.0"
          >
            <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={['image_api', 'n']} label="生成数量">
                <InputNumber min={1} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['image_api', 'response_format']} label="响应格式">
                <Select
                  options={[
                    { value: 'url', label: 'url' },
                    { value: 'b64_json', label: 'b64_json' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['image_api', 'intelligent_ratio']} label="智能比例" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name={['image_api', 'negative_prompt']} label="反向提示词">
            <Input.TextArea rows={2} placeholder="不希望出现的内容，可留空" />
          </Form.Item>
          <Form.Item
            name={['image_api', 'provider_options_text']}
            label="Provider Options（JSON）"
            tooltip="透传给底层 provider 的额外参数，例如可灵网页模式 transport/target_url"
          >
            <Input.TextArea rows={4} placeholder={'{\n  "transport": "web",\n  "target_url": "https://klingai.com/app/image/new"\n}'} />
          </Form.Item>
        </>
      );
    }

    if (currentProvider === 'gpt_image') {
      return (
        <>
          <Divider>GPT-Image 中转站配置（仅图生图）</Divider>
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="仅支持图生图"
            description="此提供商通过中转站调用 gpt-4o-image 模型，仅支持图生图（需要用户上传底图）。不支持纯文生图。计费：0.04 元/张。"
          />
          <Form.Item
            name={['gpt_image', 'api_base']}
            label="中转站地址"
            rules={[{ required: true, message: '请输入中转站 API 地址' }]}
          >
            <Input placeholder="https://your-proxy.com" />
          </Form.Item>
          <Form.Item
            name={['gpt_image', 'api_key']}
            label="API Key"
            rules={[{ required: true, message: '请输入中转站 API Key' }]}
          >
            <Input.Password placeholder="Bearer Token 格式的 API Key" />
          </Form.Item>
          <Form.Item name={['gpt_image', 'model']} label="模型">
            <Select
              options={[{ value: 'gpt-image-2', label: 'gpt-image-2' }]}
            />
          </Form.Item>
          <Form.Item name={['gpt_image', 'timeout']} label="超时时间（秒）">
            <InputNumber min={30} max={600} style={{ width: '100%' }} />
          </Form.Item>
        </>
      );
    }

    if (currentProvider === 'gpt_image_edits') {
      return (
        <>
          <Divider>GPT-Image Edits 配置（gpt-image-2）</Divider>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="接入说明"
            description="调用 /v1/images/edits multipart 接口，需要上传底图。前端选择 1K/2K/4K 后，后端会按比例转换为上游 size 参数。"
          />
          <Form.Item
            name={['gpt_image_edits', 'api_base']}
            label="API 地址"
            rules={[{ required: true, message: '请输入 API 地址' }]}
          >
            <Input placeholder="https://jeniya.top" />
          </Form.Item>
          <Form.Item name={['gpt_image_edits', 'api_key']} label="API Key">
            <Input.Password placeholder="Bearer Token，可按服务配置留空" />
          </Form.Item>
          <Form.Item
            name={['gpt_image_edits', 'model']}
            label="模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select
              options={[
                { value: 'gpt-image-2-all', label: 'gpt-image-2-all' },
                { value: 'gpt-image-2', label: 'gpt-image-2' },
              ]}
            />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={['gpt_image_edits', 'ratio']} label="图片比例">
                <Select
                  options={[
                    { value: '1:1', label: '1:1' },
                    { value: '16:9', label: '16:9' },
                    { value: '9:16', label: '9:16' },
                    { value: '4:3', label: '4:3' },
                    { value: '3:4', label: '3:4' },
                    { value: '3:2', label: '3:2' },
                    { value: '2:3', label: '2:3' },
                    { value: '21:9', label: '21:9' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['gpt_image_edits', 'resolution']} label="分辨率">
                <Select
                  options={[
                    { value: '1k', label: '1K' },
                    { value: '2k', label: '2K' },
                    { value: '4k', label: '4K' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['gpt_image_edits', 'timeout']} label="超时（秒）">
                <InputNumber min={30} max={600} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={['gpt_image_edits', 'response_format']} label="响应格式">
                <Select
                  options={[
                    { value: 'url', label: 'url' },
                    { value: 'b64_json', label: 'b64_json' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['gpt_image_edits', 'background']} label="背景">
                <Select
                  allowClear
                  options={[
                    { value: '', label: '默认' },
                    { value: 'transparent', label: 'transparent' },
                    { value: 'opaque', label: 'opaque' },
                    { value: 'auto', label: 'auto' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['gpt_image_edits', 'moderation']} label="审核级别">
                <Select
                  allowClear
                  options={[
                    { value: '', label: '默认' },
                    { value: 'auto', label: 'auto' },
                    { value: 'low', label: 'low' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name={['gpt_image_edits', 'quality']} label="质量">
            <Select
              allowClear
              options={[
                { value: '', label: '默认' },
                { value: 'auto', label: 'auto' },
                { value: 'high', label: 'high' },
                { value: 'medium', label: 'medium' },
                { value: 'low', label: 'low' },
              ]}
            />
          </Form.Item>
        </>
      );
    }

    return (
      <>
        <Divider>本地 kling-api 配置</Divider>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="接入说明"
          description="这里填写 /myproject/kling-api 暴露出来的本地接口地址。若服务启用了 SERVER_API_KEYS，需要把对应 key 也填上。"
        />
        <Form.Item
          name={['kling_api', 'api_base']}
          label="API地址"
          rules={[{ required: true, message: '请输入 kling-api 地址' }]}
        >
          <Input placeholder="http://127.0.0.1:18080" />
        </Form.Item>
        <Form.Item name={['kling_api', 'api_key']} label="API Key">
          <Input.Password placeholder="未开启鉴权可留空" />
        </Form.Item>
        <Form.Item
          name={['kling_api', 'model']}
          label="模型"
          rules={[{ required: true, message: '请选择模型' }]}
        >
          <Select options={klingModels.map((model) => ({ value: model, label: model }))} />
        </Form.Item>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name={['kling_api', 'size']} label="尺寸">
              <Select
                options={[
                  { value: '1024x1024', label: '1024x1024' },
                  { value: '768x1344', label: '768x1344' },
                  { value: '1344x768', label: '1344x768' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name={['kling_api', 'timeout']} label="超时时间（秒）">
              <InputNumber min={30} max={600} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name={['kling_api', 'poll_interval']} label="轮询间隔（秒）">
              <InputNumber min={0.5} max={30} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name={['kling_api', 'transport']} label="传输模式">
              <Select options={[{ value: 'web', label: 'web' }]} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name={['kling_api', 'target_url']} label="目标页面地址">
          <Input placeholder="https://klingai.com/app/image/new" />
        </Form.Item>
        <Form.Item name={['kling_api', 'response_format']} label="响应格式">
          <Select options={[{ value: 'url', label: 'url' }, { value: 'b64_json', label: 'b64_json' }]} />
        </Form.Item>
      </>
    );
  };

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>
        <PictureOutlined /> 图像生成配置
      </Title>

      <Alert
        message="多用户提示"
        description={
          <div>
            此页面为<strong>全局</strong>图像生成配置；如需为不同用户设置不同的生图提供商/模型/密钥，请到 <Link to="/user-config">个人配置</Link> 页面配置。
          </div>
        }
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Row gutter={[24, 24]}>
        <Col span={16}>
          <Card title="基础配置" loading={loading}>
            <Form form={form} layout="vertical" initialValues={config} onFinish={saveConfig}>
              <Form.Item name="enabled" label="启用图像生成" valuePropName="checked">
                <Switch />
              </Form.Item>

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="provider" label="主提供商">
                    <Select options={providerOptions} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="enable_fallback" label="启用自动降级" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item noStyle shouldUpdate>
                {({ getFieldValue }) => (
                  <Form.Item name="fallback_provider" label="备用提供商">
                    <Select
                      options={providerOptions.filter((item) => item.value !== getFieldValue('provider'))}
                      allowClear
                      placeholder="主提供商失败时使用"
                    />
                  </Form.Item>
                )}
              </Form.Item>

              {renderProviderFields()}

              <Divider>触发配置</Divider>
              <Form.Item
                name="trigger_keywords"
                label="触发关键词"
                rules={[{ required: true, message: '请输入触发关键词' }]}
              >
                <Select mode="tags" placeholder="输入触发关键词，按回车添加" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="generating_message" label="生成中消息">
                <Input placeholder="图片生成时显示的消息" />
              </Form.Item>
              <Form.Item name="error_message" label="错误消息">
                <Input placeholder="生成失败时显示的消息" />
              </Form.Item>
              <Form.Item name="success_message" label="成功消息">
                <Input placeholder="生成成功时显示的消息" />
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    保存配置
                  </Button>
                  <Button icon={<ExperimentOutlined />} onClick={testConnection} loading={testLoading}>
                    测试连接
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </Col>

        <Col span={8}>
          {(currentProvider === 'image_api' || currentProvider === 'gpt_image' || currentProvider === 'gpt_image_edits') && (
            <Card title="AI 伴侣底图" style={{ marginBottom: '16px' }} loading={baseImageLoading}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {baseImage?.image_data ? (
                  <>
                    <Image
                      src={`data:${baseImage.mime_type || 'image/jpeg'};base64,${baseImage.image_data}`}
                      alt="底图"
                      style={{ width: '100%', borderRadius: 8 }}
                    />
                    <Text type="secondary">
                      {baseImage.filename} ({((baseImage.file_size || 0) / 1024).toFixed(1)} KB)
                    </Text>
                    <Space>
                      <Upload
                        accept=".jpg,.jpeg,.png,.webp"
                        showUploadList={false}
                        beforeUpload={handleBaseImageUpload}
                      >
                        <Button icon={<UploadOutlined />} size="small">
                          更换底图
                        </Button>
                      </Upload>
                      <Button
                        icon={<DeleteOutlined />}
                        size="small"
                        danger
                        onClick={handleBaseImageDelete}
                      >
                        删除
                      </Button>
                    </Space>
                  </>
                ) : (
                  <>
                    <Alert
                      message="未上传底图"
                      description="上传一张 AI 伴侣大头照作为底图，图生图时会自动使用该底图保持外观一致性。未上传时使用系统默认图片。"
                      type="info"
                      showIcon
                    />
                    <Upload
                      accept=".jpg,.jpeg,.png,.webp"
                      showUploadList={false}
                      beforeUpload={handleBaseImageUpload}
                    >
                      <Button icon={<UploadOutlined />} type="primary" block>
                        上传底图
                      </Button>
                    </Upload>
                    <Text type="secondary">支持 JPEG/PNG/WebP，最大 5MB</Text>
                  </>
                )}
              </Space>
            </Card>
          )}

          <Card title="测试功能">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button type="primary" onClick={generateTestImage} loading={generateLoading} block>
                生成测试图片
              </Button>

              {generateLoading && (
                <div style={{ textAlign: 'center', padding: '20px' }}>
                  <Spin size="large" />
                  <div style={{ marginTop: '10px' }}>正在生成图片，请稍候...</div>
                </div>
              )}

              {testImage && (
                <div>
                  <Text strong>测试结果：</Text>
                  <Image src={testImage} alt="测试图片" style={{ width: '100%', marginTop: '10px' }} />
                </div>
              )}
            </Space>
          </Card>

          <Card title="使用说明" style={{ marginTop: '16px' }}>
            <Alert
              message="使用方法"
              description={
                <div>
                  <p>在 QQ / 聊天端里发送包含以下关键词的消息即可触发生图：</p>
                  <ul>
                    <li>画一只可爱的小猫</li>
                    <li>生成图片：美丽的风景</li>
                    <li>帮我生图，主题是星空</li>
                    <li>绘制一座宏伟的城堡</li>
                  </ul>
                  <p>如果主提供商设为本地 kling-api，系统会转调你已经跑通的 kling 服务。</p>
                </div>
              }
              type="info"
              showIcon
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ImageGenPage;
