import React, { useEffect, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Space,
  Switch,
  Table,
  Tag,
  TimePicker,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  CalendarOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { dailyScheduleApi } from '@/services/api'
import {
  DailyScheduleGenConfig,
  GeneratedScheduleData,
  GeneratedScheduleSlot,
  GeneratedScheduleStatus,
} from '@/types'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

type FormValues = DailyScheduleGenConfig & { use_custom_llm?: boolean }

const DEFAULT_CONFIG: DailyScheduleGenConfig = {
  enabled: true,
  generate_window_start: '00:00',
  generate_window_end: '06:00',
  persona_name: '小馨',
  persona_desc: '温柔黏人的大三外语系女生，异地恋，校园生活，爱撒娇，偶尔小脾气',
  prompt_template: '',
  timezone: '',
  llm: null,
}

/** 判断当前时间是否在某个时间段内（HH:MM 格式） */
function isCurrentSlot(start: string, end: string): boolean {
  const now = dayjs()
  const nowMin = now.hour() * 60 + now.minute()
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  const startMin = sh * 60 + sm
  const endMin = eh * 60 + em
  if (endMin > startMin) {
    return nowMin >= startMin && nowMin < endMin
  }
  // 跨午夜
  return nowMin >= startMin || nowMin < endMin
}

/** 格式化 ISO 时间字符串为本地可读格式 */
function fmtDatetime(iso: string | null | undefined): string {
  if (!iso) return '暂无'
  const d = dayjs(iso)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : iso
}

const DailySchedulePage: React.FC = () => {
  const [form] = Form.useForm<FormValues>()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [status, setStatus] = useState<GeneratedScheduleStatus | null>(null)
  const [today, setToday] = useState<GeneratedScheduleData | null>(null)
  const useCustomLlm = Form.useWatch('use_custom_llm', form)

  useEffect(() => {
    loadAll()
  }, [])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [cfg, stat] = await Promise.all([
        dailyScheduleApi.getConfig(),
        dailyScheduleApi.getStatus(),
      ])
      form.setFieldsValue({
        ...DEFAULT_CONFIG,
        ...cfg,
        use_custom_llm: !!cfg.llm,
        llm: cfg.llm ?? {
          provider: 'openai',
          api_base: '',
          api_key: '',
          model: '',
          temperature: 0.9,
          max_tokens: 2000,
        },
      })
      setStatus(stat)
    } catch {
      message.error('加载每日作息生成配置失败')
    } finally {
      setLoading(false)
    }
    // 单独加载今日作息，404 不算错误
    try {
      const data = await dailyScheduleApi.getToday()
      setToday(data)
    } catch {
      setToday(null)
    }
  }

  const refreshStatus = async () => {
    try {
      const stat = await dailyScheduleApi.getStatus()
      setStatus(stat)
    } catch {
      setStatus(null)
    }
  }

  const refreshToday = async () => {
    try {
      const data = await dailyScheduleApi.getToday()
      setToday(data)
    } catch {
      setToday(null)
    }
  }

  const saveConfig = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      const payload: DailyScheduleGenConfig = {
        enabled: values.enabled ?? true,
        generate_window_start: values.generate_window_start || '00:00',
        generate_window_end: values.generate_window_end || '06:00',
        persona_name: values.persona_name || DEFAULT_CONFIG.persona_name,
        persona_desc: values.persona_desc || DEFAULT_CONFIG.persona_desc,
        prompt_template: values.prompt_template || '',
        timezone: values.timezone || '',
        llm: values.use_custom_llm ? (values.llm ?? {}) : null,
      }
      await dailyScheduleApi.saveConfig(payload)
      message.success('配置已保存')
      await refreshStatus()
    } catch (err: any) {
      if (err?.errorFields) return // antd 表单校验失败，不弹错误
      message.error('保存失败，请检查表单内容')
    } finally {
      setSaving(false)
    }
  }

  const triggerGenerate = async (force = false) => {
    setGenerating(true)
    try {
      const result = await dailyScheduleApi.generate(force)
      if (result.success) {
        message.success(result.message)
      } else {
        message.info(result.message)
      }
      await Promise.all([refreshStatus(), refreshToday()])
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '生成失败，请检查 LLM 配置')
    } finally {
      setGenerating(false)
    }
  }

  // ---- 状态标签 ----
  const statusBadge = () => {
    if (!status) return <Badge status="default" text="未知" />
    if (!status.config_enabled) return <Badge status="default" text="已禁用" />
    if (status.generated) return <Badge status="success" text="今日已生成" />
    return <Badge status="warning" text="今日未生成" />
  }

  // ---- 今日作息表格列 ----
  const columns = [
    {
      title: '时间段',
      key: 'time',
      width: 150,
      render: (_: unknown, record: GeneratedScheduleSlot) => {
        const active = isCurrentSlot(record.start, record.end)
        return (
          <Space size={4}>
            {active && (
              <Tooltip title="当前时间段">
                <CheckCircleOutlined style={{ color: '#52c41a' }} />
              </Tooltip>
            )}
            <Text strong={active} style={active ? { color: '#52c41a' } : undefined}>
              {record.start} – {record.end}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '活动',
      dataIndex: 'activity',
      width: 160,
      render: (value: string, record: GeneratedScheduleSlot) => {
        const active = isCurrentSlot(record.start, record.end)
        return (
          <Tag color={active ? 'green' : 'blue'}>
            {active ? '▶ ' : ''}{value}
          </Tag>
        )
      },
    },
    {
      title: '状态描述',
      dataIndex: 'desc',
      render: (value: string) =>
        value ? <Text>{value}</Text> : <Text type="secondary">暂无描述</Text>,
    },
  ]

  return (
    <div style={{ padding: '0 24px' }}>
      {/* 页头 */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={3} style={{ margin: 0 }}>
            每日作息生成
          </Title>
          <Text type="secondary">
            用 LLM 每天生成一份有随机性的全天作息，自动注入"你在干嘛"类回复上下文。
          </Text>
        </Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>
              重新加载
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={saveConfig} loading={saving}>
              保存配置
            </Button>
          </Space>
        </Col>
      </Row>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>

        {/* 今日状态卡片 */}
        <Card
          title={
            <Space>
              <CalendarOutlined />
              <span>今日状态</span>
              {statusBadge()}
            </Space>
          }
          loading={loading}
          extra={
            <Space>
              <Button
                icon={<ThunderboltOutlined />}
                onClick={() => triggerGenerate(false)}
                loading={generating}
                disabled={status?.generated}
              >
                手动生成
              </Button>
              <Popconfirm
                title="确认强制重新生成？"
                description="这会覆盖 data/generated_schedule.json 中今天的作息表。"
                okText="重新生成"
                cancelText="取消"
                onConfirm={() => triggerGenerate(true)}
              >
                <Button danger icon={<CloudSyncOutlined />} loading={generating}>
                  强制重生成
                </Button>
              </Popconfirm>
            </Space>
          }
        >
          <Row gutter={24}>
            <Col span={6}>
              <Text type="secondary">生成日期</Text>
              <Paragraph style={{ marginBottom: 0, fontWeight: 500 }}>
                {status?.date || '暂无'}
              </Paragraph>
            </Col>
            <Col span={6}>
              <Text type="secondary">生成时间</Text>
              <Paragraph style={{ marginBottom: 0, fontWeight: 500 }}>
                {fmtDatetime(status?.generated_at)}
              </Paragraph>
            </Col>
            <Col span={6}>
              <Text type="secondary">时间段数量</Text>
              <Paragraph style={{ marginBottom: 0, fontWeight: 500 }}>
                {status?.slot_count ?? 0} 段
              </Paragraph>
            </Col>
            <Col span={6}>
              <Text type="secondary">自动生成</Text>
              <Paragraph style={{ marginBottom: 0, fontWeight: 500 }}>
                {status?.config_enabled ? '✅ 开启' : '⛔ 关闭'}
              </Paragraph>
            </Col>
          </Row>

          {!today && !loading && (
            <Alert
              type="info"
              showIcon
              message="今天还没有可预览的生成作息"
              description="可以等待凌晨窗口自动生成，也可以点击「手动生成」立即测试。"
              style={{ marginTop: 16 }}
            />
          )}
        </Card>

        {/* 今日作息时间表 */}
        {today && (
          <Card
            title={
              <Space>
                <span>今日生成作息</span>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  生成于 {fmtDatetime(today.generated_at)}
                </Text>
              </Space>
            }
            extra={
              <Tooltip title="绿色高亮为当前时间段">
                <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
              </Tooltip>
            }
          >
            <Table
              rowKey={(record: GeneratedScheduleSlot) => `${record.start}-${record.end}-${record.activity}`}
              columns={columns}
              dataSource={today.slots ?? []}
              pagination={false}
              size="middle"
              rowClassName={(record: GeneratedScheduleSlot) =>
                isCurrentSlot(record.start, record.end) ? 'ant-table-row-selected' : ''
              }
            />
          </Card>
        )}

        {/* 配置表单 */}
        <Form form={form} layout="vertical" initialValues={DEFAULT_CONFIG}>

          {/* 生成规则 */}
          <Card title="生成规则" loading={loading} style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={4}>
                <Form.Item name="enabled" label="启用自动生成" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="禁用" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item
                  name="timezone"
                  label="时区"
                  tooltip="留空则使用主动聊天配置或 Asia/Shanghai"
                >
                  <Input placeholder="Asia/Shanghai" />
                </Form.Item>
              </Col>
              <Col span={7}>
                <Form.Item
                  name="generate_window_start"
                  label="生成窗口开始"
                  rules={[
                    { required: true, message: '请输入开始时间' },
                    { pattern: /^\d{2}:\d{2}$/, message: '格式 HH:MM' },
                  ]}
                >
                  <Input placeholder="00:00" maxLength={5} />
                </Form.Item>
              </Col>
              <Col span={7}>
                <Form.Item
                  name="generate_window_end"
                  label="生成窗口结束"
                  rules={[
                    { required: true, message: '请输入结束时间' },
                    { pattern: /^\d{2}:\d{2}$/, message: '格式 HH:MM' },
                  ]}
                >
                  <Input placeholder="06:00" maxLength={5} />
                </Form.Item>
              </Col>
            </Row>
            <Alert
              type="info"
              showIcon
              message="自动生成由后端 scheduler 每 60 秒检查一次"
              description="只有当前时间落在生成窗口内、且今天尚未生成时才会调用 LLM；手动生成不受时间窗口限制。"
            />
          </Card>

          {/* 人设注入 */}
          <Card title="人设注入" loading={loading} style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item name="persona_name" label="人设名称">
                  <Input placeholder="小馨" />
                </Form.Item>
              </Col>
              <Col span={18}>
                <Form.Item name="persona_desc" label="人设描述">
                  <Input placeholder="温柔黏人的大三外语系女生，异地恋，校园生活..." />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              name="prompt_template"
              label={
                <Space size={4}>
                  <span>自定义提示词模板</span>
                  <Tooltip title="可用变量：{weekday_cn} {date_str} {weekday_hint} {persona_name} {persona_desc}">
                    <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                  </Tooltip>
                </Space>
              }
            >
              <TextArea
                rows={8}
                placeholder="留空则使用内置提示词模板。可用变量：{weekday_cn}、{date_str}、{weekday_hint}、{persona_name}、{persona_desc}"
              />
            </Form.Item>
          </Card>

          {/* LLM 覆盖配置 */}
          <Card title="LLM 覆盖配置" loading={loading}>
            <Form.Item
              name="use_custom_llm"
              label="使用独立 LLM"
              valuePropName="checked"
              tooltip="关闭时复用全局 LLM 配置；开启时仅作息生成使用这里的模型，适合用低成本模型生成作息。"
            >
              <Switch checkedChildren="独立配置" unCheckedChildren="复用全局" />
            </Form.Item>

            {useCustomLlm && (
              <>
                <Divider dashed />
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item name={['llm', 'provider']} label="提供商">
                      <Input placeholder="openai / qwen / deepseek / siliconflow" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name={['llm', 'model']} label="模型">
                      <Input placeholder="gpt-4o-mini" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name={['llm', 'api_base']} label="API 地址">
                      <Input placeholder="https://api.openai.com/v1" />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}>
                    <Form.Item name={['llm', 'api_key']} label="API Key">
                      <Input.Password placeholder="sk-..." />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name={['llm', 'temperature']} label="Temperature">
                      <InputNumber
                        min={0}
                        max={2}
                        step={0.1}
                        style={{ width: '100%' }}
                        placeholder="0.9"
                      />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name={['llm', 'max_tokens']} label="Max Tokens">
                      <InputNumber
                        min={500}
                        max={16000}
                        step={100}
                        style={{ width: '100%' }}
                        placeholder="2000"
                      />
                    </Form.Item>
                  </Col>
                </Row>
              </>
            )}

            {!useCustomLlm && (
              <Alert
                type="success"
                showIcon
                message="当前使用全局 LLM 配置"
                description="作息生成会复用全局 llm 节的 provider / model / api_key 等设置。如需使用更便宜的模型生成作息，可开启独立配置。"
              />
            )}
          </Card>
        </Form>
      </Space>
    </div>
  )
}

export default DailySchedulePage
