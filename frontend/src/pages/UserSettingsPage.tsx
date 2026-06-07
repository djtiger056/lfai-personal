import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Divider, Form, Input, InputNumber, Row, Select, Space, Spin, Switch, Tabs, message } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import api, { configApi } from '@/services/api'
import { useAuth } from '../contexts/AuthContext'

const { TextArea } = Input

const segmentStrategyOptions = [
  { value: 'sentence', label: '按句子分段（更自然）' },
  { value: 'length', label: '按长度分段（更均匀）' },
]

const renderSegmentConfig = (adapterKey: 'qq' | 'linyu') => (
  <>
    <Divider plain>分段发送</Divider>
    <Form.Item
      name={['adapters', adapterKey, 'segment_config', 'enabled']}
      label="启用分段发送"
      valuePropName="checked"
      help="将长消息拆分为多段发送，避免长回复一次性刷屏。"
    >
      <Switch checkedChildren="启用" unCheckedChildren="禁用" />
    </Form.Item>
    <Row gutter={16}>
      <Col span={12}>
        <Form.Item name={['adapters', adapterKey, 'segment_config', 'max_segment_length']} label="每段最大长度">
          <InputNumber min={10} max={500} step={10} style={{ width: '100%' }} placeholder="100" />
        </Form.Item>
      </Col>
      <Col span={12}>
        <Form.Item name={['adapters', adapterKey, 'segment_config', 'min_segment_length']} label="每段最小长度">
          <InputNumber min={1} max={100} style={{ width: '100%' }} placeholder="5" />
        </Form.Item>
      </Col>
    </Row>
    <Form.Item label="段间延迟范围（秒）" help="每段消息之间随机等待的最小/最大秒数。">
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name={['adapters', adapterKey, 'segment_config', 'delay_range', 0]} noStyle>
            <InputNumber min={0.1} max={30} step={0.5} style={{ width: '100%' }} placeholder="最小 0.5" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name={['adapters', adapterKey, 'segment_config', 'delay_range', 1]} noStyle>
            <InputNumber min={0.1} max={30} step={0.5} style={{ width: '100%' }} placeholder="最大 2.0" />
          </Form.Item>
        </Col>
      </Row>
    </Form.Item>
    <Row gutter={16}>
      <Col span={12}>
        <Form.Item name={['adapters', adapterKey, 'segment_config', 'strategy']} label="分割策略">
          <Select options={segmentStrategyOptions} />
        </Form.Item>
      </Col>
      <Col span={12}>
        <Form.Item name={['adapters', adapterKey, 'segment_config', 'min_sentences_to_split']} label="最小句子数阈值">
          <InputNumber min={1} max={10} style={{ width: '100%' }} placeholder="2" />
        </Form.Item>
      </Col>
    </Row>
  </>
)

const renderDebounceConfig = (adapterKey: 'qq' | 'linyu') => (
  <>
    <Divider plain>消息防抖（合并）</Divider>
    <Form.Item
      name={['adapters', adapterKey, 'debounce', 'enabled']}
      label="启用消息防抖"
      valuePropName="checked"
      help="用户短时间连续发送多条消息时，先合并再回复，避免 AI 多次打断。"
    >
      <Switch checkedChildren="启用" unCheckedChildren="禁用" />
    </Form.Item>
    <Row gutter={16}>
      <Col span={12}>
        <Form.Item
          name={['adapters', adapterKey, 'debounce', 'delay']}
          label="等待时间（秒）"
          help="最后一条消息后等待多久再回复。"
        >
          <InputNumber min={1} max={30} step={0.5} style={{ width: '100%' }} placeholder="3.0" />
        </Form.Item>
      </Col>
      <Col span={12}>
        <Form.Item
          name={['adapters', adapterKey, 'debounce', 'max_wait']}
          label="最大等待时间（秒）"
          help="防止用户一直输入导致机器人永远不回复。"
        >
          <InputNumber min={5} max={60} step={1} style={{ width: '100%' }} placeholder="15.0" />
        </Form.Item>
      </Col>
    </Row>
  </>
)

const UserSettingsPage: React.FC = () => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { refreshUser } = useAuth()

  const load = async () => {
    setLoading(true)
    try {
      const [cfg, auth] = await Promise.all([
        configApi.getConfig(),
        api.get('/auth/settings'),
      ])
      form.setFieldsValue({
        ...cfg,
        auth: { ui_auth: auth.data },
      })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const values = form.getFieldsValue()
      const auth = values.auth?.ui_auth || {}
      await configApi.updateConfig({
        llm: values.llm,
        adapters: values.adapters,
        daily_schedule_generation: values.daily_schedule_generation,
        image_generation: values.image_generation,
        video_generation: values.video_generation,
      } as any)
      await api.put('/auth/settings', auth)
      message.success('系统配置已保存')
      await refreshUser()
      load()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Spin spinning={loading}>
        <Card
          title="系统配置"
          extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>保存配置</Button>
            </Space>
          }
        >
          <Alert
            title="个人版使用 data/personal/config.yaml 作为唯一配置来源，提示词与底图保存在同一资料目录。修改适配器连接参数后，部分后台连接可能需要重启服务。"
            type="info"
            showIcon
            style={{ marginBottom: 20 }}
          />
          <Form form={form} layout="vertical">
          <Tabs
            items={[
              {
                key: 'auth',
                label: '身份验证',
                children: (
                  <>
                    <Form.Item name={['auth', 'ui_auth', 'enabled']} label="启用控制台身份验证" valuePropName="checked">
                      <Switch checkedChildren="启用" unCheckedChildren="关闭" />
                    </Form.Item>
                    <Row gutter={16}>
                      <Col span={12}>
                        <Form.Item name={['auth', 'ui_auth', 'username']} label="管理账号" rules={[{ required: true }]}>
                          <Input autoComplete="username" />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name={['auth', 'ui_auth', 'password']} label="管理密码" rules={[{ required: true }]}>
                          <Input.Password autoComplete="current-password" />
                        </Form.Item>
                      </Col>
                    </Row>
                  </>
                ),
              },
              {
                key: 'llm',
                label: 'LLM',
                children: (
                  <>
                    <Form.Item name={['llm', 'provider']} label="提供商">
                      <Select options={[
                        { value: 'openai', label: 'OpenAI' },
                        { value: 'siliconflow', label: 'SiliconFlow' },
                        { value: 'deepseek', label: 'DeepSeek' },
                        { value: 'qwen', label: '通义千问' },
                        { value: 'yunwu', label: 'Yunwu' },
                        { value: 'ollama', label: 'Ollama' },
                      ]} />
                    </Form.Item>
                    <Form.Item name={['llm', 'api_base']} label="API 地址"><Input /></Form.Item>
                    <Form.Item name={['llm', 'api_key']} label="API Key"><Input.Password /></Form.Item>
                    <Form.Item name={['llm', 'model']} label="模型"><Input /></Form.Item>
                    <Row gutter={16}>
                      <Col span={12}><Form.Item name={['llm', 'temperature']} label="Temperature"><InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} /></Form.Item></Col>
                      <Col span={12}><Form.Item name={['llm', 'max_tokens']} label="Max Tokens"><InputNumber min={1} max={128000} style={{ width: '100%' }} /></Form.Item></Col>
                    </Row>
                  </>
                ),
              },
              {
                key: 'adapters',
                label: '适配器',
                children: (
                  <>
                    <Form.Item name={['adapters', 'console', 'enabled']} label="启用控制台适配器" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Card size="small" title="QQ" style={{ marginBottom: 16 }}>
                      <Form.Item name={['adapters', 'qq', 'enabled']} label="启用 QQ" valuePropName="checked"><Switch /></Form.Item>
                      <Row gutter={16}>
                        <Col span={16}><Form.Item name={['adapters', 'qq', 'ws_host']} label="WebSocket 地址"><Input /></Form.Item></Col>
                        <Col span={8}><Form.Item name={['adapters', 'qq', 'ws_port']} label="端口"><InputNumber min={1} max={65535} style={{ width: '100%' }} /></Form.Item></Col>
                      </Row>
                      <Form.Item name={['adapters', 'qq', 'access_token']} label="访问令牌"><Input.Password /></Form.Item>
                      <Form.Item name={['adapters', 'qq', 'need_at']} label="群聊需要 @ 机器人" valuePropName="checked"><Switch /></Form.Item>
                    </Card>
                    <Card size="small" title="Linyu">
                      <Form.Item name={['adapters', 'linyu', 'enabled']} label="启用 Linyu 适配器" valuePropName="checked"><Switch /></Form.Item>
                      <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                        message="伴侣账号已迁移到账号管理"
                        description="这里不再维护 Linyu 伴侣登录账号。该页面只配置连接服务器、分段发送和防抖等适配器参数。伴侣账号、绑定关系和人格提示词请到“账号管理”和“人格设定”页面维护。"
                      />
                      <Row gutter={16}>
                        <Col span={12}><Form.Item name={['adapters', 'linyu', 'http_host']} label="HTTP 地址"><Input /></Form.Item></Col>
                        <Col span={12}><Form.Item name={['adapters', 'linyu', 'http_port']} label="HTTP 端口"><InputNumber min={1} max={65535} style={{ width: '100%' }} /></Form.Item></Col>
                      </Row>
                      <Row gutter={16}>
                        <Col span={12}><Form.Item name={['adapters', 'linyu', 'ws_host']} label="WebSocket 地址"><Input /></Form.Item></Col>
                        <Col span={12}><Form.Item name={['adapters', 'linyu', 'ws_port']} label="WebSocket 端口"><InputNumber min={1} max={65535} style={{ width: '100%' }} /></Form.Item></Col>
                      </Row>
                    </Card>
                  </>
                ),
              },
              {
                key: 'message-sending',
                label: '分段发送',
                children: (
                  <>
                    <Alert
                      title="这里集中配置消息拆分和连续消息合并，不影响适配器连接参数。"
                      type="info"
                      showIcon
                      style={{ marginBottom: 20 }}
                    />
                    <Card size="small" title="QQ 分段与防抖" style={{ marginBottom: 16 }}>
                      {renderSegmentConfig('qq')}
                      {renderDebounceConfig('qq')}
                    </Card>
                    <Card size="small" title="Linyu 分段与防抖">
                      {renderSegmentConfig('linyu')}
                      {renderDebounceConfig('linyu')}
                    </Card>
                  </>
                ),
              },
            ]}
          />
          </Form>
        </Card>
      </Spin>
    </div>
  )
}

export default UserSettingsPage
