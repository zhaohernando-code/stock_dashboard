import {
  Alert,
  Card,
  Collapse,
  Col,
  Descriptions,
  Empty,
  List,
  Progress,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type {
  ShortpickCandidateView,
  ShortpickPaperTrackingResponse,
  ShortpickRoundView,
  ShortpickRunView,
  ShortpickValidationView,
} from "../types";
import { formatDate, formatPercent, valueTone } from "../utils/format";
import {
  benchmarkLabel,
  benchmarkMetric,
  benchmarkPendingText,
  failureCategoryLabel,
  operationalStatus,
  priorityLabel,
  roundModelLabel,
  sourceAuthorityLabel,
  sourceCredibilityColor,
  sourceCredibilityLabel,
  sourceSupportLabel,
  statusColor,
  statusLabel,
  validationSummary,
  validationWindowNote,
} from "./shortpickLabLabels";
import { paperTrackingAlertType } from "./shortpickLabPaperTracking";
import { primaryBenchmarkLabel, recordValue, validationCoverage } from "./shortpickLabReplayMetrics";

const { Text, Title } = Typography;

export function TodayRunTab({
  run,
  paperTracking,
  paperTrackingLoading,
  normalCandidates,
  failedCandidates,
  failedRounds,
  loading,
  candidateColumns,
  selectedBenchmark,
}: {
  run: ShortpickRunView;
  paperTracking: ShortpickPaperTrackingResponse | null;
  paperTrackingLoading: boolean;
  normalCandidates: ShortpickCandidateView[];
  failedCandidates: ShortpickCandidateView[];
  failedRounds: ShortpickRoundView[];
  loading: boolean;
  candidateColumns: ColumnsType<ShortpickCandidateView>;
  selectedBenchmark: string;
}) {
  const llmControlCandidate = normalCandidates.find((item) => item.tracking_role === "llm_paper_control_primary");
  const llmControl = llmControlCandidate?.llm_paper_control ?? {};
  const llmAccountFilterRule = String(
    llmControl.account_filter_rule ?? "仅允许沪深主板普通A股；排除科创板、创业板、北交所、ST/退市风险类标的。",
  );
  const llmSelectionRule = String(
    llmControl.selection_rule ?? "先过滤到新开户普通现金账户可买范围；再优先跨模型同票，其次同模型重复、跨模型同题材、单模型高置信、系统外新视角；再按来源质量、置信度、来源数量、股票代码和候选ID稳定排序。",
  );
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
            <span>LLM 对照状态</span>
            <strong>{priorityLabel(run.consensus?.research_priority ?? "pending")}</strong>
            <Text type="secondary">只用于和冻结策略对比</Text>
          </div>
        </Col>
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>LLM 验证覆盖</span>
            <strong>{validationCoverage(run)}</strong>
            <Text type="secondary">主基准：{primaryBenchmarkLabel(run)}</Text>
          </div>
        </Col>
      </Row>

      <FrozenRunStatus run={run} normalCandidates={normalCandidates} paperTracking={paperTracking} loading={paperTrackingLoading} />

      <Card className="panel-card" title="LLM纸面对照标的" extra={<Tag color="blue">每日固定规则选1只</Tag>}>
        {llmControlCandidate ? (
          <Descriptions size="small" column={{ xs: 1, md: 3 }}>
            <Descriptions.Item label="纸面对照">{llmControlCandidate.name} · {llmControlCandidate.symbol}</Descriptions.Item>
            <Descriptions.Item label="原始优先级">{priorityLabel(llmControlCandidate.research_priority)}</Descriptions.Item>
            <Descriptions.Item label="验证口径">同一入场，三轨退出</Descriptions.Item>
            <Descriptions.Item label="账户过滤" span={3}>
              {llmAccountFilterRule}
            </Descriptions.Item>
            <Descriptions.Item label="选择规则" span={3}>
              {llmSelectionRule}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="本批次尚未形成LLM纸面对照标的；下一次完整LLM批次会按固定规则提前选出1只。" />
        )}
      </Card>

      {failedRounds.length || failedCandidates.length ? (
        <FailureDiagnostics failedRounds={failedRounds} failedCandidates={failedCandidates} selectedBenchmark={selectedBenchmark} />
      ) : null}

      <Card
        className="panel-card"
        title="LLM 对照组收敛"
        extra={<Tag color="default">不作为主策略</Tag>}
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
                {recordValue<Record<string, string>>(run.consensus.summary, "leader_theme_labels")
                  ? Object.values(recordValue<Record<string, string>>(run.consensus.summary, "leader_theme_labels") ?? {}).join(" / ") || "--"
                  : Array.isArray(run.consensus.summary.leader_themes)
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

      <Card className="panel-card" title="对照研究池" extra={<Text type="secondary">LLM 自由选股与动量对照样本</Text>}>
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
                  <ValidationList items={item.validations} selectedBenchmark={selectedBenchmark} />
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

      <Card className="panel-card" title="LLM 原始推荐（对照）">
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

function FrozenRunStatus({
  run,
  normalCandidates,
  paperTracking,
  loading,
}: {
  run: ShortpickRunView;
  normalCandidates: ShortpickCandidateView[];
  paperTracking: ShortpickPaperTrackingResponse | null;
  loading: boolean;
}) {
  const overlay = recordValue<Record<string, unknown>>(run.summary, "market_factor_overlay") ?? {};
  const frozen = recordValue<Record<string, unknown>>(overlay, "frozen_paper_strategy") ?? {};
  const regime = recordValue<Record<string, unknown>>(overlay, "regime") ?? {};
  const frozenCandidate = normalCandidates.find((item) => item.research_priority === "market_factor_frozen_paper");
  const gatePass = Boolean(frozen.gate_pass);
  const inserted = Boolean(frozen.inserted);
  const trackingStatus = paperTracking?.current_status;
  const isWaitingFirstFrozenRun = trackingStatus === "waiting_first_frozen_run" && !Object.keys(frozen).length;
  const alertType = isWaitingFirstFrozenRun ? "warning" : inserted ? "success" : gatePass ? "warning" : paperTrackingAlertType(trackingStatus);
  const alertMessage = isWaitingFirstFrozenRun
    ? "冻结策略已启用，等待首个正式跟踪批次"
    : inserted
      ? "本批次已生成冻结策略标的"
      : gatePass
        ? "启用条件满足，但候选不足"
        : paperTracking?.current_label || "本批次未触发冻结策略";
  const frozenSelectionRule = String(
    frozen.selection_rule ?? "当全市场10日上涨占比不低于45%时，选择20日趋势向上、成交额较高且换手率相对不拥挤的第1名",
  );
  const frozenRiskRule = String(
    frozen.risk_rule ?? "同一入场信号并行记录机械5日、机械10日、止盈止损三条退出轨道。",
  );
  const alertDescription = isWaitingFirstFrozenRun
    ? "当前最新 LLM 对照批次生成于规则冻结前；下一次盘后批次会按冻结规则写入正式纸面跟踪或记录未触发原因。"
    : inserted && frozenCandidate
      ? `本批次纸面跟踪标的：${frozenCandidate.symbol} ${frozenCandidate.name}。规则已冻结：${frozenSelectionRule}。${frozenRiskRule}`
      : paperTracking?.current_message || "冻结策略只在市场转正且候选池不过热时启动；未启动批次也会记录为真实纸面跟踪的一部分。";
  return (
    <Card className="panel-card shortpick-frozen-status" title="正式纸面跟踪（冻结策略）" loading={loading && !paperTracking}>
      <Alert
        showIcon
        type={alertType}
        message={alertMessage}
        description={alertDescription}
      />
      <Row gutter={[12, 12]} className="shortpick-frozen-metrics">
        <Col xs={24} md={8}>
          <div className="shortpick-metric">
            <span>跟踪阶段</span>
            <strong>规则冻结</strong>
            <Text type="secondary">需要40个真实交易日后再评价</Text>
          </div>
        </Col>
        <Col xs={24} md={8}>
          <div className="shortpick-metric">
            <span>市场状态</span>
            <strong>{formatPercent(Number(regime.universe_ret10_mean ?? 0))}</strong>
            <Text type="secondary">全市场10日平均收益</Text>
          </div>
        </Col>
        <Col xs={24} md={8}>
          <div className="shortpick-metric">
            <span>候选池热度</span>
            <strong>{formatPercent(Number(regime.pool_ret1_mean ?? 0))}</strong>
            <Text type="secondary">扩大候选池1日平均涨幅</Text>
          </div>
        </Col>
      </Row>
    </Card>
  );
}

function FailureDiagnostics({
  failedRounds,
  failedCandidates,
  selectedBenchmark,
}: {
  failedRounds: ShortpickRoundView[];
  failedCandidates: ShortpickCandidateView[];
  selectedBenchmark: string;
}) {
  const hasOnlyCandidateDiagnostics = !failedRounds.length && failedCandidates.length > 0;
  return (
    <Card className="panel-card" title="对照组可交易性诊断">
      <Alert
        type={hasOnlyCandidateDiagnostics ? "info" : "warning"}
        showIcon
        message={failedRounds.length ? "本批次存在失败轮次" : "部分 LLM 候选等待下个交易日确认可交易性"}
        description={
          failedRounds.length
            ? "失败轮次、解析失败、停牌/缺行情或入场不可成交候选不会进入正常研究池。可重跑失败轮次；可交易性异常需要等待行情或人工复核。"
            : "这通常来自盘后批次的下一交易日入场校验：如果信号日之后还没有真实交易日 K 线，系统会先隔离这些候选，不把它们计入正常研究池。"
        }
      />
      {failedRounds.length ? (
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
      ) : null}
      {failedCandidates.length ? (
        <Table
          className="shortpick-failure-table"
          rowKey="id"
          size="small"
          columns={[
            {
              title: "标的",
              key: "symbol",
              render: (_, item: ShortpickCandidateView) => <Text strong>{`${item.name} · ${item.symbol}`}</Text>,
            },
            {
              title: "状态",
              key: "status",
              render: (_, item: ShortpickCandidateView) => <Tag color={item.display_bucket === "diagnostic" ? "gold" : "red"}>{validationSummary(item, selectedBenchmark)}</Tag>,
            },
            {
              title: "原因",
              key: "reason",
              render: (_, item: ShortpickCandidateView) => <Text>{item.diagnostic_reason || item.thesis || "--"}</Text>,
            },
          ]}
          dataSource={failedCandidates}
          pagination={false}
        />
      ) : null}
      {failedCandidates.length ? <Text type="secondary">已隔离对照组候选 {failedCandidates.length} 条，等待交易日数据或人工复核后再判断。</Text> : null}
    </Card>
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

export function SourceList({ candidate }: { candidate: ShortpickCandidateView }) {
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
                <Tag>{sourceAuthorityLabel(source.authority_class)}</Tag>
                <Tag color={source.support_status === "supported_by_source_text" ? "green" : "gold"}>
                  {sourceSupportLabel(source.support_status)}
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

export function ValidationList({ items, selectedBenchmark }: { items: ShortpickValidationView[]; selectedBenchmark: string }) {
  if (!items.length) {
    return <Text type="secondary">暂无验证窗口。</Text>;
  }
  return (
    <List
      size="small"
      dataSource={items}
      renderItem={(item) => {
        const metric = benchmarkMetric(item, selectedBenchmark);
        return (
          <List.Item>
            <Space direction="vertical" size={0}>
              <Space wrap>
                <Tag color={statusColor(item.status)}>{item.horizon_days}日 · {statusLabel(item.status)}</Tag>
                <Text className={`value-${valueTone(item.stock_return)}`}>个股收益 {formatPercent(item.stock_return)}</Text>
                {metric.status === "available" ? (
                  <>
                    <Text className={`value-${valueTone(metric.excess_return)}`}>超额收益 {formatPercent(metric.excess_return)}</Text>
                    <Text type="secondary">{metric.benchmark_label || benchmarkLabel(selectedBenchmark)} {formatPercent(metric.benchmark_return)}</Text>
                  </>
                ) : (
                  <Text type="secondary">{metric.benchmark_label || benchmarkLabel(selectedBenchmark)} · {benchmarkPendingText(metric.status, metric.reason)}</Text>
                )}
                <Text type="secondary">{item.exit_at ? formatDate(item.exit_at) : "等待窗口"}</Text>
                <Text type="secondary">浮盈 {formatPercent(item.max_favorable_return)} / 回撤 {formatPercent(item.max_drawdown)}</Text>
              </Space>
              {validationWindowNote(item) ? <Text type="secondary">{validationWindowNote(item)}</Text> : null}
            </Space>
          </List.Item>
        );
      }}
    />
  );
}
