import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  Progress,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  ShortpickV2ConfigReadout,
  ShortpickV2HistoricalReplayResponse,
  ShortpickV2PaperDisplayChart,
  ShortpickV2PaperDisplayTableColumn,
  ShortpickV2PaperDisplayTableRow,
  ShortpickV2PaperDisplayTextItem,
  ShortpickV2PaperTrackingResponse,
} from "../types";
import { formatDate, formatNumber, formatPercent, valueTone } from "../utils/format";
import { readRouteParam, writeWorkbenchRoute } from "../utils/route";

const { Paragraph, Text, Title } = Typography;
type ShortpickV2Tab = "paper-tracking" | "historical-replay";
const SHORTPICK_V2_TABS = new Set<ShortpickV2Tab>(["paper-tracking", "historical-replay"]);

function initialShortpickV2Tab(): ShortpickV2Tab {
  const rawTab = readRouteParam("shortpickV2Tab");
  return rawTab && SHORTPICK_V2_TABS.has(rawTab as ShortpickV2Tab)
    ? rawTab as ShortpickV2Tab
    : "paper-tracking";
}

function numberField(source: Record<string, unknown> | undefined, key: string): number | null {
  const value = source?.[key];
  return typeof value === "number" ? value : null;
}

function stringField(source: Record<string, unknown> | undefined, key: string): string {
  const value = source?.[key];
  return typeof value === "string" ? value : "";
}

function configRoleLabel(role?: string | null): string {
  if (role === "phase5_contract_candidate") return "候选配置";
  if (role === "baseline_control") return "基线";
  if (role === "holdout") return "留出观察";
  if (role === "rejected") return "未采用";
  return role ? "未标注角色" : "未标注";
}

function configRoleColor(role?: string | null): string {
  if (role === "phase5_contract_candidate") return "green";
  if (role === "baseline_control") return "blue";
  if (role === "holdout") return "gold";
  if (role === "rejected") return "red";
  return "default";
}

function actionLabel(action?: string | null): string {
  if (action === "buy_primary") return "买入首选";
  if (action === "buy_fallback") return "买入候补";
  if (action === "skip") return "不买";
  return action ? "未识别动作" : "未记录";
}

function actionColor(action?: string | null): string {
  if (action === "buy_primary") return "green";
  if (action === "buy_fallback") return "cyan";
  if (action === "skip") return "gold";
  return "default";
}

function statusColor(value?: string | null): string {
  if (value === "ready" || value === "active" || value === "passed") return "green";
  if (value === "contract_ready" || value === "baseline_control") return "blue";
  if (value === "failed" || value === "blocked") return "red";
  if (value === "holdout") return "gold";
  return "default";
}

function artifactShortRef(source?: Record<string, unknown>): string {
  const artifactId = stringField(source, "artifact_id");
  if (artifactId) return "已记录来源";
  const path = stringField(source, "path");
  return path ? "已记录来源" : "暂无来源";
}

function readableStatusLabel(value?: string | null): string {
  if (value === "contract_ready") return "已满足展示合同";
  if (value === "ready") return "已就绪";
  if (value === "active") return "跟踪中";
  if (value === "passed") return "已通过";
  if (value === "failed") return "未通过";
  if (value === "blocked") return "暂不可用";
  if (value === "baseline_control") return "基线对照";
  if (value === "holdout") return "留出观察";
  if (value === "research_observation") return "研究观察";
  if (value === "true_forward_tracking") return "真实前向跟踪";
  if (value === "historical_account_replay") return "历史账户回放";
  if (value === "historical_account_replay_selection") return "历史账户回放筛选";
  return value ? "未命名状态" : "暂无状态";
}

function reasonLabel(value?: string | null): string {
  if (value === "bought_primary") return "首选标的满足资金和整手要求。";
  if (value === "bought_fallback") return "首选不满足要求，改买当天候补标的。";
  if (value === "insufficient_cash") return "可用现金不足，无法买满一手。";
  if (value === "board_lot_minimum") return "不足 100 股整手要求。";
  if (value === "cash_reserve") return "触发现金保留约束。";
  if (value === "position_count_cap") return "持仓数量已经达到上限。";
  if (value === "position_value_cap") return "单一标的仓位上限已满。";
  if (value === "limit_up_unfillable") return "入场日涨停不可成交。";
  if (value === "no_ranked_candidates") return "当天没有满足条件的候选。";
  if (value === "no_executable_candidate") return "当天候选都不满足买入约束。";
  return value ? "按既定规则完成判断。" : "暂无说明。";
}

function configReadableLabel(configId?: string | null): string {
  if (configId === "quiet_r2_poolhot10_mtw__fixed85_top5_v1") return "8.5 万目标买入方案";
  if (configId === "quiet_r2_poolhot10_mtw__fixed80_top5_v1") return "8 万目标买入方案";
  if (configId === "top1_or_skip_v1") return "首位候选对照策略";
  if (configId === "top3_fallback_v1") return "前三候选对照策略";
  if (configId === "fixed_notional_40k_top5_v1") return "4 万目标买入旧候选策略";
  if (configId === "conservative_cash_reserve_60k_top5_v1") return "保留 6 万现金的旧候选策略";
  if (configId === "position_cap_utilization_top5_v1") return "仓位上限旧候选策略";
  return configId ? "未命名策略" : "暂无策略";
}

function displayValue(value: unknown, fallback = "暂无"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function appendPaperSummaryCard(
  cards: ShortpickV2PaperDisplayTextItem[],
  label: string,
  value: unknown,
): ShortpickV2PaperDisplayTextItem[] {
  if (cards.some((item) => item.label === label)) return cards;
  return [...cards, { label, value: displayValue(value) }];
}

function tagColorByTone(tone?: string | null): string {
  if (tone === "success") return "green";
  if (tone === "warning") return "gold";
  if (tone === "error") return "red";
  if (tone === "info") return "blue";
  return "default";
}

function chartPercent(value: number, maxValue: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(maxValue) || maxValue <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((value / maxValue) * 100)));
}

function ConfigSummaryTable({
  rows,
  loading,
}: {
  rows: ShortpickV2ConfigReadout[];
  loading: boolean;
}) {
  const columns: ColumnsType<ShortpickV2ConfigReadout> = [
    {
      title: "配置",
      key: "config",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{configReadableLabel(item.config_id)}</Text>
          <Space wrap size={4}>
            <Tag color={configRoleColor(item.role)}>{configRoleLabel(item.role)}</Tag>
            <Tag color={statusColor(item.gate_status)}>{readableStatusLabel(item.gate_status) || "未过闸"}</Tag>
          </Space>
        </Space>
      ),
    },
    {
      title: "账户结果",
      key: "return",
      render: (_, item) => {
        const totalReturn = numberField(item.summary, "total_return");
        const maxDrawdown = numberField(item.summary, "max_drawdown");
        return (
          <Space direction="vertical" size={0}>
            <Text className={`value-${valueTone(totalReturn)}`}>{formatPercent(totalReturn)}</Text>
            <Text type="secondary">最大回撤 {formatPercent(maxDrawdown)}</Text>
          </Space>
        );
      },
    },
    {
      title: "执行",
      key: "execution",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>交易 {formatNumber(numberField(item.summary, "trade_count"))}</Text>
          <Text type="secondary">
            跳过 {formatNumber(numberField(item.summary, "skip_count"))}
            {" · "}
            候补 {formatNumber(numberField(item.summary, "fallback_trade_count"))}
          </Text>
        </Space>
      ),
    },
    {
      title: "说明",
      dataIndex: "reason",
      key: "reason",
      render: (value?: string | null) => <Text>{reasonLabel(value)}</Text>,
    },
  ];
  return (
    <Table
      className="shortpick-v2-config-table"
      rowKey={(item, index) => `config-summary-${configRoleLabel(item.role)}-${index ?? 0}`}
      size="small"
      loading={loading}
      pagination={false}
      columns={columns}
      dataSource={rows}
    />
  );
}

function ShortpickV2PaperTab({
  tracking,
  loading,
  onReload,
}: {
  tracking: ShortpickV2PaperTrackingResponse | null;
  loading: boolean;
  onReload: () => void;
}) {
  const display = tracking?.paper_display;
  const latestTrade = display?.latest_trade;
  const strategyExplanation = display?.strategy_explanation;
  const charts = display?.charts ?? [];
  const table = display?.table;
  const tableRows = table?.rows ?? [];
  const tableColumns = paperDisplayTableColumns(table?.columns ?? []);
  const baseSummaryCards = display?.summary_cards ?? [
    { label: "真实前向记录", value: numberField(tracking?.summary, "true_forward_record_count") ?? 0 },
    { label: "回放展示行", value: numberField(tracking?.summary, "replay_record_count") ?? 0 },
    { label: "覆盖起点", value: stringField(display?.coverage, "coverage_start") || "2026-05-08" },
    { label: "最新来源信号日", value: stringField(display?.coverage, "latest_source_signal_date") || "暂无" },
  ];
  const summaryCards = appendPaperSummaryCard(
    appendPaperSummaryCard(
      baseSummaryCards,
      "覆盖终点",
      stringField(display?.coverage, "coverage_end") || stringField(display?.coverage, "latest_source_signal_date") || "暂无",
    ),
    "数据缺口",
    numberField(display?.coverage, "source_gap_count") ?? numberField(tracking?.summary, "display_source_gap_count") ?? 0,
  );
  const pageStatus = display?.status_label || readableStatusLabel(tracking?.status);
  const pageSubtitle = display?.subtitle || tracking?.data_disclaimer || "暂无纸面追踪展示数据。";
  return (
    <div className="panel-stack shortpick-v2-tab-body">
      <Card
        className="panel-card"
        title={display?.title || "试验田v2纸面追踪"}
        extra={<Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>刷新</Button>}
      >
        {loading && !tracking ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          <>
            <Alert
              showIcon
              type={tracking?.status === "blocked" ? "warning" : tracking?.status === "contract_ready" ? "info" : "success"}
              message={pageStatus}
              description={pageSubtitle}
            />
            <div className="metric-strip shortpick-v2-metrics">
              {summaryCards.map((item) => (
                <div className="metric-strip-item" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{displayValue(item.value)}</strong>
                </div>
              ))}
            </div>
            <Space wrap className="inline-tags">
              <Tag color="blue">回放补齐不计入真实前向收益</Tag>
              <Tag color="red">不允许延迟买入</Tag>
              <Tag color="green">研究观察，不构成建议</Tag>
            </Space>
          </>
        )}
      </Card>

      <Card
        className="panel-card"
        title={latestTrade?.title || "最新模拟交易"}
        extra={latestTrade?.tag ? <Tag color={latestTrade.tag === "回放" ? "gold" : "green"}>{latestTrade.tag}</Tag> : null}
      >
        {loading && !tracking ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : (
          <Space direction="vertical" size="middle" className="full-width">
            <Paragraph className="panel-description">{latestTrade?.summary || "暂无可展示的模拟交易。"}</Paragraph>
            <div className="metric-strip shortpick-v2-metrics">
              {(latestTrade?.items ?? []).map((item) => (
                <div className="metric-strip-item" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{displayValue(item.value)}</strong>
                </div>
              ))}
            </div>
            {latestTrade?.note ? <Text type="secondary">{latestTrade.note}</Text> : null}
          </Space>
        )}
      </Card>

      <Card className="panel-card" title={strategyExplanation?.title || "策略说明"}>
        {loading && !tracking ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          <Space direction="vertical" size="middle" className="full-width">
            {(strategyExplanation?.items ?? []).map((item) => (
              <div className="shortpick-v2-explanation-row" key={item.label}>
                <Text strong>{item.label}</Text>
                <Paragraph className="panel-description">{displayValue(item.value)}</Paragraph>
              </div>
            ))}
          </Space>
        )}
      </Card>

      <div className="shortpick-v2-chart-grid">
        {charts.length ? charts.map((chart) => <PaperDisplayChartCard key={chart.title || chart.kind} chart={chart} />) : (
          <Card className="panel-card" title="图表">
            <Empty description="暂无可展示的图表数据。" />
          </Card>
        )}
      </div>

      <Card className="panel-card" title={table?.title || "模拟交易明细"}>
        {tableRows.length ? (
          <Table
            rowKey={(_item, index) => `paper-display-row-${index ?? 0}`}
            size="small"
            columns={tableColumns}
            dataSource={tableRows}
            pagination={{ pageSize: 20 }}
          />
        ) : (
          <Empty description={table?.empty_text || "暂无可展示的纸面追踪记录。"} />
        )}
      </Card>
    </div>
  );
}

function PaperDisplayChartCard({ chart }: { chart: ShortpickV2PaperDisplayChart }) {
  const points = chart.data ?? [];
  const maxValue = Math.max(...points.map((item) => item.value), 0);
  return (
    <Card className="panel-card" title={chart.title || "图表"}>
      <Space direction="vertical" size="middle" className="full-width">
        {chart.subtitle ? <Text type="secondary">{chart.subtitle}</Text> : null}
        {points.length ? points.map((item) => (
          <div className="shortpick-v2-chart-row" key={item.name}>
            <Space className="full-width" direction="vertical" size={2}>
              <Space className="full-width" style={{ justifyContent: "space-between" }}>
                <Text>{item.name}</Text>
                <Text strong>{formatNumber(item.value)}</Text>
              </Space>
              <Progress percent={chartPercent(item.value, maxValue)} showInfo={false} size="small" />
            </Space>
          </div>
        )) : <Empty description="暂无图表数据。" />}
      </Space>
    </Card>
  );
}

function paperDisplayTableColumns(
  sourceColumns: ShortpickV2PaperDisplayTableColumn[],
): ColumnsType<ShortpickV2PaperDisplayTableRow> {
  const fallbackColumns: ShortpickV2PaperDisplayTableColumn[] = [
    { key: "signal_date_text", label: "信号日" },
    { key: "tracking_tag", label: "记录类型" },
    { key: "strategy_text", label: "策略" },
    { key: "action_text", label: "动作" },
    { key: "reason_text", label: "原因" },
    { key: "stock_text", label: "标的" },
    { key: "selected_rank_text", label: "入选位置" },
    { key: "quantity_text", label: "数量" },
    { key: "cash_after_text", label: "剩余现金" },
    { key: "note", label: "说明" },
  ];
  return (sourceColumns.length ? sourceColumns : fallbackColumns).map((column) => ({
    title: column.label,
    key: column.key,
    render: (_, item) => paperDisplayTableCell(column.key, item),
  }));
}

function paperDisplayTableCell(key: string, item: ShortpickV2PaperDisplayTableRow) {
  if (key === "tracking_tag") {
    return <Tag color={tagColorByTone(item.tracking_tag_tone)}>{displayValue(item.tracking_tag)}</Tag>;
  }
  if (key === "action_text") {
    return <Text strong>{displayValue(item.action_text)}</Text>;
  }
  if (key === "note") {
    return <Text type="secondary">{displayValue(item.note)}</Text>;
  }
  return <Text>{displayValue(item[key])}</Text>;
}

function ShortpickV2ReplayTab({
  replay,
  loading,
  onReload,
}: {
  replay: ShortpickV2HistoricalReplayResponse | null;
  loading: boolean;
  onReload: () => void;
}) {
  const selectedRows = replay?.selected_configs ?? [];
  const baselineRows = replay?.baseline_configs ?? [];
  const holdoutRows = replay?.holdout_configs ?? [];
  const rejectedRows = replay?.rejected_configs ?? [];
  const samples = useMemo(
    () => selectedRows.flatMap((config) => (
      config.decision_samples.map((sample) => ({ ...sample, config_id: config.config_id }))
    )),
    [selectedRows],
  );
  const sampleColumns: ColumnsType<Record<string, unknown>> = [
    {
      title: "信号日",
      key: "signal_date",
      render: (_, item) => <Text>{String(item.signal_date ?? "--")}</Text>,
    },
    {
      title: "配置",
      key: "config",
      render: (_, item) => <Text>{configReadableLabel(String(item.config_id ?? ""))}</Text>,
    },
    {
      title: "动作 / 原因",
      key: "action",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Tag color={actionColor(String(item.action ?? ""))}>{actionLabel(String(item.action ?? ""))}</Tag>
          <Text type="secondary">{reasonLabel(String(item.reason ?? ""))}</Text>
        </Space>
      ),
    },
    {
      title: "标的 / 排名",
      key: "symbol",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{String(item.symbol ?? "--")}</Text>
          <Text type="secondary">入选位置 {displayValue(item.selected_rank, "无")}</Text>
        </Space>
      ),
    },
    {
      title: "资金 / 数量",
      key: "cash",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>后 {formatNumber(typeof item.cash_after === "number" ? item.cash_after : null)}</Text>
          <Text type="secondary">数量 {formatNumber(typeof item.quantity === "number" ? item.quantity : null)}</Text>
        </Space>
      ),
    },
  ];
  return (
    <div className="panel-stack shortpick-v2-tab-body">
      <Card
        className="panel-card"
        title="历史回放核心读数"
        extra={<Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>刷新</Button>}
      >
        {loading && !replay ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          <>
            <div className="metric-strip shortpick-v2-metrics">
              <div className="metric-strip-item">
                <span>信号日</span>
                <strong>{formatNumber(numberField(replay?.summary, "signal_day_count"))}</strong>
              </div>
              <div className="metric-strip-item">
                <span>交易日</span>
                <strong>{formatNumber(numberField(replay?.summary, "trade_day_count"))}</strong>
              </div>
              <div className="metric-strip-item">
                <span>入选配置</span>
                <strong>{formatNumber(numberField(replay?.summary, "selected_config_count"))}</strong>
              </div>
              <div className="metric-strip-item">
                <span>覆盖状态</span>
                <strong>{readableStatusLabel(String(replay?.summary?.coverage_status ?? ""))}</strong>
              </div>
            </div>
            <Space wrap className="inline-tags">
              <Tag color={statusColor(replay?.status)}>{readableStatusLabel(replay?.status)}</Tag>
              <Tag color="green">{readableStatusLabel(replay?.claim_ceiling)}</Tag>
              <Tag color="blue">{readableStatusLabel(replay?.evidence_basis)}</Tag>
              <Tag>生成 {formatDate(replay?.generated_at)}</Tag>
              <Tag>回放来源 {artifactShortRef(replay?.source_artifacts?.replay)}</Tag>
            </Space>
            <Paragraph type="secondary" className="panel-description">
              {replay?.data_disclaimer || "历史回放读取固定来源文件，不构成投资建议。"}
            </Paragraph>
          </>
        )}
      </Card>

      <Card className="panel-card" title={selectedRows.length ? "推广配置与基线" : "合格配置与基线"}>
        <ConfigSummaryTable rows={[...selectedRows, ...baselineRows]} loading={loading} />
      </Card>

      <Collapse
        className="shortpick-v2-reference-collapse"
        items={[
          {
            key: "holdout",
            label: "留出与未采用配置",
            children: <ConfigSummaryTable rows={[...holdoutRows, ...rejectedRows]} loading={loading} />,
          },
          {
            key: "samples",
            label: "决策样本",
            children: samples.length ? (
              <Table
                rowKey={(_item, index) => `decision-sample-${index ?? 0}`}
                size="small"
                columns={sampleColumns}
                dataSource={samples}
                pagination={false}
              />
            ) : (
              <Empty description="暂无决策样本" />
            ),
          },
        ]}
      />
    </div>
  );
}

export function ShortpickLabV2View() {
  const [activeTab, setActiveTab] = useState<ShortpickV2Tab>(() => initialShortpickV2Tab());
  const activeTabRef = useRef<ShortpickV2Tab>(activeTab);
  const [paperTracking, setPaperTracking] = useState<ShortpickV2PaperTrackingResponse | null>(null);
  const [historicalReplay, setHistoricalReplay] = useState<ShortpickV2HistoricalReplayResponse | null>(null);
  const [paperLoading, setPaperLoading] = useState(false);
  const [replayLoading, setReplayLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPaperTracking(): Promise<void> {
    setPaperLoading(true);
    setError(null);
    try {
      const result = await api.getShortpickV2PaperTracking();
      setPaperTracking(result.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载 v2 纸面追踪失败。");
    } finally {
      setPaperLoading(false);
    }
  }

  async function loadHistoricalReplay(): Promise<void> {
    setReplayLoading(true);
    setError(null);
    try {
      const result = await api.getShortpickV2HistoricalReplay(5);
      setHistoricalReplay(result.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载 v2 历史回放失败。");
    } finally {
      setReplayLoading(false);
    }
  }

  function loadActiveTab(tab: ShortpickV2Tab): void {
    if (tab === "paper-tracking") {
      void loadPaperTracking();
    } else {
      void loadHistoricalReplay();
    }
  }

  useEffect(() => {
    loadActiveTab(activeTab);
  }, []);

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  useEffect(() => {
    function handlePopState(): void {
      const nextTab = initialShortpickV2Tab();
      if (activeTabRef.current === nextTab) return;
      activeTabRef.current = nextTab;
      setActiveTab(nextTab);
      loadActiveTab(nextTab);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    writeWorkbenchRoute({ view: "shortpick-v2", shortpickV2Tab: activeTab }, "replace");
  }, [activeTab]);

  return (
    <section className="shortpick-lab-v2 panel-stack">
      <Card className="panel-card shortpick-v2-header">
        <div className="shortpick-header-main">
          <Space direction="vertical" size={4}>
            <Title level={3}>试验田v2</Title>
            <Text type="secondary">资金约束账户路径研究</Text>
          </Space>
          <Space wrap className="inline-tags">
            <Tag color="green">研究观察，不构成建议</Tag>
            <Tag color="blue">20万资金约束</Tag>
            <Tag color="purple">100股手数</Tag>
            <Tag color="red">不延迟买入</Tag>
          </Space>
        </div>
        <Alert
          className="sub-alert"
          showIcon
          icon={<SafetyCertificateOutlined />}
          type="info"
          message="只读研究口径"
          description="页面只读取 v2 后端只读接口；不触发回放生成、行情刷新、模型调用、纸面记录写入或参数搜索。"
        />
      </Card>

      {error ? <Alert type="error" showIcon message={error} /> : null}

      <Tabs
        className="shortpick-v2-tabs"
        activeKey={activeTab}
        onChange={(key) => {
          if (!SHORTPICK_V2_TABS.has(key as ShortpickV2Tab)) return;
          const nextTab = key as ShortpickV2Tab;
          activeTabRef.current = nextTab;
          writeWorkbenchRoute({ view: "shortpick-v2", shortpickV2Tab: nextTab }, "push");
          setActiveTab(nextTab);
          loadActiveTab(nextTab);
        }}
        items={[
          {
            key: "paper-tracking",
            label: "纸面追踪",
            children: (
              <ShortpickV2PaperTab
                tracking={paperTracking}
                loading={paperLoading}
                onReload={() => void loadPaperTracking()}
              />
            ),
          },
          {
            key: "historical-replay",
            label: "历史回放",
            children: (
              <ShortpickV2ReplayTab
                replay={historicalReplay}
                loading={replayLoading}
                onReload={() => void loadHistoricalReplay()}
              />
            ),
          },
        ]}
      />
    </section>
  );
}
