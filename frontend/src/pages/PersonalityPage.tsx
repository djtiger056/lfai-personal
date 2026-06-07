import React, { useEffect, useMemo, useState } from 'react'
import { Button, Card, Form, Input, InputNumber, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { accountsApi, CompanionActionCatalogItem, CompanionActionConfig, CompanionActionLog, LinyuAIAccount, promptApi } from '@/services/api'

const { TextArea } = Input
const { Text } = Typography

type PromptFormValues = {
  content: string
  rules: string
  summary?: string
}

type ActionFormValues = {
  enabled: boolean
  allow_actions: string[]
  max_actions_per_plan: number
  max_actions_per_hour: number
  max_actions_per_day: number
  max_proactive_messages_per_friend_per_hour: number
}

const companionIdOf = (account: LinyuAIAccount): string => account.companion_id || `companion:${account.id}`
const getPlatformAccounts = (account?: LinyuAIAccount) => Array.isArray(account?.platform_accounts) ? account.platform_accounts : []
const getBoundAccounts = (account?: LinyuAIAccount) => Array.isArray(account?.bound_accounts) ? account.bound_accounts : []

const companionLabel = (account?: LinyuAIAccount): string => {
  if (!account) return ''
  return account.companion_name || account.account_name || `伴侣 ${account.id}`
}

const platformLabel = (account?: LinyuAIAccount): string => {
  if (!account) return '-'
  const platforms = getPlatformAccounts(account)
  if (!platforms.length) {
    return account.account_name || account.account || '-'
  }
  return platforms
    .map((item) => `${String(item.platform).toUpperCase()}:${item.account_name}`)
    .join(' / ')
}

const PersonalityPage: React.FC = () => {
  const [form] = Form.useForm<PromptFormValues>()
  const [actionsForm] = Form.useForm<ActionFormValues>()
  const [companions, setCompanions] = useState<LinyuAIAccount[]>([])
  const [selectedAIId, setSelectedAIId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionSaving, setActionSaving] = useState(false)
  const [promptMeta, setPromptMeta] = useState<{ is_custom: boolean; updated_at?: string; source: string } | null>(null)
  const [rulesMeta, setRulesMeta] = useState<{ is_custom: boolean } | null>(null)
  const [actionCatalog, setActionCatalog] = useState<CompanionActionCatalogItem[]>([])
  const [actionLogs, setActionLogs] = useState<CompanionActionLog[]>([])

  const selectedCompanion = useMemo(
    () => companions.find((item) => item.id === selectedAIId),
    [companions, selectedAIId]
  )
  const selectedCompanionId = selectedCompanion ? companionIdOf(selectedCompanion) : ''

  const loadCompanions = async () => {
    setLoading(true)
    try {
      const data = await accountsApi.listCompanions()
      setCompanions(data)
      setSelectedAIId((prev) => {
        if (prev && data.some((item) => item.id === prev)) return prev
        return data[0]?.id ?? null
      })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载伴侣账号失败')
    } finally {
      setLoading(false)
    }
  }

  const loadActionCatalog = async () => {
    try {
      const data = await accountsApi.getCompanionActionsCatalog()
      setActionCatalog(data)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载动作目录失败')
    }
  }

  const loadPrompt = async (companionId: string) => {
    if (!companionId) {
      form.resetFields()
      setPromptMeta(null)
      return
    }
    setLoading(true)
    try {
      const data = await promptApi.getPrompt(companionId)
      const rules = await promptApi.getCompanionRules(companionId)
      form.setFieldsValue({ content: data.content || '', rules: rules.content || '', summary: '' })
      setPromptMeta({
        is_custom: data.is_custom,
        updated_at: data.updated_at,
        source: data.source,
      })
      setRulesMeta({ is_custom: rules.is_custom })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载人设提示词失败')
    } finally {
      setLoading(false)
    }
  }

  const loadActionConfig = async (companionId: string) => {
    if (!companionId) {
      actionsForm.resetFields()
      setActionLogs([])
      return
    }
    setLoading(true)
    try {
      const [cfg, logs] = await Promise.all([
        accountsApi.getCompanionActionsConfig(companionId),
        accountsApi.listCompanionActionLogs(companionId, 50),
      ])
      actionsForm.setFieldsValue({
        enabled: cfg.enabled,
        allow_actions: cfg.allow_actions || [],
        max_actions_per_plan: cfg.rate_limits?.max_actions_per_plan ?? 3,
        max_actions_per_hour: cfg.rate_limits?.max_actions_per_hour ?? 10,
        max_actions_per_day: cfg.rate_limits?.max_actions_per_day ?? 50,
        max_proactive_messages_per_friend_per_hour: cfg.rate_limits?.max_proactive_messages_per_friend_per_hour ?? 10,
      })
      setActionLogs(logs)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载自主动作配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCompanions()
    loadActionCatalog()
  }, [])

  useEffect(() => {
    loadPrompt(selectedCompanionId)
    loadActionConfig(selectedCompanionId)
  }, [selectedCompanionId])

  const savePrompt = async () => {
    if (!selectedCompanionId) {
      message.warning('请选择伴侣账号')
      return
    }
    const values = await form.validateFields()
    setSaving(true)
    try {
      await promptApi.updatePrompt(values.content, values.summary || '', selectedCompanionId)
      await promptApi.updateRules(values.rules || '', selectedCompanionId)
      message.success('人设提示词已保存')
      await loadPrompt(selectedCompanionId)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存人设提示词失败')
    } finally {
      setSaving(false)
    }
  }

  const resetPrompt = async () => {
    if (!selectedCompanionId) return
    setSaving(true)
    try {
      await promptApi.resetPrompt(selectedCompanionId)
      await promptApi.resetRules(selectedCompanionId)
      message.success('已恢复默认人设')
      await loadPrompt(selectedCompanionId)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重置人设提示词失败')
    } finally {
      setSaving(false)
    }
  }

  const saveActionsConfig = async () => {
    if (!selectedCompanionId) {
      message.warning('请选择伴侣账号')
      return
    }
    const values = await actionsForm.validateFields()
    setActionSaving(true)
    try {
      await accountsApi.updateCompanionActionsConfig(selectedCompanionId, {
        enabled: values.enabled,
        autonomy_mode: 'auto',
        target_scope: 'bound_and_friends',
        allow_actions: values.allow_actions || [],
        rate_limits: {
          max_actions_per_plan: values.max_actions_per_plan,
          max_actions_per_hour: values.max_actions_per_hour,
          max_actions_per_day: values.max_actions_per_day,
          max_proactive_messages_per_friend_per_hour: values.max_proactive_messages_per_friend_per_hour,
        },
      })
      message.success('自主 IM 动作配置已保存')
      await loadActionConfig(selectedCompanionId)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存自主动作配置失败')
    } finally {
      setActionSaving(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card
          title="伴侣人设"
          extra={
            <Button icon={<ReloadOutlined />} onClick={loadCompanions} loading={loading}>
              刷新
            </Button>
          }
        >
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Select
              style={{ width: 360, maxWidth: '100%' }}
              placeholder="选择伴侣"
              value={selectedAIId ?? undefined}
              onChange={setSelectedAIId}
              loading={loading}
              options={companions.map((item) => ({
                value: item.id,
                label: `${companionLabel(item)} / ${platformLabel(item)}`,
              }))}
              optionFilterProp="label"
              showSearch
            />

            {selectedCompanion ? (
              <Space wrap>
                <Tag color="blue">{companionLabel(selectedCompanion)}</Tag>
                <Text type="secondary">平台账号: {platformLabel(selectedCompanion)}</Text>
                <Tag color={promptMeta?.is_custom ? 'green' : undefined}>
                  {promptMeta?.is_custom ? '自定义' : '默认'}
                </Tag>
                <Tag color={rulesMeta?.is_custom ? 'gold' : undefined}>
                  {rulesMeta?.is_custom ? '伴侣功能协议已自定义' : '功能协议走全局默认'}
                </Tag>
                <Text type="secondary">聊天时会一起注入系统提示词和功能协议提示词</Text>
                {promptMeta?.updated_at ? <Text type="secondary">更新时间: {new Date(promptMeta.updated_at).toLocaleString('zh-CN')}</Text> : null}
              </Space>
            ) : (
              <Text type="secondary">暂无伴侣账号</Text>
            )}

            <Form form={form} layout="vertical">
              <Form.Item
                label="系统提示词"
                name="content"
                rules={[{ required: true, message: '请输入系统提示词' }]}
              >
                <TextArea rows={18} disabled={!selectedCompanionId} />
              </Form.Item>
              <Form.Item
                label="功能协议提示词"
                name="rules"
              >
                <TextArea rows={12} disabled={!selectedCompanionId} />
              </Form.Item>
              <Form.Item label="变更备注" name="summary">
                <Input disabled={!selectedCompanionId} allowClear />
              </Form.Item>
              <Space>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  loading={saving}
                  disabled={!selectedCompanionId}
                  onClick={savePrompt}
                >
                  保存人设
                </Button>
                <Popconfirm
                  title="恢复默认人设？"
                  okText="恢复"
                  cancelText="取消"
                  onConfirm={resetPrompt}
                  disabled={!selectedCompanionId}
                >
                  <Button disabled={!selectedCompanionId || saving}>恢复默认</Button>
                </Popconfirm>
              </Space>
            </Form>
          </Space>
        </Card>

        <Card title="伴侣列表">
          <Table
            rowKey="id"
            loading={loading}
            dataSource={companions}
            columns={[
              { title: '伴侣名称', render: (_, record) => companionLabel(record) },
              { title: '平台账号', render: (_, record) => platformLabel(record) },
              {
                title: '绑定用户账号',
                render: (_, record) => {
                  const bound = getBoundAccounts(record)
                  if (!bound.length) return <Text type="secondary">未绑定</Text>
                  return (
                    <Space wrap>
                      {bound.map((item) => (
                        <Tag key={item.id}>{item.display_name || item.account_name || item.remote_user_id}</Tag>
                      ))}
                    </Space>
                  )
                },
              },
              {
                title: '状态',
                dataIndex: 'enabled',
                width: 90,
                render: (enabled) => enabled ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
              },
            ]}
            pagination={{ pageSize: 6 }}
            onRow={(record) => ({
              onClick: () => setSelectedAIId(record.id),
              style: { cursor: 'pointer' },
            })}
          />
        </Card>

        <Card title="自主 IM 动作">
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Text type="secondary">
              默认运行模式：完全自主执行、静默执行但保留强审计日志。当前目标范围固定为“绑定对象 + 现有好友”。
            </Text>
            <Text type="warning">
              红包能力当前仅为云端占位接口：会记录 `red_packet.prepare` 意图与状态，但不会产生真实金额流转，也不会向聊天对象伪造红包消息。
            </Text>
            <Form form={actionsForm} layout="vertical">
              <Form.Item name="enabled" label="启用自主 IM 动作" valuePropName="checked">
                <Switch disabled={!selectedCompanionId} />
              </Form.Item>
              <Form.Item name="allow_actions" label="允许动作">
                <Select
                  mode="multiple"
                  disabled={!selectedCompanionId}
                  options={actionCatalog.map((item) => ({
                    value: item.name,
                    label: `${item.name} · ${item.description}`,
                  }))}
                />
              </Form.Item>
              <Space wrap size={16}>
                <Form.Item name="max_actions_per_plan" label="单次规划动作上限">
                  <InputNumber min={1} max={20} disabled={!selectedCompanionId} />
                </Form.Item>
                <Form.Item name="max_actions_per_hour" label="每小时动作上限">
                  <InputNumber min={1} max={200} disabled={!selectedCompanionId} />
                </Form.Item>
                <Form.Item name="max_actions_per_day" label="每天动作上限">
                  <InputNumber min={1} max={1000} disabled={!selectedCompanionId} />
                </Form.Item>
                <Form.Item name="max_proactive_messages_per_friend_per_hour" label="单好友每小时主动私聊上限">
                  <InputNumber min={1} max={200} disabled={!selectedCompanionId} />
                </Form.Item>
              </Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={actionSaving}
                disabled={!selectedCompanionId}
                onClick={saveActionsConfig}
              >
                保存动作配置
              </Button>
            </Form>
          </Space>
        </Card>

        <Card title="最近动作日志">
          <Table
            rowKey="id"
            size="small"
            dataSource={actionLogs}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: '时间', dataIndex: 'created_at', render: (value) => value ? new Date(value).toLocaleString('zh-CN') : '-' },
              { title: '来源', dataIndex: 'source', width: 90 },
              { title: '动作', dataIndex: 'action_name', width: 180 },
              { title: '目标', dataIndex: 'target_key', width: 160, render: (value) => value || '-' },
              {
                title: '状态',
                dataIndex: 'status',
                width: 90,
                render: (value) => {
                  if (value === 'success') return <Tag color="green">成功</Tag>
                  if (value === 'blocked') return <Tag color="orange">拦截</Tag>
                  return <Tag color="red">失败</Tag>
                },
              },
              {
                title: '结果',
                render: (_, record) => (
                  <Text type={record.error_message ? 'danger' : 'secondary'}>
                    {record.error_message || JSON.stringify(record.result || {})}
                  </Text>
                ),
              },
            ]}
          />
        </Card>
      </Space>
    </div>
  )
}

export default PersonalityPage
