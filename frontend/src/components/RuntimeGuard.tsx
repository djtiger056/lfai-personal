import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Space, Typography } from 'antd'

const { Paragraph, Text, Title } = Typography

type CrashInfo = {
  source: 'render' | 'error' | 'unhandledrejection'
  message: string
  stack?: string
}

type ErrorBoundaryProps = {
  children: React.ReactNode
  onCrash: (info: CrashInfo) => void
}

type ErrorBoundaryState = {
  hasError: boolean
}

class RootErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    this.props.onCrash({
      source: 'render',
      message: error?.message || '页面渲染失败',
      stack: [error?.stack, info?.componentStack].filter(Boolean).join('\n'),
    })
  }

  render() {
    if (this.state.hasError) {
      return null
    }
    return this.props.children
  }
}

const normalizeCrashMessage = (reason: unknown): { message: string; stack?: string } => {
  if (reason instanceof Error) {
    return {
      message: reason.message || '前端运行时异常',
      stack: reason.stack,
    }
  }
  if (typeof reason === 'string') {
    return { message: reason }
  }
  if (reason && typeof reason === 'object') {
    try {
      return { message: JSON.stringify(reason) }
    } catch {
      return { message: '前端运行时异常' }
    }
  }
  return { message: '前端运行时异常' }
}

const CrashFallback: React.FC<{ crash: CrashInfo; onReload: () => void; onResetSession: () => void }> = ({
  crash,
  onReload,
  onResetSession,
}) => (
  <div
    style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
      background: '#f5f5f5',
    }}
  >
    <Card style={{ width: '100%', maxWidth: 760 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <div>
          <Title level={3} style={{ marginBottom: 8 }}>
            前端页面发生异常
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            已阻止整页直接空白。请先刷新重试；如果反复出现，再根据下面的异常信息继续排查。
          </Paragraph>
        </div>

        <Alert
          type="error"
          showIcon
          message={crash.message || '未知前端异常'}
          description={`异常来源: ${crash.source} | 页面: ${window.location.pathname}`}
        />

        {crash.stack ? (
          <div
            style={{
              background: '#141414',
              color: '#f5f5f5',
              borderRadius: 6,
              padding: 12,
              maxHeight: 280,
              overflow: 'auto',
              fontFamily: 'Consolas, Monaco, monospace',
              fontSize: 12,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {crash.stack}
          </div>
        ) : (
          <Text type="secondary">当前未捕获到堆栈信息。</Text>
        )}

        <Space wrap>
          <Button type="primary" onClick={onReload}>
            刷新页面
          </Button>
          <Button onClick={onResetSession}>
            清理本地会话后刷新
          </Button>
        </Space>
      </Space>
    </Card>
  </div>
)

const RuntimeGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [crash, setCrash] = useState<CrashInfo | null>(null)

  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      const info = normalizeCrashMessage(event.error || event.message)
      console.error('[RuntimeGuard:error]', event.error || event.message)
      setCrash((prev) => prev || { source: 'error', message: info.message, stack: info.stack })
    }

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const info = normalizeCrashMessage(event.reason)
      console.error('[RuntimeGuard:unhandledrejection]', event.reason)
      setCrash((prev) => prev || { source: 'unhandledrejection', message: info.message, stack: info.stack })
    }

    window.addEventListener('error', handleError)
    window.addEventListener('unhandledrejection', handleUnhandledRejection)
    return () => {
      window.removeEventListener('error', handleError)
      window.removeEventListener('unhandledrejection', handleUnhandledRejection)
    }
  }, [])

  const handleBoundaryCrash = (info: CrashInfo) => {
    console.error('[RuntimeGuard:render]', info.message, info.stack)
    setCrash((prev) => prev || info)
  }

  if (crash) {
    return (
      <CrashFallback
        crash={crash}
        onReload={() => window.location.reload()}
        onResetSession={() => {
          try {
            localStorage.removeItem('token')
            localStorage.removeItem('user')
          } catch (error) {
            console.error('[RuntimeGuard:reset-session]', error)
          }
          window.location.reload()
        }}
      />
    )
  }

  return <RootErrorBoundary onCrash={handleBoundaryCrash}>{children}</RootErrorBoundary>
}

export default RuntimeGuard
