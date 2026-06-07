import React, { useEffect, useMemo, useState } from 'react'
import { Button, Card, Form, Input, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { accountsApi, LinyuAIAccount, promptApi } from '@/services/api'

const { TextArea } = Input
const { Text } = Typography

type PromptFormValues = {
  content: string
  rules: string
  summary?: string
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
  const [companions, setCompanions] = useState<LinyuAIAccount[]>([])
  const [selectedAIId, setSelectedAIId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [promptMeta, setPromptMeta] = useState<{ is_custom: boolean; updated_at?: string; source: string } | null>(null)
  const [rulesMeta, setRulesMeta] = useState<{ is_custom: boolean } | null>(null)

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

  useEffect(() => {
    loadCompanions()
  }, [])

  useEffect(() => {
    loadPrompt(selectedCompanionId)
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
      </Space>
    </div>
  )
}

export default PersonalityPage
