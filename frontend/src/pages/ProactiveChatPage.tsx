import React, { useEffect, useMemo, useState } from 'react'
import {
  Card,
  Form,
  Input,
  InputNumber,
  Switch,
  Button,
  Space,
  Row,
  Col,
  message,
  Divider,
  Alert,
  Tag,
  Collapse,
  Typography,
  Statistic,
} from 'antd'
import { SaveOutlined, ThunderboltOutlined, ReloadOutlined, RobotOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { proactiveApi } from '@/services/api'

const { TextArea } = Input
const { Panel } = Collapse
const { Title, Text } = Typography

type TimeWindow = {
  start?: string
  end?: string
  randomize?: boolean
  max_messages?: number
  prompt?: string
}

type ImageGenerationSetting = {
  enabled?: boolean
  max_per_day?: number
}

type TargetForm = {
  channel?: string
  user_id?: string
  session_id?: string
  display_name?: string
  prompt?: string
  message_templates_text?: string
  time_windows?: TimeWindow[]
  image_generation_enabled?: boolean
  image_generation_max_per_day?: number
}

const defaultWindow: TimeWindow = {
  start: '09:00',
  end: '11:00',
  randomize: true,
  max_messages: 1,
  prompt: '',
}

const defaultTarget: TargetForm = {
  channel: 'web',
  user_id: 'web_user',
  session_id: 'web_user',
  display_name: '',
  prompt: '',
  time_windows: [defaultWindow],
  image_generation_enabled: undefined,
  image_generation_max_per_day: undefined,
}

const ProactiveChatPage: React.FC = () => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [status, setStatus] = useState<any>(null)
  const [triggering, setTriggering] = useState(false)

  useEffect(() => {
    loadConfig()
    loadStatus()
  }, [])

  const loadConfig = async () => {
    try {
      const cfg = await proactiveApi.getConfig()
      const targets: TargetForm[] = (cfg?.targets || []).map((t: any) => ({
        channel: t.channel || 'qq_private',
        user_id: t.user_id || '',
        session_id: t.session_id || '',
        display_name: t.display_name || '',
        prompt: t.prompt || '',
        message_templates_text: (t.message_templates || []).join('\n'),
        image_generation_enabled: t.image_generation ? t.image_generation.enabled : undefined,
        image_generation_max_per_day: t.image_generation ? t.image_generation.max_per_day : undefined,
        time_windows: (t.time_windows || []).map((w: any) => ({
          start: w.start || '09:00',
          end: w.end || '11:00',
          randomize: w.randomize !== false,
          max_messages: w.max_messages || w.max_messages_per_window || 1,
          prompt: w.prompt || '',
        })),
      }))

      form.setFieldsValue({
        enabled: cfg?.enabled,
        timezone: cfg?.timezone || 'Asia/Shanghai',
        check_interval_seconds: cfg?.check_interval_seconds || 60,
        default_prompt: cfg?.default_prompt,
        image_generation_enabled: cfg?.image_generation?.enabled ?? false,
        image_generation_max_per_day: cfg?.image_generation?.max_per_day ?? 3,
        message_templates_text: (cfg?.message_templates || []).join('\n'),
        behavior_rules: {
          enabled: cfg?.behavior_rules?.enabled ?? true,
          global_cooldown_seconds: cfg?.behavior_rules?.global_cooldown_seconds ?? 1800,
          inactive_greeting: {
            enabled: cfg?.behavior_rules?.inactive_greeting?.enabled ?? true,
            after_seconds: cfg?.behavior_rules?.inactive_greeting?.after_seconds ?? 21600,
            min_user_messages: cfg?.behavior_rules?.inactive_greeting?.min_user_messages ?? 1,
            instruction: cfg?.behavior_rules?.inactive_greeting?.instruction || '',
          },
          conversation_follow_up: {
            enabled: cfg?.behavior_rules?.conversation_follow_up?.enabled ?? true,
            after_seconds: cfg?.behavior_rules?.conversation_follow_up?.after_seconds ?? 900,
            min_user_messages: cfg?.behavior_rules?.conversation_follow_up?.min_user_messages ?? 1,
            instruction: cfg?.behavior_rules?.conversation_follow_up?.instruction || '',
          },
        },
        targets: targets.length ? targets : [defaultTarget],
      })
    } catch (err) {
      message.error('加载配置失败')
      console.error(err)
    }
  }

  const loadStatus = async () => {
    try {
      setStatusLoading(true)
      const data = await proactiveApi.getStatus()
      setStatus(data)
    } catch (err) {
      console.error(err)
    } finally {
      setStatusLoading(false)
    }
  }

  const buildTemplates = (text?: string) =>
    (text || '')
      .split('\n')
      .map(t => t.trim())
      .filter(Boolean)

  const handleSave = async () => {
    try {
      setLoading(true)
      const values = await form.validateFields()
      const payload = {
        enabled: values.enabled,
        timezone: values.timezone,
        check_interval_seconds: values.check_interval_seconds,
        default_prompt: values.default_prompt,
        image_generation: {
          enabled: values.image_generation_enabled,
          max_per_day: values.image_generation_max_per_day,
        },
        message_templates: buildTemplates(values.message_templates_text),
        behavior_rules: {
          enabled: values.behavior_rules?.enabled ?? true,
          global_cooldown_seconds: values.behavior_rules?.global_cooldown_seconds,
          inactive_greeting: {
            enabled: values.behavior_rules?.inactive_greeting?.enabled ?? true,
            after_seconds: values.behavior_rules?.inactive_greeting?.after_seconds,
            min_user_messages: values.behavior_rules?.inactive_greeting?.min_user_messages,
            instruction: values.behavior_rules?.inactive_greeting?.instruction,
          },
          conversation_follow_up: {
            enabled: values.behavior_rules?.conversation_follow_up?.enabled ?? true,
            after_seconds: values.behavior_rules?.conversation_follow_up?.after_seconds,
            min_user_messages: values.behavior_rules?.conversation_follow_up?.min_user_messages,
            instruction: values.behavior_rules?.conversation_follow_up?.instruction,
          },
        },
        targets: (values.targets || []).map((t: TargetForm) => {
          const imageGeneration: ImageGenerationSetting = {}
          if (typeof t.image_generation_enabled === 'boolean') {
            imageGeneration.enabled = t.image_generation_enabled
          }
          if (typeof t.image_generation_max_per_day === 'number') {
            imageGeneration.max_per_day = t.image_generation_max_per_day
          }

          const targetPayload: any = {
            channel: t.channel || 'qq_private',
            user_id: t.user_id,
            session_id: t.session_id || t.user_id,
            display_name: t.display_name,
            prompt: t.prompt,
            message_templates: buildTemplates(t.message_templates_text),
            time_windows: (t.time_windows || []).map(w => ({
              start: w.start,
              end: w.end,
              randomize: w.randomize !== false,
              max_messages: w.max_messages || 1,
              prompt: w.prompt,
            })),
          }

          if (Object.keys(imageGeneration).length > 0) {
            targetPayload.image_generation = imageGeneration
          }
          return targetPayload
        }),
      }
      await proactiveApi.updateConfig(payload)
      message.success('配置已保存')
      loadStatus()
    } catch (err) {
      console.error(err)
      message.error('保存失败')
    } finally {
      setLoading(false)
    }
  }

  const handleTrigger = async () => {
    try {
      setTriggering(true)
      const values = form.getFieldsValue()
      const target: TargetForm = (values.targets && values.targets[0]) || defaultTarget
      if (!target.user_id) {
        message.warning('请填写至少一个目标用户ID')
        return
      }
      const reply = await proactiveApi.triggerOnce({
        channel: target.channel || 'qq_private',
        user_id: target.user_id,
        session_id: target.session_id || target.user_id,
        display_name: target.display_name,
        instruction: values.default_prompt || target.prompt,
      })
      message.success('已触发 ' + reply)
      loadStatus()
    } catch (err) {
      console.error(err)
      message.error('触发失败')
    } finally {
      setTriggering(false)
    }
  }

  const statusTargets = useMemo(() => {
    const data = status?.targets_state || {}
    return Object.entries(data) as [string, any][]
  }, [status])

  return (
    <div style={{ padding: '0 24px' }}>
      {/* 顶部标题和状态栏 */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={3} style={{ margin: 0 }}>主动聊天</Title>
        </Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { loadConfig(); loadStatus(); }} loading={statusLoading}>
              刷新
            </Button>
            {status && (
              <Tag color={status.enabled ? 'green' : 'red'}>
                {status.enabled ? '已开启' : '未开启'}
              </Tag>
            )}
            <Button type="primary" icon={<SaveOutlined />} loading={loading} onClick={handleSave}>
              保存配置
            </Button>
            <Button icon={<ThunderboltOutlined />} loading={triggering} onClick={handleTrigger}>
              立即触发一次
            </Button>
          </Space>
        </Col>
      </Row>

      {/* 状态卡片 */}
      <Card 
        title="运行状态" 
        size="small" 
        style={{ marginBottom: 16 }}
        extra={
          <Button icon={<RobotOutlined />} onClick={loadStatus} size="small">
            刷新状态
          </Button>
        }
      >
        {status ? (
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="运行状态" value={status.running ? '运行中' : '已停止'} />
            </Col>
            <Col span={6}>
              <Statistic title="目标用户数" value={status.targets || 0} />
            </Col>
            <Col span={12}>
              {statusTargets.length === 0 ? (
                <Alert message="暂无目标状态" type="info" />
              ) : (
                <Collapse ghost size="small">
                  {statusTargets.slice(0, 3).map(([key, info]) => (
                    <Panel header={`${key} - 最后发送: ${info.last_sent || '无'}`} key={key}>
                      {info.activity && (
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: 8 }}>
                          最近用户发言: {info.activity.last_user_message_at || '无'}<br />
                          最近 AI 发言: {info.activity.last_assistant_message_at || '无'}<br />
                          待续聊触发时间: {info.activity.pending_follow_up_due_at || '无'}<br />
                          最近用户内容: {info.activity.last_user_message || '无'}
                        </div>
                      )}
                      {info.windows && Object.entries(info.windows as Record<string, any>).map(([wKey, w]) => (
                        <div key={wKey} style={{ marginBottom: 4 }}>
                          <Text strong>{wKey}</Text>
                          <div style={{ fontSize: '12px', color: '#666' }}>
                            计划: {(w as any)?.scheduled_time || '未排程'} | 已发: {(w as any)?.sent_today}
                          </div>
                        </div>
                      ))}
                    </Panel>
                  ))}
                  {statusTargets.length > 3 && (
                    <Panel header={`...还有 ${statusTargets.length - 3} 个用户`} key="more">
                      <Alert message="更多用户状态请查看详细日志" type="info" />
                    </Panel>
                  )}
                </Collapse>
              )}
            </Col>
          </Row>
        ) : (
          <Alert message="暂无状态数据" type="info" />
        )}
      </Card>

      {/* 配置区域 */}
      <Card title="配置管理">
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Web 聊天页已固定使用 channel=`web`、user_id=`web_user`、session_id=`web_user`。如果你想在网页里测试主动聊天，新增或修改一个目标为这组值即可。"
        />
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            enabled: false,
            timezone: 'Asia/Shanghai',
            check_interval_seconds: 60,
            image_generation_enabled: false,
            image_generation_max_per_day: 3,
            behavior_rules: {
              enabled: true,
              global_cooldown_seconds: 1800,
              inactive_greeting: {
                enabled: true,
                after_seconds: 21600,
                min_user_messages: 1,
              },
              conversation_follow_up: {
                enabled: true,
                after_seconds: 900,
                min_user_messages: 1,
              },
            },
            targets: [defaultTarget],
          }}
        >
          {/* 全局设置 */}
          <Card size="small" title="全局设置" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item label="开启主动聊天" name="enabled" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="时区" name="timezone">
                  <Input placeholder="Asia/Shanghai" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="检测间隔(秒)" name="check_interval_seconds">
                  <InputNumber min={10} max={3600} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="快速操作">
                  <Space>
                    <Button icon={<ReloadOutlined />} onClick={() => { loadConfig(); loadStatus(); }} loading={statusLoading} size="small">
                      刷新配置
                    </Button>
                  </Space>
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={6}>
                <Form.Item label="主动生图" name="image_generation_enabled" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="每日生图上限" name="image_generation_max_per_day">
                  <InputNumber min={0} max={10} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="默认提示词" name="default_prompt">
                  <TextArea rows={2} placeholder="请以女友身份主动问候..." />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="全局话术模板（每行一条）" name="message_templates_text">
                  <TextArea rows={2} placeholder="轻松问候模板，每行一条" />
                </Form.Item>
              </Col>
            </Row>
          </Card>

          <Card size="small" title="拟人化规则" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item label="启用行为规则" name={['behavior_rules', 'enabled']} valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="全局冷却(秒)" name={['behavior_rules', 'global_cooldown_seconds']}>
                  <InputNumber min={0} max={86400} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>

            <Divider plain>长期未聊问候</Divider>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item label="启用" name={['behavior_rules', 'inactive_greeting', 'enabled']} valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="多久未聊触发(秒)" name={['behavior_rules', 'inactive_greeting', 'after_seconds']}>
                  <InputNumber min={60} max={604800} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="最少历史用户消息数" name={['behavior_rules', 'inactive_greeting', 'min_user_messages']}>
                  <InputNumber min={1} max={1000} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="长期未聊补充提示词" name={['behavior_rules', 'inactive_greeting', 'instruction']}>
              <TextArea rows={2} placeholder="例如：像突然想起对方一样，发一句自然问候，不要显得催促。" />
            </Form.Item>

            <Divider plain>话题未完续聊</Divider>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item label="启用" name={['behavior_rules', 'conversation_follow_up', 'enabled']} valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="沉默多久续聊(秒)" name={['behavior_rules', 'conversation_follow_up', 'after_seconds']}>
                  <InputNumber min={30} max={86400} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="最少历史用户消息数" name={['behavior_rules', 'conversation_follow_up', 'min_user_messages']}>
                  <InputNumber min={1} max={1000} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="续聊补充提示词" name={['behavior_rules', 'conversation_follow_up', 'instruction']}>
              <TextArea rows={2} placeholder="例如：像真实伴侣一样轻轻追一句，延续上个话题，不要像系统提醒。" />
            </Form.Item>
          </Card>

          {/* 用户配置区域 */}
          <Form.List name="targets">
            {(fields, { add, remove }) => {
              return (
                <>
                  <div style={{ marginBottom: 16 }}>
                    <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
                      <Col>
                        <Title level={5} style={{ margin: 0 }}>用户配置（横向布局）</Title>
                      </Col>
                      <Col>
                        <Space>
                          <Text type="secondary">拖动查看更多用户</Text>
                          <Button type="dashed" icon={<PlusOutlined />} onClick={() => add(defaultTarget)}>
                            新增用户
                          </Button>
                        </Space>
                      </Col>
                    </Row>
                  </div>

                  <div style={{ 
                    display: 'flex', 
                    gap: 16, 
                    overflowX: 'auto', 
                    paddingBottom: 16,
                    scrollBehavior: 'smooth'
                  }}>
                    {fields.map((field, idx) => (
                      <Card
                        key={field.key}
                        type="inner"
                        title={`用户 ${idx + 1}`}
                        size="small"
                        style={{ minWidth: 320, maxWidth: 400, flex: '0 0 auto' }}
                        extra={
                          <Space>
                            {fields.length > 1 && (
                              <Button
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => remove(field.name)}
                              />
                            )}
                          </Space>
                        }
                      >
                        <Form.Item
                          label="渠道"
                          name={[field.name, 'channel']}
                          rules={[{ required: true, message: '请填写渠道' }]}
                        >
                          <Input placeholder="qq_private / qq_group / web" />
                        </Form.Item>
                        
                        <Form.Item
                          label="用户ID"
                          name={[field.name, 'user_id']}
                          rules={[{ required: true, message: '请输入用户ID' }]}
                        >
                          <Input />
                        </Form.Item>
                        
                        <Form.Item label="会话ID" name={[field.name, 'session_id']}>
                          <Input placeholder="默认为用户ID" />
                        </Form.Item>
                        
                        <Form.Item label="显示名" name={[field.name, 'display_name']}>
                          <Input placeholder="用于提示词中的昵称" />
                        </Form.Item>

                        <Form.Item label="专属提示词" name={[field.name, 'prompt']}>
                          <TextArea rows={2} placeholder="给当前用户的个性化语气/提醒" />
                        </Form.Item>
                        
                        <Form.Item label="自定义话术" name={[field.name, 'message_templates_text']}>
                          <TextArea rows={2} placeholder="覆盖/补充全局模板" />
                        </Form.Item>

                        <Row gutter={8}>
                          <Col span={12}>
                            <Form.Item label="允许主动生图" name={[field.name, 'image_generation_enabled']} valuePropName="checked">
                              <Switch size="small" />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item label="单日生图上限" name={[field.name, 'image_generation_max_per_day']}>
                              <InputNumber min={0} max={10} style={{ width: '100%' }} size="small" />
                            </Form.Item>
                          </Col>
                        </Row>

                        <Divider style={{ margin: '12px 0' }}>时间段</Divider>
                        <Form.List name={[field.name, 'time_windows']}>
                          {(winFields, { add: addWin, remove: removeWin }) => (
                            <>
                              {winFields.map((wf, wIdx) => (
                                <Card
                                  key={wf.key}
                                  size="small"
                                  type="inner"
                                  title={`时段 ${wIdx + 1}`}
                                  style={{ marginBottom: 8 }}
                                  extra={
                                    winFields.length > 1 && (
                                      <Button
                                        size="small"
                                        danger
                                        icon={<DeleteOutlined />}
                                        onClick={() => removeWin(wf.name)}
                                      />
                                    )
                                  }
                                >
                                  <Row gutter={8}>
                                    <Col span={12}>
                                      <Form.Item
                                        label="开始"
                                        name={[wf.name, 'start']}
                                        rules={[{ required: true, message: '必填' }]}
                                      >
                                        <Input placeholder="08:00" />
                                      </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                      <Form.Item
                                        label="结束"
                                        name={[wf.name, 'end']}
                                        rules={[{ required: true, message: '必填' }]}
                                      >
                                        <Input placeholder="21:30" />
                                      </Form.Item>
                                    </Col>
                                  </Row>
                                  <Row gutter={8}>
                                    <Col span={12}>
                                      <Form.Item label="随机时间" name={[wf.name, 'randomize']} valuePropName="checked">
                                        <Switch size="small" defaultChecked />
                                      </Form.Item>
                                    </Col>
                                    <Col span={12}>
                                      <Form.Item
                                        label="当日最多"
                                        name={[wf.name, 'max_messages']}
                                        rules={[{ type: 'number', min: 1 }]}
                                      >
                                        <InputNumber min={1} max={10} style={{ width: '100%' }} size="small" />
                                      </Form.Item>
                                    </Col>
                                  </Row>
                                  <Form.Item label="时段提示词" name={[wf.name, 'prompt']}>
                                    <TextArea rows={1} placeholder="例如 早安关心" />
                                  </Form.Item>
                                </Card>
                              ))}
                              <Button
                                type="dashed"
                                icon={<PlusOutlined />}
                                block
                                size="small"
                                onClick={() => addWin(defaultWindow)}
                              >
                                添加时间段
                              </Button>
                            </>
                          )}
                        </Form.List>
                      </Card>
                    ))}
                  </div>
                </>
              )
            }}
          </Form.List>
        </Form>
      </Card>
    </div>
  )
}

export default ProactiveChatPage
