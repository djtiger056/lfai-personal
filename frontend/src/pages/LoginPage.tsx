import React, { useState } from 'react'
import { Button, Card, Form, Input, Typography, message } from 'antd'
import { LockOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const { Title, Text } = Typography

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { verify } = useAuth()
  const from = (location.state as any)?.from?.pathname || '/chat'

  const handleVerify = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      await verify(values.username, values.password)
      message.success('身份验证通过')
      navigate(from, { replace: true })
    } catch (error: any) {
      message.error(error.response?.data?.detail || '身份验证失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#101418',
      padding: 24,
    }}>
      <Card style={{ width: 420, borderRadius: 8 }} styles={{ body: { padding: 32 } }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <RobotOutlined style={{ fontSize: 42, color: '#1677ff', marginBottom: 12 }} />
          <Title level={3} style={{ margin: 0 }}>LFBot 个人控制台</Title>
          <Text type="secondary">请输入配置文件中的管理凭据</Text>
        </div>
        <Form layout="vertical" size="large" onFinish={handleVerify} autoComplete="off">
          <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }]}>
            <Input prefix={<UserOutlined />} placeholder="admin" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="管理密码" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            验证身份
          </Button>
        </Form>
      </Card>
    </div>
  )
}

export default LoginPage
