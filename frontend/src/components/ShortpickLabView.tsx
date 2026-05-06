import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  Input,
  List,
  Progress,
  Row,
  Col,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import { ExperimentOutlined, ReloadOutlined, SafetyCertificateOutlined, SyncOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type {
  ShortpickCandidateView,
  ShortpickFeedbackGroup,
  ShortpickModelFeedbackItem,
  ShortpickModelFeedbackResponse,
  ShortpickRoundView,
  ShortpickRunView,
  ShortpickValidationQueueItem,
  ShortpickValidationQueueResponse,
  ShortpickValidationView,
} from "../types";
import { formatDate, formatPercent, valueTone } from "../utils/format";

const { Paragraph, Text, Title } = Typography;
const DEFAULT_VALIDATION_PAGE_SIZE = 50;

function priorityLabel(value: string): string {
  if (value === "high_convergence") return "高收敛";
  if (value === "theme_convergence") return "题材收敛";
  if (value === "divergent_novel") return "发散新颖";
  if (value === "watch_only") return "观察";
  return "待聚合";
}

function priorityColor(value: string): string {
  if (value === "high_convergence") return "red";
  if (value === "theme_convergence") return "gold";
  if (value === "divergent_novel") return "blue";
  if (value === "watch_only") return "default";
  return "default";
}

function statusColor(value: string): string {
  if (value === "completed" || value === "success") return "green";
  if (value === "running") return "blue";
  if (value === "failed" || value === "parse_failed" || value === "retryable_failures") return "red";
  if (value === "partial_completed" || value.startsWith("pending")) return "gold";
  return "default";
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    completed: "已完成",
    running: "运行中",
    failed: "失败",
    partial_completed: "部分完成",
    retryable_failures: "失败待重跑",
    parsed: "已解析",
    parse_failed: "解析失败",
    pending_market_data: "待行情",
    pending_forward_window: "待窗口",
    pending_entry_bar: "待入场价",
    pending_benchmark_data: "待基准",
  };
  return labels[value] ?? value;
}

function failureCategoryLabel(value?: string | null): string {
  if (value === "retryable_search_failure") return "搜索失败，可重跑";
  if (value === "retryable_parse_failure") return "解析失败，可重跑";
  if (value === "configuration_failure") return "配置失败";
  if (value === "round_execution_failure") return "执行失败";
  return "未分类失败";
}

function roundModelLabel(round: ShortpickRoundView): string {
  return `${round.provider_name}:${round.model_name} #${round.round_index}`;
}

function validationSummary(candidate: ShortpickCandidateView): string {
  const completed = candidate.validations.filter((item) => item.status === "completed");
  if (!completed.length) {
    const pending = candidate.validations[0];
    return pending ? statusLabel(pending.status) : "待验证";
  }
  const shortest = completed[0];
  return `${shortest.horizon_days}日 个股 ${formatPercent(shortest.stock_return)} / 沪深300超额 ${formatPercent(shortest.excess_return)}`;
}

function recordValue<T>(record: Record<string, unknown> | undefined, key: string): T | undefined {
  return record?.[key] as T | undefined;
}

function validationCoverage(run: ShortpickRunView): string {
  const completed = Number(run.summary.validation_completed_count ?? run.summary.completed_validation_count ?? 0);
  const total = Number(run.summary.validation_total_count ?? 0);
  if (total) return `${completed} / ${total}`;
  const counts = recordValue<Record<string, number>>(run.summary, "validation_status_counts") ?? {};
  const derivedTotal = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
  return `${completed} / ${derivedTotal}`;
}

function primaryBenchmarkLabel(run: ShortpickRunView): string {
  const primary = recordValue<Record<string, string>>(run.summary, "primary_benchmark");
  return primary?.label || "沪深300";
}

function operationalStatus(run: ShortpickRunView): string {
  return String(run.summary.operational_status ?? run.status);
}

function sourceCredibilityLabel(value?: string | null): string {
  if (value === "verified") return "来源可达";
  if (value === "reachable_restricted") return "来源受限";
  if (value === "suspicious") return "疑似占位";
  if (value === "unreachable") return "不可达";
  if (value === "missing_url") return "缺 URL";
  return "未校验";
}

function sourceCredibilityColor(value?: string | null): string {
  if (value === "verified") return "green";
  if (value === "reachable_restricted") return "gold";
  if (value === "suspicious" || value === "unreachable" || value === "missing_url") return "red";
  return "default";
}

export function ShortpickLabView({ canTrigger }: { canTrigger: boolean }) {
  const [runs, setRuns] = useState<ShortpickRunView[]>([]);
  const [selectedRun, setSelectedRun] = useState<ShortpickRunView | null>(null);
  const [candidates, setCandidates] = useState<ShortpickCandidateView[]>([]);
  const [validationQueue, setValidationQueue] = useState<ShortpickValidationQueueResponse | null>(null);
  const [feedback, setFeedback] = useState<ShortpickModelFeedbackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [validationLoading, setValidationLoading] = useState(false);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationFilters, setValidationFilters] = useState({ status: "", horizon: "", model: "", symbol: "" });
  const [validationPage, setValidationPage] = useState({ current: 1, pageSize: DEFAULT_VALIDATION_PAGE_SIZE });

  const latestRun = selectedRun ?? runs[0] ?? null;
  const normalCandidates = useMemo(
    () => candidates.filter((item) => item.parse_status === "parsed" && item.symbol !== "PARSE_FAILED"),
    [candidates],
  );
  const failedCandidates = useMemo(
    () => candidates.filter((item) => item.parse_status !== "parsed" || item.symbol === "PARSE_FAILED"),
    [candidates],
  );
  const failedRounds = useMemo(
    () => (latestRun?.rounds ?? []).filter((item) => item.status === "failed"),
    [latestRun],
  );

  async function loadLab(runId?: number): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const runList = await api.getShortpickRuns({ limit: 20 });
      const targetRunId = runId ?? selectedRun?.id ?? runList.data.items[0]?.id;
      const target = runList.data.items.find((item) => item.id === targetRunId) ?? runList.data.items[0] ?? null;
      setRuns(runList.data.items);
      setSelectedRun(target);
      if (target) {
        const candidateList = await api.getShortpickCandidates({ runId: target.id, limit: 100 });
        setCandidates(candidateList.data.items);
      } else {
        setCandidates([]);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载短投推荐试验田失败。");
    } finally {
      setLoading(false);
    }
  }

  async function loadValidationQueue(page = validationPage.current, pageSize = validationPage.pageSize): Promise<void> {
    setValidationLoading(true);
    try {
      const result = await api.getShortpickValidationQueue({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        status: validationFilters.status || undefined,
        horizon: validationFilters.horizon ? Number(validationFilters.horizon) : undefined,
        model: validationFilters.model || undefined,
        symbol: validationFilters.symbol || undefined,
      });
      setValidationQueue(result.data);
      setValidationPage({ current: page, pageSize });
    } catch (queueError) {
      setError(queueError instanceof Error ? queueError.message : "加载历史验证失败。");
    } finally {
      setValidationLoading(false);
    }
  }

  async function loadFeedback(): Promise<void> {
    setFeedbackLoading(true);
    try {
      const result = await api.getShortpickModelFeedback();
      setFeedback(result.data);
    } catch (feedbackError) {
      setError(feedbackError instanceof Error ? feedbackError.message : "加载模型反馈失败。");
    } finally {
      setFeedbackLoading(false);
    }
  }

  async function handleCreateRun(): Promise<void> {
    setAction("run");
    setError(null);
    try {
      const result = await api.createShortpickRun({ rounds_per_model: 5 });
      await loadLab(result.data.id);
      await loadValidationQueue(1, validationPage.pageSize);
      await loadFeedback();
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "触发短投推荐实验失败。");
    } finally {
      setAction(null);
    }
  }

  async function handleValidateRun(): Promise<void> {
    if (!latestRun) return;
    setAction("validate");
    setError(null);
    try {
      await api.validateShortpickRun(latestRun.id, { horizons: [1, 3, 5, 10, 20] });
      await loadLab(latestRun.id);
      await loadValidationQueue(validationPage.current, validationPage.pageSize);
      await loadFeedback();
    } catch (validateError) {
      setError(validateError instanceof Error ? validateError.message : "补跑后验复盘失败。");
    } finally {
      setAction(null);
    }
  }

  async function handleRetryFailedRounds(): Promise<void> {
    if (!latestRun) return;
    setAction("retry");
    setError(null);
    try {
      await api.retryShortpickFailedRounds(latestRun.id, {});
      await loadLab(latestRun.id);
      await loadValidationQueue(validationPage.current, validationPage.pageSize);
      await loadFeedback();
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "重跑失败轮次失败。");
    } finally {
      setAction(null);
    }
  }

  useEffect(() => {
    void loadLab();
    void loadValidationQueue(1, DEFAULT_VALIDATION_PAGE_SIZE);
    void loadFeedback();
  }, []);

  const candidateColumns: ColumnsType<ShortpickCandidateView> = [
    {
      title: "研究标的",
      dataIndex: "symbol",
      key: "symbol",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.name} · {item.symbol}</Text>
          <Text type="secondary">{item.normalized_theme || "未归类题材"}</Text>
        </Space>
      ),
    },
    {
      title: "优先级",
      dataIndex: "research_priority",
      key: "research_priority",
      render: (value: string, item) => (
        <Space wrap>
          <Tag color={priorityColor(value)}>{priorityLabel(value)}</Tag>
          {item.is_system_external ? <Tag color="blue">系统外新视角</Tag> : <Tag>系统内已覆盖</Tag>}
        </Space>
      ),
    },
    {
      title: "模型理由",
      dataIndex: "thesis",
      key: "thesis",
      render: (value: string | null) => <Text>{value || "--"}</Text>,
    },
    {
      title: "验证",
      key: "validation",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{validationSummary(item)}</Text>
          <Text type="secondary">完成前不得显示为 verified</Text>
        </Space>
      ),
    },
  ];

  const validationColumns: ColumnsType<ShortpickValidationQueueItem> = [
    {
      title: "批次 / 标的",
      key: "stock",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.name} · {item.symbol}</Text>
          <Text type="secondary">{item.run_date} · {item.provider_name || "--"}:{item.model_name || "--"}</Text>
        </Space>
      ),
    },
    {
      title: "周期",
      dataIndex: "horizon_days",
      key: "horizon_days",
      render: (value: number) => <Tag>{value}日</Tag>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={statusColor(value)}>{statusLabel(value)}</Tag>,
    },
    {
      title: "收益反馈",
      key: "returns",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text className={`value-${valueTone(item.excess_return)}`}>超额收益 {formatPercent(item.excess_return)}</Text>
          <Text type="secondary">个股 {formatPercent(item.stock_return)} / {item.benchmark_label || "沪深300"} {formatPercent(item.benchmark_return)}</Text>
        </Space>
      ),
    },
    {
      title: "窗口",
      key: "window",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{item.entry_at ? formatDate(item.entry_at) : "等待入场"} → {item.exit_at ? formatDate(item.exit_at) : "等待窗口"}</Text>
          <Text type="secondary">浮盈 {formatPercent(item.max_favorable_return)} / 回撤 {formatPercent(item.max_drawdown)}</Text>
        </Space>
      ),
    },
  ];

  const feedbackColumns: ColumnsType<ShortpickModelFeedbackItem> = [
    {
      title: "模型",
      key: "model",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.provider_name}:{item.model_name}</Text>
          <Text type="secondary">{item.executor_kind}</Text>
        </Space>
      ),
    },
    {
      title: "轮次质量",
      key: "rounds",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{item.completed_round_count} / {item.round_count} 成功</Text>
          <Text type="secondary">失败 {item.failed_round_count} · 可重跑 {item.retryable_failed_round_count} · 解析失败 {item.parse_failed_candidate_count}</Text>
        </Space>
      ),
    },
    {
      title: "成功率",
      dataIndex: "success_rate",
      key: "success_rate",
      render: (value?: number | null) => <Text>{formatPercent(value)}</Text>,
    },
    {
      title: "来源质量",
      key: "sources",
      render: (_, item) => (
        <Space wrap>
          {Object.entries(item.source_credibility_counts).map(([key, value]) => (
            <Tag key={key} color={sourceCredibilityColor(key)}>{sourceCredibilityLabel(key)} {value}</Tag>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <section className="shortpick-lab">
      <Card className="panel-card shortpick-lab-header">
        <div className="shortpick-lab-title">
          <div>
            <Paragraph className="topbar-kicker">Short Pick Lab</Paragraph>
            <Title level={3}>短投推荐试验田</Title>
            <Paragraph className="panel-description">
              独立研究课题，不进入主推荐评分；模型一致性只代表研究优先级，不代表交易建议；后验验证完成前不得显示为已验证能力。
            </Paragraph>
          </div>
          <Space wrap>
            <Select
              className="shortpick-run-select"
              value={latestRun?.id}
              placeholder="选择历史批次"
              options={runs.map((run) => ({
                value: run.id,
                label: `${run.run_date} · ${statusLabel(operationalStatus(run))}`,
              }))}
              onChange={(runId) => void loadLab(Number(runId))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => {
              void loadLab(latestRun?.id);
              void loadValidationQueue(validationPage.current, validationPage.pageSize);
              void loadFeedback();
            }} loading={loading || validationLoading || feedbackLoading}>
              刷新
            </Button>
            {canTrigger ? (
              <>
                <Button
                  type="primary"
                  icon={<ExperimentOutlined />}
                  loading={action === "run"}
                  onClick={() => void handleCreateRun()}
                >
                  触发实验
                </Button>
                <Button
                  icon={<SyncOutlined />}
                  disabled={!latestRun}
                  loading={action === "validate"}
                  onClick={() => void handleValidateRun()}
                >
                  补跑复盘
                </Button>
                <Button
                  danger
                  disabled={!latestRun || !failedRounds.some((item) => item.retryable)}
                  loading={action === "retry"}
                  onClick={() => void handleRetryFailedRounds()}
                >
                  重跑失败轮次
                </Button>
              </>
            ) : null}
          </Space>
        </div>
        {error ? <Alert type="error" showIcon message={error} /> : null}
      </Card>

      {!latestRun && !loading ? (
        <Card className="panel-card">
          <Empty description="暂无短投推荐实验批次" />
        </Card>
      ) : null}

      {latestRun ? (
        <Tabs
          className="shortpick-workspace-tabs"
          items={[
            {
              key: "today",
              label: "今日批次",
              children: (
                <TodayRunTab
                  run={latestRun}
                  normalCandidates={normalCandidates}
                  failedCandidates={failedCandidates}
                  failedRounds={failedRounds}
                  loading={loading}
                  candidateColumns={candidateColumns}
                />
              ),
            },
            {
              key: "validation",
              label: "历史验证",
              children: (
                <ValidationQueueTab
                  filters={validationFilters}
                  onFiltersChange={setValidationFilters}
                  onSearch={() => void loadValidationQueue(1, validationPage.pageSize)}
                  queue={validationQueue}
                  loading={validationLoading}
                  columns={validationColumns}
                  page={validationPage}
                  onPageChange={(pagination) => {
                    void loadValidationQueue(pagination.current ?? 1, pagination.pageSize ?? DEFAULT_VALIDATION_PAGE_SIZE);
                  }}
                />
              ),
            },
            {
              key: "feedback",
              label: "模型反馈",
              children: <ModelFeedbackTab feedback={feedback} loading={feedbackLoading} columns={feedbackColumns} />,
            },
          ]}
        />
      ) : null}

      <Alert
        type="info"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message="隔离规则"
        description="短投推荐实验只写入 shortpick_lab 数据域和 artifact，不写入现有候选池、自选池、量化推荐、模拟盘自动调仓或生产权重。来源可达只代表 URL/访问层校验，不等于权威来源。"
      />
    </section>
  );
}

function TodayRunTab({
  run,
  normalCandidates,
  failedCandidates,
  failedRounds,
  loading,
  candidateColumns,
}: {
  run: ShortpickRunView;
  normalCandidates: ShortpickCandidateView[];
  failedCandidates: ShortpickCandidateView[];
  failedRounds: ShortpickRoundView[];
  loading: boolean;
  candidateColumns: ColumnsType<ShortpickCandidateView>;
}) {
  return (
    <>
      <Row gutter={[16, 16]} className="shortpick-metrics">
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>最近批次</span>
            <strong>{run.run_date}</strong>
            <Tag color={statusColor(operationalStatus(run))}>{statusLabel(operationalStatus(run))}</Tag>
          </div>
        </Col>
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>完成 / 失败轮次</span>
            <strong>{Number(run.summary.completed_round_count ?? 0)} / {Number(run.summary.failed_round_count ?? 0)}</strong>
            <Text type="secondary">{Number(run.summary.retryable_failed_round_count ?? 0)} 个可重跑</Text>
          </div>
        </Col>
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>综合优先级</span>
            <strong>{priorityLabel(run.consensus?.research_priority ?? "pending")}</strong>
            <Text type="secondary">研究池排序信号</Text>
          </div>
        </Col>
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>验证覆盖</span>
            <strong>{validationCoverage(run)}</strong>
            <Text type="secondary">主基准：{primaryBenchmarkLabel(run)}</Text>
          </div>
        </Col>
      </Row>

      {failedRounds.length ? <FailureDiagnostics failedRounds={failedRounds} failedCandidates={failedCandidates} /> : null}

      <Card
        className="panel-card"
        title="今日收敛结果"
        extra={<Tag color={priorityColor(run.consensus?.research_priority ?? "pending")}>{priorityLabel(run.consensus?.research_priority ?? "pending")}</Tag>}
      >
        {run.consensus ? (
          <>
            <Row gutter={[20, 16]}>
              <Col xs={24} md={8}>
                <Progress percent={Math.round(run.consensus.stock_convergence * 100)} size="small" />
                <Text>单票收敛</Text>
              </Col>
              <Col xs={24} md={8}>
                <Progress percent={Math.round(run.consensus.theme_convergence * 100)} size="small" />
                <Text>题材收敛</Text>
              </Col>
              <Col xs={24} md={8}>
                <Progress percent={Math.round(run.consensus.source_diversity * 100)} size="small" />
                <Text>来源多样性</Text>
              </Col>
            </Row>
            <Descriptions className="shortpick-consensus-desc" size="small" column={{ xs: 1, md: 3 }}>
              <Descriptions.Item label="领先股票">
                {Array.isArray(run.consensus.summary.leader_symbols)
                  ? (run.consensus.summary.leader_symbols as string[]).join(" / ") || "--"
                  : "--"}
              </Descriptions.Item>
              <Descriptions.Item label="领先题材">
                {Array.isArray(run.consensus.summary.leader_themes)
                  ? (run.consensus.summary.leader_themes as string[]).join(" / ") || "--"
                  : "--"}
              </Descriptions.Item>
              <Descriptions.Item label="解释">
                {String(run.consensus.summary.interpretation ?? "模型一致性只代表研究优先级。")}
              </Descriptions.Item>
            </Descriptions>
          </>
        ) : (
          <Empty description="等待聚合结果" />
        )}
      </Card>

      <Card className="panel-card" title="研究池">
        <Table
          rowKey="id"
          size="middle"
          loading={loading}
          columns={candidateColumns}
          dataSource={normalCandidates}
          pagination={{ pageSize: 8 }}
          expandable={{
            expandedRowRender: (item) => (
              <div className="shortpick-detail-grid">
                <div>
                  <Title level={5}>催化与风险</Title>
                  <List size="small" dataSource={[...item.catalysts, ...item.risks]} renderItem={(text) => <List.Item>{text}</List.Item>} />
                </div>
                <div>
                  <Title level={5}>后验复盘</Title>
                  <ValidationList items={item.validations} />
                </div>
                <div>
                  <Title level={5}>来源与留痕</Title>
                  <SourceList candidate={item} />
                </div>
              </div>
            ),
          }}
        />
      </Card>

      <Card className="panel-card" title="模型原始推荐">
        <Table
          rowKey="id"
          size="middle"
          loading={loading}
          columns={roundColumns()}
          dataSource={run.rounds}
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </>
  );
}

function FailureDiagnostics({
  failedRounds,
  failedCandidates,
}: {
  failedRounds: ShortpickRoundView[];
  failedCandidates: ShortpickCandidateView[];
}) {
  return (
    <Card className="panel-card" title="失败诊断">
      <Alert
        type="warning"
        showIcon
        message="本批次存在失败轮次"
        description="失败轮次不会进入正常研究池。DeepSeek/SearXNG 无结果或 JSON 解析失败可重跑；配置类失败需要先修复模型配置。"
      />
      <Table
        className="shortpick-failure-table"
        rowKey="id"
        size="small"
        columns={[
          {
            title: "轮次",
            key: "round",
            render: (_, item: ShortpickRoundView) => <Text strong>{roundModelLabel(item)}</Text>,
          },
          {
            title: "分类",
            key: "category",
            render: (_, item: ShortpickRoundView) => <Tag color={item.retryable ? "gold" : "red"}>{failureCategoryLabel(item.failure_category)}</Tag>,
          },
          {
            title: "错误",
            dataIndex: "error_message",
            key: "error_message",
            render: (value?: string | null) => <Text>{value || "--"}</Text>,
          },
        ]}
        dataSource={failedRounds}
        pagination={false}
      />
      {failedCandidates.length ? <Text type="secondary">已隔离异常候选 {failedCandidates.length} 条，包含 PARSE_FAILED，不参与正常候选统计。</Text> : null}
    </Card>
  );
}

function ValidationQueueTab({
  filters,
  onFiltersChange,
  onSearch,
  queue,
  loading,
  columns,
  page,
  onPageChange,
}: {
  filters: { status: string; horizon: string; model: string; symbol: string };
  onFiltersChange: (filters: { status: string; horizon: string; model: string; symbol: string }) => void;
  onSearch: () => void;
  queue: ShortpickValidationQueueResponse | null;
  loading: boolean;
  columns: ColumnsType<ShortpickValidationQueueItem>;
  page: { current: number; pageSize: number };
  onPageChange: (pagination: TablePaginationConfig) => void;
}) {
  return (
    <Card className="panel-card" title="历史验证">
      <Space wrap className="shortpick-filter-bar">
        <Select
          allowClear
          placeholder="验证状态"
          value={filters.status || undefined}
          options={[
            { value: "pending_forward_window", label: "待窗口" },
            { value: "pending_entry_bar", label: "待入场价" },
            { value: "pending_market_data", label: "待行情" },
            { value: "pending_benchmark_data", label: "待基准" },
            { value: "completed", label: "已完成" },
          ]}
          onChange={(value) => onFiltersChange({ ...filters, status: value ?? "" })}
        />
        <Select
          allowClear
          placeholder="周期"
          value={filters.horizon || undefined}
          options={[1, 3, 5, 10, 20].map((value) => ({ value: String(value), label: `${value}日` }))}
          onChange={(value) => onFiltersChange({ ...filters, horizon: value ?? "" })}
        />
        <Input
          className="shortpick-filter-input"
          placeholder="模型"
          value={filters.model}
          onChange={(event) => onFiltersChange({ ...filters, model: event.target.value })}
        />
        <Input
          className="shortpick-filter-input"
          placeholder="股票代码"
          value={filters.symbol}
          onChange={(event) => onFiltersChange({ ...filters, symbol: event.target.value })}
        />
        <Button onClick={onSearch} loading={loading}>查询</Button>
      </Space>
      <Table
        rowKey="validation_id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={queue?.items ?? []}
        pagination={{
          current: page.current,
          pageSize: page.pageSize,
          total: queue?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: [20, 50, 100],
        }}
        onChange={onPageChange}
      />
    </Card>
  );
}

function ModelFeedbackTab({
  feedback,
  loading,
  columns,
}: {
  feedback: ShortpickModelFeedbackResponse | null;
  loading: boolean;
  columns: ColumnsType<ShortpickModelFeedbackItem>;
}) {
  const overall = feedback?.overall ?? {};
  return (
    <>
      <Row gutter={[16, 16]} className="shortpick-metrics">
        <Col xs={24} md={6}>
          <Statistic title="批次数" value={Number(overall.run_count ?? 0)} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="模型轮次" value={Number(overall.round_count ?? 0)} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="正常候选" value={Number(overall.candidate_count ?? 0)} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="验证快照" value={Number(overall.validation_count ?? 0)} />
        </Col>
      </Row>
      <Card className="panel-card" title="模型反馈">
        <Table
          rowKey={(item) => `${item.provider_name}:${item.model_name}:${item.executor_kind}`}
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={feedback?.models ?? []}
          expandable={{
            expandedRowRender: (item) => <FeedbackDetails item={item} />,
          }}
          pagination={false}
        />
      </Card>
    </>
  );
}

function FeedbackDetails({ item }: { item: ShortpickModelFeedbackItem }) {
  return (
    <div className="shortpick-feedback-detail">
      <FeedbackGroupList title="周期表现" groups={item.validation_by_horizon} />
      <FeedbackGroupList title="优先级表现" groups={item.validation_by_priority} />
      <FeedbackGroupList title="题材表现" groups={item.validation_by_theme} />
    </div>
  );
}

function FeedbackGroupList({ title, groups }: { title: string; groups: ShortpickFeedbackGroup[] }) {
  return (
    <div>
      <Title level={5}>{title}</Title>
      <List
        size="small"
        dataSource={groups}
        renderItem={(group) => (
          <List.Item>
            <Space wrap>
              <Text strong>{group.label}</Text>
              <Text>样本 {group.completed_validation_count}/{group.sample_count}</Text>
              <Text className={`value-${valueTone(group.mean_excess_return)}`}>平均超额 {formatPercent(group.mean_excess_return)}</Text>
              <Text>正超额 {formatPercent(group.positive_excess_rate)}</Text>
              <Text type="secondary">最大回撤 {formatPercent(group.max_drawdown)}</Text>
            </Space>
          </List.Item>
        )}
      />
    </div>
  );
}

function roundColumns(): ColumnsType<ShortpickRoundView> {
  return [
    {
      title: "模型轮次",
      key: "model",
      render: (_, item) => <Text strong>{roundModelLabel(item)}</Text>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={statusColor(value)}>{statusLabel(value)}</Tag>,
    },
    {
      title: "推荐",
      key: "pick",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{item.stock_name && item.symbol ? `${item.stock_name} · ${item.symbol}` : "--"}</Text>
          <Text type="secondary">{item.theme || "未归类"}</Text>
        </Space>
      ),
    },
    {
      title: "理由",
      dataIndex: "thesis",
      key: "thesis",
      render: (value: string | null) => <Text>{value || "--"}</Text>,
    },
  ];
}

function SourceList({ candidate }: { candidate: ShortpickCandidateView }) {
  return (
    <>
      <List
        size="small"
        dataSource={candidate.sources}
        renderItem={(source) => (
          <List.Item>
            <Space direction="vertical" size={0}>
              <Space wrap>
                <a href={source.url || undefined} target="_blank" rel="noreferrer">{source.title || source.url || "未命名来源"}</a>
                <Tag color={sourceCredibilityColor(source.credibility_status)}>
                  {sourceCredibilityLabel(source.credibility_status)}
                  {source.http_status ? ` ${source.http_status}` : ""}
                </Tag>
              </Space>
              <Text type="secondary">{source.published_at || "发布时间未声明"} · {source.why_it_matters || "未说明"}</Text>
              {source.credibility_reason ? <Text type="secondary">校验：{source.credibility_reason}</Text> : null}
            </Space>
          </List.Item>
        )}
      />
      {candidate.raw_round?.raw_answer ? (
        <Collapse
          className="shortpick-raw-collapse"
          items={[{
            key: "raw",
            label: "原始模型输出",
            children: <pre className="shortpick-raw-answer">{candidate.raw_round?.raw_answer}</pre>,
          }]}
        />
      ) : null}
    </>
  );
}

function ValidationList({ items }: { items: ShortpickValidationView[] }) {
  if (!items.length) {
    return <Text type="secondary">暂无验证窗口。</Text>;
  }
  return (
    <List
      size="small"
      dataSource={items}
      renderItem={(item) => (
        <List.Item>
          <Space wrap>
            <Tag color={statusColor(item.status)}>{item.horizon_days}日 · {statusLabel(item.status)}</Tag>
            <Text className={`value-${valueTone(item.stock_return)}`}>个股收益 {formatPercent(item.stock_return)}</Text>
            <Text className={`value-${valueTone(item.excess_return)}`}>超额收益 {formatPercent(item.excess_return)}</Text>
            <Text type="secondary">{item.benchmark_label || "沪深300"} {formatPercent(item.benchmark_return)}</Text>
            <Text type="secondary">{item.exit_at ? formatDate(item.exit_at) : "等待窗口"}</Text>
            <Text type="secondary">浮盈 {formatPercent(item.max_favorable_return)} / 回撤 {formatPercent(item.max_drawdown)}</Text>
          </Space>
        </List.Item>
      )}
    />
  );
}
