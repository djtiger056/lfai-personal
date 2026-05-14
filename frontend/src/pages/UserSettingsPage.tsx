import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Form, 
  Input, 
  InputNumber, 
  Switch, 
  Button, 
  message, 
  Tabs, 
  Space,
  Select,
  Alert,
  Popconfirm,
  Spin,
  Tag,
  Tooltip,
  Divider,
  Row,
  Col,
} from 'antd';
import { 
  SaveOutlined, 
  ExperimentOutlined, 
  ReloadOutlined,
  InfoCircleOutlined,
  DeleteOutlined,
  QqOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { userConfigApi, configApi, authApi } from '@/services/api';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';

const { Option } = Select;
const { TextArea } = Input;

/**
 * QQ 绑定区域组件
 */
const QQBindSection: React.FC<{ user: any; onSuccess: () => void }> = ({ user, onSuccess }) => {
  const [qqId, setQqId] = useState('');
  const [binding, setBinding] = useState(false);
  const { refreshUser } = useAuth();

  const handleBind = async () => {
    if (!qqId.trim()) {
      message.warning('请输入 QQ 号');
      return;
    }
    if (!/^\d{5,12}$/.test(qqId.trim())) {
      message.warning('请输入有效的 QQ 号（5-12位数字）');
      return;
    }
    setBinding(true);
    try {
      await authApi.bindQQ(qqId.trim());
      message.success('QQ 号绑定成功');
      setQqId('');
      await refreshUser();
      onSuccess();
    } catch (error: any) {
      const detail = error.response?.data?.detail || error.message;
      message.error('绑定失败: ' + detail);
    } finally {
      setBinding(false);
    }
  };

  return (
    <>
      <Alert
        message="QQ 号绑定"
        description="绑定 QQ 号后，通过 QQ 聊天时系统能识别你的身份，自动使用你上传的底图进行图生图。"
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      {user?.qq_user_id ? (
        <div style={{ marginBottom: 16 }}>
          <Space>
            <QqOutlined style={{ fontSize: 20, color: '#1890ff' }} />
            <span>当前绑定的 QQ 号：</span>
            <Tag color="blue" style={{ fontSize: 14 }}>{user.qq_user_id}</Tag>
          </Space>
        </div>
      ) : (
        <div style={{ marginBottom: 16 }}>
          <Space>
            <QqOutlined style={{ fontSize: 20, color: '#999' }} />
            <span style={{ color: '#999' }}>尚未绑定 QQ 号</span>
          </Space>
        </div>
      )}

      <Form.Item label="绑定新的 QQ 号" help="输入你的 QQ 号并点击绑定，每个 QQ 号只能绑定一个账号">
        <Space>
          <Input
            placeholder="输入 QQ 号"
            value={qqId}
            onChange={(e) => setQqId(e.target.value)}
            style={{ width: 200 }}
            prefix={<QqOutlined />}
            onPressEnter={handleBind}
          />
          <Button
            type="primary"
            icon={<LinkOutlined />}
            onClick={handleBind}
            loading={binding}
          >
            绑定
          </Button>
        </Space>
      </Form.Item>
    </>
  );
};

/**
 * Linyu 绑定区域组件
 */
const LinyuBindSection: React.FC<{ user: any; onSuccess: () => void }> = ({ user, onSuccess }) => {
  const [linyuId, setLinyuId] = useState('');
  const [binding, setBinding] = useState(false);
  const { refreshUser } = useAuth();

  const handleBind = async () => {
    if (!linyuId.trim()) {
      message.warning('请输入 Linyu 账号');
      return;
    }
    setBinding(true);
    try {
      await authApi.bindLinyu(linyuId.trim());
      message.success('Linyu 账号绑定成功');
      setLinyuId('');
      await refreshUser();
      onSuccess();
    } catch (error: any) {
      const detail = error.response?.data?.detail || error.message;
      message.error('绑定失败: ' + detail);
    } finally {
      setBinding(false);
    }
  };

  return (
    <>
      <Alert
        message="Linyu 账号绑定"
        description="绑定 Linyu 账号后，通过 Linyu 聊天时系统能识别你的身份，使用你的个性化配置与 AI 对话。你可以输入 Linyu 账号名或用户 ID。"
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      {user?.linyu_user_id ? (
        <div style={{ marginBottom: 16 }}>
          <Space>
            <LinkOutlined style={{ fontSize: 20, color: '#722ed1' }} />
            <span>当前绑定的 Linyu 账号：</span>
            <Tag color="purple" style={{ fontSize: 14 }}>{user.linyu_account || user.linyu_user_id}</Tag>
          </Space>
        </div>
      ) : (
        <div style={{ marginBottom: 16 }}>
          <Space>
            <LinkOutlined style={{ fontSize: 20, color: '#999' }} />
            <span style={{ color: '#999' }}>尚未绑定 Linyu 账号</span>
          </Space>
        </div>
      )}

      <Form.Item label="绑定 Linyu 账号" help="输入你的 Linyu 账号名或用户 ID，系统会自动解析。每个 Linyu 账号只能绑定一个用户">
        <Space>
          <Input
            placeholder="输入 Linyu 账号名或用户 ID"
            value={linyuId}
            onChange={(e) => setLinyuId(e.target.value)}
            style={{ width: 240 }}
            prefix={<LinkOutlined />}
            onPressEnter={handleBind}
          />
          <Button
            type="primary"
            icon={<LinkOutlined />}
            onClick={handleBind}
            loading={binding}
          >
            绑定
          </Button>
        </Space>
      </Form.Item>
    </>
  );
};

/**
 * 用户个人设置页面
 * 用户可以在这里配置自己的个性化设置，覆盖全局默认配置
 */
const UserSettingsPage: React.FC = () => {
  const [form] = Form.useForm();
  const [adapterForm] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingAdapters, setSavingAdapters] = useState(false);
  const [testing, setTesting] = useState(false);
  const [userConfig, setUserConfig] = useState<any>(null);
  const [globalConfig, setGlobalConfig] = useState<any>(null);
  const { user, isAdmin } = useAuth();

  useEffect(() => {
    loadConfigs();
  }, []);

  const loadConfigs = async () => {
    setLoading(true);
    try {
      // 并行加载用户配置和全局配置
      const [userCfg, globalCfg] = await Promise.all([
        userConfigApi.getConfig(),
        configApi.getConfig(),
      ]);
      
      setUserConfig(userCfg);
      setGlobalConfig(globalCfg);
      
      // 设置表单值（用户配置优先，否则显示全局配置作为占位符）
      form.setFieldsValue({
        system_prompt: userCfg.system_prompt || '',
        llm: userCfg.llm || {},
        tts: userCfg.tts || {},
      });

      // 管理员：加载适配器配置到 adapterForm
      if (globalCfg?.adapters) {
        adapterForm.setFieldsValue(globalCfg);
      }
    } catch (error: any) {
      message.error('加载配置失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const values = form.getFieldsValue();
      
      // 构建更新数据，只包含用户实际填写的字段
      const updateData: any = {};
      
      if (values.system_prompt) {
        updateData.system_prompt = values.system_prompt;
      }
      
      if (values.llm && Object.keys(values.llm).some(k => values.llm[k])) {
        updateData.llm = values.llm;
      }
      
      if (values.tts && Object.keys(values.tts).some(k => values.tts[k])) {
        updateData.tts = values.tts;
      }
      
      await userConfigApi.updateConfig(updateData);
      message.success('配置保存成功');
      loadConfigs();
    } catch (error: any) {
      message.error('保存失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async (configType?: string) => {
    try {
      await userConfigApi.resetConfig(configType);
      message.success(configType ? `${configType} 配置已重置` : '所有配置已重置');
      loadConfigs();
    } catch (error: any) {
      message.error('重置失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleSaveAdapters = async () => {
    setSavingAdapters(true);
    try {
      const formValues = adapterForm.getFieldsValue();
      const deepMerge = (target: any, source: any): any => {
        const result = { ...target };
        for (const key of Object.keys(source ?? {})) {
          if (source[key] !== null && typeof source[key] === 'object' && !Array.isArray(source[key])) {
            result[key] = deepMerge(target?.[key] ?? {}, source[key]);
          } else if (source[key] !== undefined) {
            result[key] = source[key];
          }
        }
        return result;
      };
      const payload = {
        adapters: deepMerge(globalConfig?.adapters ?? {}, formValues.adapters),
      };
      await axios.post('/api/config', payload);
      message.success('适配器配置保存成功，重启后端后生效');
      loadConfigs();
    } catch (error: any) {
      message.error('保存失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSavingAdapters(false);
    }
  };

  const handleTestLLM = async () => {
    setTesting(true);
    try {
      const success = await configApi.testLLMConnection();
      if (success) {
        message.success('LLM 连接测试成功');
      } else {
        message.error('LLM 连接测试失败');
      }
    } catch (error) {
      message.error('LLM 连接测试失败');
    } finally {
      setTesting(false);
    }
  };

  const llmProviders = [
    { value: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1' },
    { value: 'siliconflow', label: 'SiliconFlow', baseUrl: 'https://api.siliconflow.cn/v1' },
    { value: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1' },
    { value: 'yunwu', label: 'Yunwu', baseUrl: 'https://yunwu.ai/v1' },
    { value: 'qwen', label: '千问（DashScope）', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  ];

  const handleProviderChange = (provider: string) => {
    const selectedProvider = llmProviders.find(p => p.value === provider);
    if (selectedProvider) {
      form.setFieldsValue({
        llm: {
          ...form.getFieldValue('llm'),
          api_base: selectedProvider.baseUrl,
        },
      });
    }
  };

  // 渲染全局默认值提示
  const renderGlobalDefault = (path: string[], label: string) => {
    let value = globalConfig;
    for (const key of path) {
      value = value?.[key];
    }
    if (value !== undefined && value !== null && value !== '') {
      return (
        <Tooltip title={`全局默认值: ${typeof value === 'object' ? JSON.stringify(value) : value}`}>
          <Tag color="blue" style={{ marginLeft: 8 }}>
            <InfoCircleOutlined /> 有默认值
          </Tag>
        </Tooltip>
      );
    }
    return null;
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px' }}>
        <Spin size="large" tip="加载配置中..." />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px' }}>
      <Card
        title={`我的设置 - ${user?.nickname || user?.username}`}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadConfigs}>
              刷新
            </Button>
            <Popconfirm
              title="确定要重置所有配置吗？"
              description="重置后将使用系统默认配置"
              onConfirm={() => handleReset()}
              okText="确定"
              cancelText="取消"
            >
              <Button icon={<DeleteOutlined />} danger>
                重置全部
              </Button>
            </Popconfirm>
            <Button
              icon={<ExperimentOutlined />}
              onClick={handleTestLLM}
              loading={testing}
            >
              测试 LLM
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSave}
              loading={saving}
            >
              保存配置
            </Button>
          </Space>
        }
      >
        <Alert
          message="个人配置说明"
          description="在这里配置的内容会覆盖系统默认配置。如果某项留空，则使用系统默认值。点击「重置」可以恢复使用默认配置。"
          type="info"
          showIcon
          style={{ marginBottom: 24 }}
        />

        <Form form={form} layout="vertical">
          <Tabs
            defaultActiveKey="llm"
            items={[
              {
                key: 'llm',
                label: (
                  <span>
                    LLM 配置
                    {userConfig?.llm && Object.keys(userConfig.llm).length > 0 && (
                      <Tag color="green" style={{ marginLeft: 8 }}>已自定义</Tag>
                    )}
                  </span>
                ),
                children: (
                  <>
                    <Form.Item
                      label={
                        <span>
                          LLM 提供商
                          {renderGlobalDefault(['llm', 'provider'], 'LLM 提供商')}
                        </span>
                      }
                      name={['llm', 'provider']}
                    >
                      <Select
                        placeholder={`使用默认: ${globalConfig?.llm?.provider || '未设置'}`}
                        allowClear
                        onChange={handleProviderChange}
                      >
                        {llmProviders.map(provider => (
                          <Option key={provider.value} value={provider.value}>
                            {provider.label}
                          </Option>
                        ))}
                      </Select>
                    </Form.Item>

                    <Form.Item
                      label={
                        <span>
                          模型名称
                          {renderGlobalDefault(['llm', 'model'], '模型')}
                        </span>
                      }
                      name={['llm', 'model']}
                    >
                      <Input placeholder={`使用默认: ${globalConfig?.llm?.model || '未设置'}`} allowClear />
                    </Form.Item>

                    <Form.Item
                      label={
                        <span>
                          API 地址
                          {renderGlobalDefault(['llm', 'api_base'], 'API 地址')}
                        </span>
                      }
                      name={['llm', 'api_base']}
                    >
                      <Input placeholder={`使用默认: ${globalConfig?.llm?.api_base || '未设置'}`} allowClear />
                    </Form.Item>

                    <Form.Item
                      label={
                        <span>
                          API Key
                          {renderGlobalDefault(['llm', 'api_key'], 'API Key')}
                        </span>
                      }
                      name={['llm', 'api_key']}
                    >
                      <Input.Password placeholder="留空使用默认 API Key" allowClear />
                    </Form.Item>

                    <Form.Item
                      label="Temperature"
                      name={['llm', 'temperature']}
                    >
                      <InputNumber
                        min={0}
                        max={2}
                        step={0.1}
                        placeholder={`默认: ${globalConfig?.llm?.temperature || 0.7}`}
                        style={{ width: '100%' }}
                      />
                    </Form.Item>

                    <Form.Item
                      label="Max Tokens"
                      name={['llm', 'max_tokens']}
                    >
                      <InputNumber
                        min={1}
                        max={128000}
                        placeholder={`默认: ${globalConfig?.llm?.max_tokens || 2000}`}
                        style={{ width: '100%' }}
                      />
                    </Form.Item>

                    <Popconfirm
                      title="确定要重置 LLM 配置吗？"
                      onConfirm={() => handleReset('llm')}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button type="link" danger>
                        重置 LLM 配置
                      </Button>
                    </Popconfirm>
                  </>
                ),
              },
              {
                key: 'prompt',
                label: (
                  <span>
                    系统提示词
                    {userConfig?.system_prompt && (
                      <Tag color="green" style={{ marginLeft: 8 }}>已自定义</Tag>
                    )}
                  </span>
                ),
                children: (
                  <>
                    <Form.Item
                      label="我的系统提示词"
                      name="system_prompt"
                      help="定义 AI 的角色和行为方式。留空则使用系统默认提示词。"
                    >
                      <TextArea
                        rows={12}
                        placeholder={globalConfig?.system_prompt ? `默认提示词:\n${globalConfig.system_prompt.substring(0, 200)}...` : '输入你的自定义系统提示词'}
                        allowClear
                      />
                    </Form.Item>

                    {globalConfig?.system_prompt && (
                      <Alert
                        message="当前默认系统提示词"
                        description={
                          <pre style={{ whiteSpace: 'pre-wrap', maxHeight: '200px', overflow: 'auto' }}>
                            {globalConfig.system_prompt}
                          </pre>
                        }
                        type="info"
                        style={{ marginTop: 16 }}
                      />
                    )}

                    <Popconfirm
                      title="确定要重置系统提示词吗？"
                      onConfirm={() => handleReset('system_prompt')}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button type="link" danger style={{ marginTop: 16 }}>
                        重置系统提示词
                      </Button>
                    </Popconfirm>
                  </>
                ),
              },
              {
                key: 'tts',
                label: (
                  <span>
                    TTS 配置
                    {userConfig?.tts && Object.keys(userConfig.tts).length > 0 && (
                      <Tag color="green" style={{ marginLeft: 8 }}>已自定义</Tag>
                    )}
                  </span>
                ),
                children: (
                  <>
                    <Form.Item
                      label="启用 TTS"
                      name={['tts', 'enabled']}
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>

                    <Form.Item
                      label="TTS 提供商"
                      name={['tts', 'provider']}
                    >
                      <Select
                        placeholder={`使用默认: ${globalConfig?.tts?.provider || '未设置'}`}
                        allowClear
                      >
                        <Option value="edge">Edge TTS (免费)</Option>
                        <Option value="azure">Azure TTS</Option>
                        <Option value="openai">OpenAI TTS</Option>
                        <Option value="fish">Fish Audio</Option>
                        <Option value="qwen">通义千问 TTS</Option>
                      </Select>
                    </Form.Item>

                    <Alert
                      message="提示"
                      description="更多 TTS 配置（如音色、语速等）请前往 TTS 配置页面设置"
                      type="info"
                      showIcon
                      style={{ marginTop: 16 }}
                    />

                    <Popconfirm
                      title="确定要重置 TTS 配置吗？"
                      onConfirm={() => handleReset('tts')}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button type="link" danger style={{ marginTop: 16 }}>
                        重置 TTS 配置
                      </Button>
                    </Popconfirm>
                  </>
                ),
              },
              {
                key: 'account',
                label: (
                  <span>
                    <LinkOutlined /> 账号绑定
                    {(user?.qq_user_id || user?.linyu_user_id) && (
                      <Tag color="green" style={{ marginLeft: 8 }}>已绑定</Tag>
                    )}
                  </span>
                ),
                children: (
                  <>
                    <QQBindSection user={user} onSuccess={loadConfigs} />
                    <Divider />
                    <LinyuBindSection user={user} onSuccess={loadConfigs} />
                  </>
                ),
              },
              // 适配器配置 Tab（仅管理员可见）
              ...(isAdmin ? [{
                key: 'adapters',
                label: <span>🔌 适配器配置 <Tag color="orange">管理员</Tag></span>,
                children: (
                  <Form form={adapterForm} layout="vertical">
                    <Alert
                      message="适配器说明"
                      description="适配器决定机器人通过哪些渠道收发消息。修改后需重启后端服务才能生效。可同时启用多个适配器。"
                      type="info"
                      showIcon
                      style={{ marginBottom: 20 }}
                    />

                    {/* 控制台适配器 */}
                    <Card
                      size="small"
                      style={{ marginBottom: 16, borderRadius: 8 }}
                      title={<Space>🖥️ 控制台适配器 <Tag color="default">调试用</Tag></Space>}
                      extra={
                        <Form.Item name={['adapters', 'console', 'enabled']} valuePropName="checked" noStyle>
                          <Switch checkedChildren="已启用" unCheckedChildren="已禁用" />
                        </Form.Item>
                      }
                    >
                      <span style={{ color: '#888', fontSize: 13 }}>
                        在后端终端中直接输入消息与机器人对话，适合本地调试，无需额外配置。
                      </span>
                    </Card>

                    {/* QQ 适配器 */}
                    <Card
                      size="small"
                      style={{ marginBottom: 16, borderRadius: 8 }}
                      title={<Space>🐧 QQ 适配器 <Tag color="blue">NapCat / OneBot</Tag></Space>}
                      extra={
                        <Form.Item name={['adapters', 'qq', 'enabled']} valuePropName="checked" noStyle>
                          <Switch checkedChildren="已启用" unCheckedChildren="已禁用" />
                        </Form.Item>
                      }
                    >
                      <Form.Item noStyle shouldUpdate={(p: any, c: any) =>
                        p?.adapters?.qq?.enabled !== c?.adapters?.qq?.enabled
                      }>
                        {({ getFieldValue }: any) => getFieldValue(['adapters', 'qq', 'enabled']) ? (
                          <>
                            <Divider orientation="left" plain style={{ marginTop: 8 }}>连接配置</Divider>
                            <Row gutter={16}>
                              <Col span={16}>
                                <Form.Item name={['adapters', 'qq', 'ws_host']} label="WebSocket 地址" help="NapCat 监听地址">
                                  <Input placeholder="127.0.0.1" />
                                </Form.Item>
                              </Col>
                              <Col span={8}>
                                <Form.Item name={['adapters', 'qq', 'ws_port']} label="端口">
                                  <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="3001" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Form.Item name={['adapters', 'qq', 'access_token']} label="访问令牌（可选）">
                              <Input.Password placeholder="留空表示不使用认证" />
                            </Form.Item>
                            <Form.Item
                              name={['adapters', 'qq', 'need_at']}
                              label="群聊需要 @ 机器人"
                              valuePropName="checked"
                              help="开启后群聊中必须 @ 机器人才会回复"
                            >
                              <Switch checkedChildren="需要" unCheckedChildren="不需要" />
                            </Form.Item>
                            <Divider orientation="left" plain>分段发送</Divider>
                            <Form.Item
                              name={['adapters', 'qq', 'segment_config', 'enabled']}
                              label="启用分段发送"
                              valuePropName="checked"
                              help="将长消息拆分多段发送，模拟真人打字节奏"
                            >
                              <Switch checkedChildren="启用" unCheckedChildren="禁用" />
                            </Form.Item>
                            <Row gutter={16}>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'qq', 'segment_config', 'max_segment_length']} label="每段最大长度">
                                  <InputNumber min={10} max={500} step={10} style={{ width: '100%' }} placeholder="100" />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'qq', 'segment_config', 'min_segment_length']} label="每段最小长度">
                                  <InputNumber min={1} max={100} style={{ width: '100%' }} placeholder="5" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Form.Item label="段间延迟范围（秒）" help="每段之间的随机等待时间">
                              <Row gutter={16}>
                                <Col span={12}>
                                  <Form.Item name={['adapters', 'qq', 'segment_config', 'delay_range', 0]} noStyle>
                                    <InputNumber min={0.1} max={30} step={0.5} style={{ width: '100%' }} placeholder="最小 0.5" />
                                  </Form.Item>
                                </Col>
                                <Col span={12}>
                                  <Form.Item name={['adapters', 'qq', 'segment_config', 'delay_range', 1]} noStyle>
                                    <InputNumber min={0.1} max={30} step={0.5} style={{ width: '100%' }} placeholder="最大 2.0" />
                                  </Form.Item>
                                </Col>
                              </Row>
                            </Form.Item>
                            <Row gutter={16}>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'qq', 'segment_config', 'strategy']} label="分割策略">
                                  <Select>
                                    <Option value="sentence">按句子分段（更自然）</Option>
                                    <Option value="length">按长度分段（更均匀）</Option>
                                  </Select>
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'qq', 'segment_config', 'min_sentences_to_split']} label="最小句子数阈值">
                                  <InputNumber min={1} max={10} style={{ width: '100%' }} placeholder="2" />
                                </Form.Item>
                              </Col>
                            </Row>
                          </>
                        ) : (
                          <span style={{ color: '#aaa', fontSize: 13 }}>启用后展开详细配置</span>
                        )}
                      </Form.Item>
                    </Card>

                    {/* Linyu 适配器 */}
                    <Card
                      size="small"
                      style={{ marginBottom: 16, borderRadius: 8 }}
                      title={<Space>💬 Linyu 适配器 <Tag color="purple">Linyu IM</Tag></Space>}
                      extra={
                        <Form.Item name={['adapters', 'linyu', 'enabled']} valuePropName="checked" noStyle>
                          <Switch checkedChildren="已启用" unCheckedChildren="已禁用" />
                        </Form.Item>
                      }
                    >
                      <Form.Item noStyle shouldUpdate={(p: any, c: any) =>
                        p?.adapters?.linyu?.enabled !== c?.adapters?.linyu?.enabled
                      }>
                        {({ getFieldValue }: any) => getFieldValue(['adapters', 'linyu', 'enabled']) ? (
                          <>
                            <Divider orientation="left" plain style={{ marginTop: 8 }}>账号配置</Divider>
                            <Row gutter={16}>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'account']} label="账号">
                                  <Input placeholder="Linyu 登录账号" />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'password']} label="密码">
                                  <Input.Password placeholder="Linyu 登录密码" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Divider orientation="left" plain>服务器地址</Divider>
                            <Row gutter={16}>
                              <Col span={14}>
                                <Form.Item name={['adapters', 'linyu', 'http_host']} label="HTTP 地址" help="Linyu 服务器 IP 或域名">
                                  <Input placeholder="127.0.0.1" />
                                </Form.Item>
                              </Col>
                              <Col span={10}>
                                <Form.Item name={['adapters', 'linyu', 'http_port']} label="HTTP 端口">
                                  <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="9200" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Row gutter={16}>
                              <Col span={14}>
                                <Form.Item name={['adapters', 'linyu', 'ws_host']} label="WebSocket 地址">
                                  <Input placeholder="127.0.0.1" />
                                </Form.Item>
                              </Col>
                              <Col span={10}>
                                <Form.Item name={['adapters', 'linyu', 'ws_port']} label="WebSocket 端口">
                                  <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="9100" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Divider orientation="left" plain>目标用户</Divider>
                            <Row gutter={16}>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'target_user_id']} label="目标用户 ID" help="留空则不限制">
                                  <Input placeholder="指定聊天对象的用户 ID" />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'target_user_account']} label="目标用户账号">
                                  <Input placeholder="指定聊天对象的账号" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Form.Item
                              name={['adapters', 'linyu', 'auto_bind_first_user']}
                              label="自动绑定首个用户"
                              valuePropName="checked"
                              help="首次收到消息时自动将发送者设为目标用户"
                            >
                              <Switch checkedChildren="启用" unCheckedChildren="禁用" />
                            </Form.Item>
                            <Divider orientation="left" plain>分段发送</Divider>
                            <Form.Item
                              name={['adapters', 'linyu', 'segment_config', 'enabled']}
                              label="启用分段发送"
                              valuePropName="checked"
                            >
                              <Switch checkedChildren="启用" unCheckedChildren="禁用" />
                            </Form.Item>
                            <Row gutter={16}>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'segment_config', 'max_segment_length']} label="每段最大长度">
                                  <InputNumber min={10} max={500} step={10} style={{ width: '100%' }} placeholder="100" />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'segment_config', 'min_segment_length']} label="每段最小长度">
                                  <InputNumber min={1} max={100} style={{ width: '100%' }} placeholder="5" />
                                </Form.Item>
                              </Col>
                            </Row>
                            <Form.Item label="段间延迟范围（秒）">
                              <Row gutter={16}>
                                <Col span={12}>
                                  <Form.Item name={['adapters', 'linyu', 'segment_config', 'delay_range', 0]} noStyle>
                                    <InputNumber min={0.1} max={30} step={0.5} style={{ width: '100%' }} placeholder="最小 0.5" />
                                  </Form.Item>
                                </Col>
                                <Col span={12}>
                                  <Form.Item name={['adapters', 'linyu', 'segment_config', 'delay_range', 1]} noStyle>
                                    <InputNumber min={0.1} max={30} step={0.5} style={{ width: '100%' }} placeholder="最大 2.0" />
                                  </Form.Item>
                                </Col>
                              </Row>
                            </Form.Item>
                            <Row gutter={16}>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'segment_config', 'strategy']} label="分割策略">
                                  <Select>
                                    <Option value="sentence">按句子分段（更自然）</Option>
                                    <Option value="length">按长度分段（更均匀）</Option>
                                  </Select>
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name={['adapters', 'linyu', 'segment_config', 'min_sentences_to_split']} label="最小句子数阈值">
                                  <InputNumber min={1} max={10} style={{ width: '100%' }} placeholder="2" />
                                </Form.Item>
                              </Col>
                            </Row>
                          </>
                        ) : (
                          <span style={{ color: '#aaa', fontSize: 13 }}>启用后展开详细配置</span>
                        )}
                      </Form.Item>
                    </Card>

                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      onClick={handleSaveAdapters}
                      loading={savingAdapters}
                    >
                      保存适配器配置
                    </Button>
                  </Form>
                ),
              }] : []),
            ]}
          />
        </Form>
      </Card>
    </div>
  );
};

export default UserSettingsPage;
