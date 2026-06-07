import React, { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { accountsApi, ExternalAccount, LinyuAIAccount } from '../services/api'

const { Text } = Typography

type AccountFormValues = {
  platform: 'qq' | 'linyu'
  account_name: string
  display_name?: string
  enabled?: boolean
}

type AIAccountFormValues = {
  companion_name?: string
  linyu_account_name?: string
  linyu_password?: string
  qq_account_name?: string
  enabled?: boolean
  bound_account_ids?: number[]
}

type CompanionPlatformAccountPayload = NonNullable<LinyuAIAccount['platform_accounts']>[number]

const getPlatformAccounts = (account?: LinyuAIAccount): CompanionPlatformAccountPayload[] =>
  Array.isArray(account?.platform_accounts) ? account.platform_accounts : []

const getBoundAccounts = (account?: LinyuAIAccount): ExternalAccount[] =>
  Array.isArray(account?.bound_accounts) ? account.bound_accounts : []

const accountLabel = (account?: ExternalAccount): string => {
  if (!account) return '-'
  return account.display_name || account.account_name || account.remote_user_id || `账号 ${account.id}`
}

const aiLabel = (account?: LinyuAIAccount): string => {
  if (!account) return '-'
  return account.companion_name || account.account_name || `伴侣 ${account.id}`
}

const AccountsPage: React.FC = () => {
  const [accounts, setAccounts] = useState<ExternalAccount[]>([])
  const [aiAccounts, setAiAccounts] = useState<LinyuAIAccount[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [accountModalOpen, setAccountModalOpen] = useState(false)
  const [aiModalOpen, setAIModalOpen] = useState(false)
  const [editingAccount, setEditingAccount] = useState<ExternalAccount | null>(null)
  const [editingAI, setEditingAI] = useState<LinyuAIAccount | null>(null)
  const [accountForm] = Form.useForm<AccountFormValues>()
  const [aiForm] = Form.useForm<AIAccountFormValues>()

  const userAccountOptions = useMemo(
    () => accounts.map((item) => ({
      value: item.id,
      label: `${String(item.platform).toUpperCase()} / ${accountLabel(item)}`,
    })),
    [accounts]
  )

  const load = async () => {
    setLoading(true)
    try {
      const [nextAccounts, nextAIAccounts] = await Promise.all([
        accountsApi.listAccounts(),
        accountsApi.listCompanions(),
      ])
      setAccounts(nextAccounts)
      setAiAccounts(nextAIAccounts)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载账号失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openAccountModal = (record?: ExternalAccount) => {
    setEditingAccount(record || null)
    accountForm.setFieldsValue(record ? {
      platform: record.platform,
      account_name: record.account_name || record.display_name || '',
      display_name: record.display_name || '',
      enabled: record.enabled,
    } : {
      platform: 'linyu',
      enabled: true,
    })
    setAccountModalOpen(true)
  }

  const saveAccount = async () => {
    const values = await accountForm.validateFields()
    setSaving(true)
    try {
      const payload = {
        platform: values.platform,
        account_name: values.account_name.trim(),
        display_name: (values.display_name || '').trim(),
        enabled: values.enabled ?? true,
      }
      if (editingAccount) {
        await accountsApi.updateAccount(editingAccount.id, payload)
      } else {
        await accountsApi.createAccount(payload)
      }
      message.success(values.platform === 'linyu' ? '用户账号已保存并完成解析' : '用户账号已保存')
      setAccountModalOpen(false)
      await load()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存用户账号失败')
    } finally {
      setSaving(false)
    }
  }

  const openAIModal = (record?: LinyuAIAccount) => {
    setEditingAI(record || null)
    const platformAccounts = getPlatformAccounts(record)
    const linyuAccount = platformAccounts.find((item) => item.platform === 'linyu')
    const qqAccount = platformAccounts.find((item) => item.platform === 'qq')
    aiForm.setFieldsValue(record ? {
      companion_name: record.companion_name || '',
      linyu_account_name: linyuAccount?.account_name || record.account_name || record.account || '',
      linyu_password: linyuAccount?.password || record.password || '',
      qq_account_name: qqAccount?.account_name || '',
      enabled: record.enabled,
      bound_account_ids: Array.isArray(record.bound_account_ids) ? record.bound_account_ids : [],
    } : {
      enabled: true,
      bound_account_ids: [],
    })
    setAIModalOpen(true)
  }

  const saveAI = async () => {
    const values = await aiForm.validateFields()
    setSaving(true)
    try {
      const platformAccounts: CompanionPlatformAccountPayload[] = []
      const linyuAccountName = values.linyu_account_name?.trim()
      const qqAccountName = values.qq_account_name?.trim()

      if (linyuAccountName) {
        platformAccounts.push({
          platform: 'linyu',
          account_name: linyuAccountName,
          password: values.linyu_password || '',
          enabled: values.enabled ?? true,
          is_primary: true,
        })
      }

      if (qqAccountName) {
        platformAccounts.push({
          platform: 'qq',
          account_name: qqAccountName,
          enabled: values.enabled ?? true,
        })
      }

      if (!platformAccounts.length) {
        message.warning('至少配置一个伴侣平台账号')
        setSaving(false)
        return
      }

      const payload = {
        companion_name: (values.companion_name || linyuAccountName || qqAccountName || '').trim(),
        enabled: values.enabled ?? true,
        bound_account_ids: values.bound_account_ids || [],
        platform_accounts: platformAccounts,
      }
      if (editingAI) {
        await accountsApi.updateCompanion(editingAI.id, payload)
      } else {
        await accountsApi.createCompanion(payload)
      }
      message.success('伴侣账号已保存')
      setAIModalOpen(false)
      await load()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存伴侣账号失败')
    } finally {
      setSaving(false)
    }
  }

  const updateBindings = async (aiAccountId: number, boundIds: number[]) => {
    try {
      await accountsApi.updateCompanionBindings(aiAccountId, boundIds)
      message.success('绑定关系已更新')
      await load()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新绑定失败')
    }
  }

  const deleteAccount = (record: ExternalAccount) => {
    Modal.confirm({
      title: `删除用户账号：${accountLabel(record)}`,
      content: '删除后会同时移除相关绑定关系。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await accountsApi.deleteAccount(record.id)
        message.success('已删除')
        await load()
      },
    })
  }

  const deleteAIAccount = (record: LinyuAIAccount) => {
    Modal.confirm({
      title: `删除伴侣账号：${aiLabel(record)}`,
      content: '删除后该伴侣的运行会话和绑定关系会停止使用。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await accountsApi.deleteCompanion(record.id)
        message.success('已删除')
        await load()
      },
    })
  }

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card
          title="用户账号"
          extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openAccountModal()}>
                添加用户账号
              </Button>
            </Space>
          }
        >
          <Table
            rowKey="id"
            loading={loading}
            dataSource={accounts}
            columns={[
              { title: '平台', dataIndex: 'platform', width: 100, render: (v) => <Tag>{String(v).toUpperCase()}</Tag> },
              { title: '账号名', dataIndex: 'account_name', render: (value, record) => value || record.display_name || '-' },
              { title: '显示名', dataIndex: 'display_name', render: (value, record) => value || record.account_name || '-' },
              {
                title: '底层 ID',
                dataIndex: 'remote_user_id',
                render: (value) => value ? (
                  <Tooltip title={value}>
                    <Text type="secondary">{String(value).length > 18 ? `${String(value).slice(0, 8)}...${String(value).slice(-6)}` : value}</Text>
                  </Tooltip>
                ) : '-',
              },
              { title: '状态', dataIndex: 'enabled', width: 90, render: (v) => v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag> },
              {
                title: '操作',
                width: 120,
                render: (_, record) => (
                  <Space>
                    <Button icon={<EditOutlined />} onClick={() => openAccountModal(record)} />
                    <Button danger icon={<DeleteOutlined />} onClick={() => deleteAccount(record)} />
                  </Space>
                ),
              },
            ]}
            pagination={{ pageSize: 8 }}
          />
        </Card>

        <Card
          title="伴侣账号"
          extra={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openAIModal()}>
              添加伴侣账号
            </Button>
          }
        >
          <Table
            rowKey="id"
            loading={loading}
            dataSource={aiAccounts}
            columns={[
              { title: '伴侣名称', dataIndex: 'companion_name', render: (value, record) => value || record.account_name || '-' },
              {
                title: '平台账号',
                render: (_, record) => {
                  const platforms = getPlatformAccounts(record)
                  if (!platforms.length) return '-'
                  return (
                    <Space wrap>
                      {platforms.map((item) => (
                        <Tag key={`${record.id}-${item.platform}-${item.account_name}`}>
                          {String(item.platform).toUpperCase()}: {item.account_name}
                        </Tag>
                      ))}
                    </Space>
                  )
                },
              },
              {
                title: '绑定用户账号',
                render: (_, record) => {
                  const bound = getBoundAccounts(record)
                  if (!bound.length) return <Text type="secondary">未绑定</Text>
                  return (
                    <Space wrap>
                      {bound.map((item) => <Tag key={item.id} color="blue">{accountLabel(item)}</Tag>)}
                    </Space>
                  )
                },
              },
              { title: '运行状态', dataIndex: 'enabled', width: 100, render: (v) => v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
              {
                title: '操作',
                width: 120,
                render: (_, record) => (
                  <Space>
                    <Button icon={<EditOutlined />} onClick={() => openAIModal(record)} />
                    <Button danger icon={<DeleteOutlined />} onClick={() => deleteAIAccount(record)} />
                  </Space>
                ),
              },
            ]}
            pagination={{ pageSize: 8 }}
          />
        </Card>

        <Card title="绑定关系">
          <Table
            rowKey="id"
            loading={loading}
            dataSource={aiAccounts}
            columns={[
              { title: '伴侣', render: (_, record) => aiLabel(record) },
              {
                title: '平台账号',
                render: (_, record) => {
                  const platforms = getPlatformAccounts(record)
                  if (!platforms.length) return '-'
                  return platforms.map((item) => `${String(item.platform).toUpperCase()}:${item.account_name}`).join(' / ')
                },
              },
              {
                title: '可聊天的用户账号',
                render: (_, record) => (
                  <Select
                    mode="multiple"
                    style={{ width: '100%', minWidth: 320 }}
                    placeholder="选择一个或多个可绑定的用户账号"
                    options={userAccountOptions}
                    value={record.bound_account_ids || []}
                    onChange={(nextIds) => updateBindings(record.id, nextIds)}
                    optionFilterProp="label"
                  />
                ),
              },
            ]}
            pagination={false}
          />
        </Card>
      </Space>

      <Modal
        title={editingAccount ? '编辑用户账号' : '添加用户账号'}
        open={accountModalOpen}
        onOk={saveAccount}
        confirmLoading={saving}
        onCancel={() => setAccountModalOpen(false)}
        destroyOnHidden
      >
        <Form form={accountForm} layout="vertical">
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select options={[{ value: 'linyu', label: 'Linyu' }, { value: 'qq', label: 'QQ' }]} />
          </Form.Item>
          <Form.Item
            name="account_name"
            label="账号名"
            rules={[{ required: true, message: '请输入账号名' }]}
          >
            <Input placeholder="Linyu 账号名或 QQ 号" autoComplete="off" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名">
            <Input placeholder="留空时使用账号名" autoComplete="off" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingAI ? '编辑伴侣账号' : '添加伴侣账号'}
        open={aiModalOpen}
        onOk={saveAI}
        confirmLoading={saving}
        onCancel={() => setAIModalOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form form={aiForm} layout="vertical">
          <Form.Item name="companion_name" label="伴侣名称">
            <Input placeholder="例如：小雨" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="linyu_account_name"
            label="Linyu 登录账号"
          >
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="linyu_password" label="Linyu 登录密码">
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="qq_account_name" label="QQ 账号">
            <Input autoComplete="off" placeholder="可选，作为同一伴侣的 QQ 账号" />
          </Form.Item>
          <Form.Item name="bound_account_ids" label="绑定用户账号">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择可与该伴侣聊天的用户账号"
              options={userAccountOptions}
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="enabled" label="启用运行" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default AccountsPage
