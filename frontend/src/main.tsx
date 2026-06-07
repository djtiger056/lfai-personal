import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import RuntimeGuard from './components/RuntimeGuard'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <RuntimeGuard>
        <App />
      </RuntimeGuard>
    </ConfigProvider>
  </React.StrictMode>,
)
