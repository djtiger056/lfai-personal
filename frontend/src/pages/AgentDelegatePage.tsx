import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Switch,
  Button,
  Space,
  message,
  InputNumber,
  Typography,
  Divider,
  Alert,
  Row,
  Col,
  Spin,
  Tag,
  Badge,
} from 'antd';
import {
  RocketOutlined,
  ExperimentOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { agentDelegateConfigProxy } from '@/services/configProxy';
import api from '@/services/api';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface HermesConfig {
  api_base: string;
  api_key: string;
  timeout: number;
  poll_interval: number;
  max_concurrent_tasks: number;
  instructions: string;
}

interface AgentDelegateConfig {
  enabled: boolean;
  hermes: HermesConfig;
}

interface DelegateStatus {
  initialized: boolean;
  enabled: boolean;
  active_tasks: number;
  tasks: any[];
  hermes_online: boolean;
}

const AgentDelegatePage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [config, setConfig] = useState<AgentDelegateConfig>({
    enabled: false,
    hermes: {
      api_base: 'http://127.0.0.1:8642',
      api_key: '',
      timeout: 300,
      poll_interval: 3,
      max_concurrent_tasks: 5,
      instructions: '',
    },
  });
  const [status, setStatus] = useState<DelegateStatus | null>(null);

  useEffect(() => {
    loadConfig();
    loadStatus();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const data = await agentDelegateConfigProxy.getConfig();
      setConfig(data);
      form.setFieldsValue(data);
    } catch (error: any) {
      console.error('加载配置失败:', error);
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const loadStatus = async () => {
    try {
      setStatusLoading(true);
      const response = await api.get('/agent-delegate/status');
      if (response.data.success) {
        setStatus(response.data.data);
      }
    } catch (error: any) {
      console.error('加载状态失败:', error);
    } finally {
      setStatusLoading(false);
    }
  };

  const saveConfig = async (values: AgentDelegateConfig) => {
    try {
      setLoading(true);
      await agentDelegateConfigProxy.updateConfig(values);
      message.success('配置保存成功，重启后生效');
      await loadConfig();
    } catch (error: any) {
      console.error('保存配置失败:', error);
      message.error('配置保存失败');
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    try {
      setTestLoading(true);
      const response = await api.post('/agent-delegate/test-connection');
      if (response.data.success) {
        message.success(response.data.message);
      } else {
        message.error(response.data.message);
      }
    } catch (error: any) {
      message.error('连接测试失败');
    } finally {
      setTestLoading(false);
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>
        <RocketOutlined /> Agent 委派配置
      </Title>

      <Row gutter={[24, 24]}>
        <Col span={16}>
          <Card title="委派设置" loading={loading}>
            <Form
              form={form}
              layout="vertical"
              initialValues={config}
              onFinish={saveConfig}
            >
              <Form.Item
                name="enabled"
                label="启用 Agent 委派"
                valuePropName="checked"
                help="启用后，小馨会将任务型需求自动委派给 Hermes Agent 执行"
              >
                <Switch />
              </Form.Item>

              <Divider>Hermes Agent 连接配置</Divider>

              <Form.Item
                name={['hermes', 'api_base']}
                label="API 地址"
                rules={[{ required: true, message: '请输入 Hermes API 地址' }]}
                help="Hermes Agent 的 HTTP API 地址，默认 http://127.0.0.1:8642"
              >
                <Input placeholder="http://127.0.0.1:8642" />
              </Form.Item>

              <Form.Item
                name={['hermes', 'api_key']}
                label="API 密钥"
                rules={[{ required: true, message: '请输入 API 密钥' }]}
                help="与 Hermes 的 API_SERVER_KEY 环境变量一致"
              >
                <Input.Password placeholder="请输入 Hermes API 密钥" />
              </Form.Item>

              <Divider>任务执行参数</Divider>

              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item
                    name={['hermes', 'timeout']}
                    label="任务超时（秒）"
                    help="单次任务最大等待时间"
                  >
                    <InputNumber min={30} max={1800} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item
                    name={['hermes', 'poll_interval']}
                    label="轮询间隔（秒）"
                    help="检查任务状态的频率"
                  >
                    <InputNumber min={1} max={30} step={0.5} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item
                    name={['hermes', 'max_concurrent_tasks']}
                    label="最大并发任务数"
                    help="同时执行的任务上限"
                  >
                    <InputNumber min={1} max={20} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>

              <Divider>Agent 人格指令</Divider>

              <Form.Item
                name={['hermes', 'instructions']}
                label="Instructions（系统指令）"
                help="发送给 Hermes 的 system instructions，控制其回复风格"
              >
                <TextArea
                  rows={5}
                  placeholder={'你是一个能干的助理。语气亲切自然，称呼用户"你"。\n任务结果该正式就正式（代码用代码块），但可以在开头结尾带一点温度。\n不要撒娇，不要用颜文字。简洁高效地完成任务。'}
                />
              </Form.Item>

              <Divider />
              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    保存配置
                  </Button>
                  <Button
                    icon={<ExperimentOutlined />}
                    onClick={testConnection}
                    loading={testLoading}
                  >
                    测试连接
                  </Button>
                  <Button
                    icon={<SyncOutlined />}
                    onClick={loadStatus}
                    loading={statusLoading}
                  >
                    刷新状态
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </Col>

        <Col span={8}>
          {/* 运行状态卡片 */}
          <Card title="运行状态" loading={statusLoading}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>
                <Text strong>委派器状态：</Text>
                {status ? (
                  <Tag
                    color={status.initialized && status.enabled ? 'green' : 'red'}
                    style={{ marginLeft: '8px' }}
                  >
                    {status.initialized && status.enabled ? '运行中' : '未启动'}
                  </Tag>
                ) : (
                  <Tag color="default" style={{ marginLeft: '8px' }}>未知</Tag>
                )}
              </div>

              <div>
                <Text strong>Hermes 连接：</Text>
                {status ? (
                  status.hermes_online ? (
                    <Tag icon={<CheckCircleOutlined />} color="success" style={{ marginLeft: '8px' }}>
                      在线
                    </Tag>
                  ) : (
                    <Tag icon={<CloseCircleOutlined />} color="error" style={{ marginLeft: '8px' }}>
                      离线
                    </Tag>
                  )
                ) : (
                  <Tag color="default" style={{ marginLeft: '8px' }}>未知</Tag>
                )}
              </div>

              <div>
                <Text strong>活跃任务：</Text>
                <Badge
                  count={status?.active_tasks || 0}
                  showZero
                  style={{ marginLeft: '8px' }}
                />
              </div>

              {status?.tasks && status.tasks.length > 0 && (
                <>
                  <Divider style={{ margin: '12px 0' }} />
                  <Text strong>当前任务：</Text>
                  {status.tasks.map((task: any) => (
                    <Card
                      key={task.run_id}
                      size="small"
                      style={{ marginTop: '8px' }}
                    >
                      <Text ellipsis style={{ display: 'block' }}>
                        {task.task}
                      </Text>
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        耗时: {Math.round(task.elapsed)}秒
                      </Text>
                    </Card>
                  ))}
                </>
              )}
            </Space>
          </Card>

          {/* 功能说明卡片 */}
          <Card title="功能说明" style={{ marginTop: '16px' }}>
            <Alert
              message="Agent 委派系统"
              description={
                <div>
                  <Paragraph>
                    启用后，小馨会将所有任务型需求（查资料、写代码、搜索等）
                    自动委派给 Hermes Agent 执行。小馨只负责聊天和情绪价值。
                  </Paragraph>

                  <Paragraph strong>工作流程：</Paragraph>
                  <ol style={{ paddingLeft: '20px', margin: '8px 0' }}>
                    <li>用户发送任务型消息</li>
                    <li>小馨立即回复（情绪安抚）</li>
                    <li>后台提交任务给 Hermes</li>
                    <li>Hermes 执行完成后推送结果</li>
                  </ol>

                  <Paragraph strong>前置条件：</Paragraph>
                  <ul style={{ paddingLeft: '20px', margin: '8px 0' }}>
                    <li>Hermes Agent 已安装并运行</li>
                    <li>API Server 已开启（端口 8642）</li>
                    <li>API Key 配置正确</li>
                  </ul>
                </div>
              }
              type="info"
              showIcon
              icon={<ApiOutlined />}
            />
          </Card>

          {/* 部署提示 */}
          <Card title="快速部署" style={{ marginTop: '16px' }}>
            <Alert
              message="Hermes 安装命令"
              description={
                <div>
                  <Paragraph code copyable style={{ margin: '4px 0' }}>
                    curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
                  </Paragraph>
                  <Paragraph style={{ margin: '8px 0 4px' }}>
                    开启 API Server（编辑 ~/.hermes/.env）：
                  </Paragraph>
                  <Paragraph code style={{ margin: '4px 0' }}>
                    API_SERVER_ENABLED=true
                  </Paragraph>
                  <Paragraph code style={{ margin: '4px 0' }}>
                    API_SERVER_KEY=your-key
                  </Paragraph>
                  <Paragraph style={{ margin: '8px 0 4px' }}>
                    启动：
                  </Paragraph>
                  <Paragraph code copyable style={{ margin: '4px 0' }}>
                    hermes gateway
                  </Paragraph>
                </div>
              }
              type="warning"
              showIcon
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default AgentDelegatePage;
