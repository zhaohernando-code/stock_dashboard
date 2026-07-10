import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Progress,
  Select,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined } from "@ant-design/icons";
import { init } from "echarts";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  ShortpickStrategyLabConfigReadout,
  ShortpickStrategyLabHistoricalReplayResponse,
  ShortpickStrategyLabPaperDisplayAccountCurve,
  ShortpickStrategyLabPaperDisplayChart,
  ShortpickStrategyLabPaperDisplayTableColumn,
  ShortpickStrategyLabPaperDisplayTableRow,
  ShortpickStrategyLabPaperDisplayTextItem,
  ShortpickStrategyLabPaperTrackingResponse,
} from "../types";
import { formatDate, formatNumber, formatPercent, valueTone } from "../utils/format";
import { readRouteParam, writeWorkbenchRoute } from "../utils/route";

const { Paragraph, Text, Title } = Typography;
type ShortpickStrategyLabTab = "paper-tracking" | "historical-replay";
const SHORTPICK_STRATEGY_LAB_TABS = new Set<ShortpickStrategyLabTab>(["paper-tracking", "historical-replay"]);

function initialShortpickStrategyLabTab(): ShortpickStrategyLabTab {
  const rawTab = readRouteParam("shortpickStrategyLabTab");
  return rawTab && SHORTPICK_STRATEGY_LAB_TABS.has(rawTab as ShortpickStrategyLabTab)
    ? rawTab as ShortpickStrategyLabTab
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
  if (role === "primary_forward_observation") return "主策略";
  if (role === "lower_concentration_control") return "低集中对照";
  if (role === "recursive_upstream_rank_weight_candidate") return "递归上游候选";
  if (role === "phase6_forward_observation_candidate") return "前向观察候选";
  if (role === "primary_future_observation_candidate") return "冻结主策略";
  if (role === "capital_shadow_future_observation_candidate") return "资金影子对照";
  if (role === "diagnostic_boundary") return "诊断边界";
  if (role === "legacy_baseline_control") return "旧基线参照";
  if (role === "legacy_holdout") return "旧留出参照";
  if (role === "legacy_rejected") return "旧弱结果参照";
  if (role === "phase5_contract_candidate") return "候选配置";
  if (role === "baseline_control") return "基线";
  if (role === "holdout") return "留出观察";
  if (role === "rejected") return "未采用";
  return role ? "未标注角色" : "未标注";
}

function configRoleColor(role?: string | null): string {
  if (role === "primary_forward_observation") return "green";
  if (role === "lower_concentration_control") return "blue";
  if (role === "recursive_upstream_rank_weight_candidate") return "purple";
  if (role === "phase6_forward_observation_candidate") return "green";
  if (role === "primary_future_observation_candidate") return "green";
  if (role === "capital_shadow_future_observation_candidate") return "blue";
  if (role === "diagnostic_boundary") return "gold";
  if (role?.startsWith("legacy_")) return "default";
  if (role === "phase5_contract_candidate") return "green";
  if (role === "baseline_control") return "blue";
  if (role === "holdout") return "gold";
  if (role === "rejected") return "red";
  return "default";
}

function statusColor(value?: string | null): string {
  if (value === "ready" || value === "active" || value === "passed") return "green";
  if (value === "contract_ready" || value === "baseline_control" || value === "active_control") return "blue";
  if (value === "failed" || value === "blocked") return "red";
  if (value === "holdout" || value === "diagnostic_only") return "gold";
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
  if (value === "awaiting_first_forward_fill") return "等待首笔前向成交";
  if (value === "active_control") return "对照观察中";
  if (value === "static_full_history_ready") return "静态历史指标已就绪";
  if (value === "passed") return "已通过";
  if (value === "failed") return "未通过";
  if (value === "blocked") return "暂不可用";
  if (value === "baseline_control") return "基线对照";
  if (value === "holdout") return "留出观察";
  if (value === "research_observation") return "研究观察";
  if (value === "true_forward_tracking") return "真实前向跟踪";
  if (value === "historical_account_replay") return "历史账户回放";
  if (value === "historical_account_replay_selection") return "历史账户回放筛选";
  if (value === "diagnostic_only") return "仅作诊断";
  if (value === "legacy_reference") return "旧结果参照";
  if (value === "forward_observation_ready_with_open_risks") return "可前向观察，仍有开放风险";
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
  if (configId === "daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1") {
    return "主策略：14 tranche 分层退出";
  }
  if (configId === "daily_15_tranche_rank_weighted_compound_min1000_v1") {
    return "对照组：15 tranche 低集中复投";
  }
  return configId ? "未命名策略" : "暂无策略";
}

function displayValue(value: unknown, fallback = "暂无"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function metricDisplayValue(item: { value?: string | number | null; format?: string | null }): string {
  if (typeof item.value !== "number") return displayValue(item.value);
  if (item.format === "percent") return formatPercent(item.value);
  if (item.format === "currency") return `${formatNumber(item.value)} 元`;
  return formatNumber(item.value);
}

function appendPaperSummaryCard(
  cards: ShortpickStrategyLabPaperDisplayTextItem[],
  label: string,
  value: unknown,
): ShortpickStrategyLabPaperDisplayTextItem[] {
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

function paperRowSearchText(row: ShortpickStrategyLabPaperDisplayTableRow): string {
  return [
    row.signal_date_text,
    row.tracking_tag,
    row.strategy_text,
    row.action_text,
    row.reason_text,
    row.stock_text,
    row.selected_rank_text,
    row.quantity_text,
    row.cash_before_text,
    row.cash_after_text,
    row.exit_state_text,
    row.exit_date_text,
    row.return_text,
    row.note,
  ].map((value) => displayValue(value, "")).join(" ");
}

function uniquePaperOptions(rows: ShortpickStrategyLabPaperDisplayTableRow[], key: string): { label: string; value: string }[] {
  return Array.from(
    new Set(rows.map((row) => displayValue(row[key], "")).filter(Boolean)),
  ).map((value) => ({ label: value, value }));
}

function ConfigSummaryTable({
  rows,
  loading,
}: {
  rows: ShortpickStrategyLabConfigReadout[];
  loading: boolean;
}) {
  const columns: ColumnsType<ShortpickStrategyLabConfigReadout> = [
    {
      title: "配置",
      key: "config",
        render: (_, item) => (
          <Space direction="vertical" size={0}>
          <Text strong>{item.label || "未命名策略"}</Text>
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
      className="shortpick-strategy-lab-config-table"
      rowKey={(item, index) => `config-summary-${configRoleLabel(item.role)}-${index ?? 0}`}
      size="small"
      loading={loading}
      pagination={false}
      columns={columns}
      dataSource={rows}
    />
  );
}

function PaperForwardStrategyTable({
  rows,
  loading,
}: {
  rows: ShortpickStrategyLabConfigReadout[];
  loading: boolean;
}) {
  const columns: ColumnsType<ShortpickStrategyLabConfigReadout> = [
    {
      title: "策略",
      key: "config",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.label || configReadableLabel(item.config_id)}</Text>
          <Space wrap size={4}>
            <Tag color={configRoleColor(item.role)}>{configRoleLabel(item.role)}</Tag>
            <Tag color="blue">从 20 万重新开始</Tag>
          </Space>
        </Space>
      ),
    },
    {
      title: "前向账户",
      key: "forward-account",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>当前净值 {formatNumber(numberField(item.summary, "current_nav_cny"))} 元</Text>
          <Text type="secondary">纸面收益 {formatPercent(numberField(item.summary, "paper_total_return"))}</Text>
        </Space>
      ),
    },
    {
      title: "状态",
      key: "forward-status",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{readableStatusLabel(stringField(item.summary, "forward_status")) || "等待首笔成交"}</Text>
          <Text type="secondary">历史回放收益不计入纸面追踪。</Text>
        </Space>
      ),
    },
  ];
  return (
    <Table
      className="shortpick-strategy-lab-config-table"
      rowKey={(item, index) => `paper-forward-config-${configRoleLabel(item.role)}-${index ?? 0}`}
      size="small"
      loading={loading}
      pagination={false}
      columns={columns}
      dataSource={rows}
    />
  );
}

function plannedOrderText(order: Record<string, unknown>, key: string): string {
  return displayValue(order[key], "");
}

function PlannedOrdersCard({
  orders,
  loading,
  emptyDescription,
}: {
  orders: Record<string, unknown>[];
  loading: boolean;
  emptyDescription?: string;
}) {
  const columns: ColumnsType<Record<string, unknown>> = [
    {
      title: "策略",
      key: "strategy",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{plannedOrderText(item, "strategy_label") || "未命名策略"}</Text>
          <Text type="secondary">信号日 {plannedOrderText(item, "signal_date") || "待生成"}</Text>
        </Space>
      ),
    },
    {
      title: "明日买入",
      key: "buy",
      render: (_, item) => {
        const stock = `${plannedOrderText(item, "name")} · ${plannedOrderText(item, "symbol")}`.replace(/^ · | · $/g, "");
        return (
          <Space direction="vertical" size={0}>
            <Text strong>{stock || "暂无标的"}</Text>
            <Text>
              {plannedOrderText(item, "planned_entry_date") || "待定"}
              {" · "}
              {plannedOrderText(item, "entry_timing") || "次日收盘"}
              {" · 买 "}
              {plannedOrderText(item, "shares") || "0"}
              {" 股"}
            </Text>
          </Space>
        );
      },
    },
    {
      title: "预计占用",
      key: "notional",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{displayValue(item["estimated_notional_cny"])} 元</Text>
          <Text type="secondary">估算价 {displayValue(item["estimated_entry_price_cny"])} 元</Text>
        </Space>
      ),
    },
    {
      title: "说明",
      key: "note",
      render: (_, item) => <Text type="secondary">{plannedOrderText(item, "note") || "按资金池约束生成。"}</Text>,
    },
  ];
  return (
    <Card className="panel-card" title="明日计划单">
      {loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : orders.length ? (
        <Table
          rowKey={(item, index) => `planned-order-${plannedOrderText(item, "strategy_id")}-${plannedOrderText(item, "symbol")}-${index ?? 0}`}
          size="small"
          columns={columns}
          dataSource={orders}
          pagination={false}
        />
      ) : (
        <Empty description={emptyDescription || "暂无明日计划单"} />
      )}
    </Card>
  );
}

function ShortpickStrategyLabPaperTab({
  tracking,
  loading,
  onReload,
}: {
  tracking: ShortpickStrategyLabPaperTrackingResponse | null;
  loading: boolean;
  onReload: () => void;
}) {
  const display = tracking?.paper_display;
  const latestTrade = display?.latest_trade;
  const strategyExplanation = display?.strategy_explanation;
  const charts = display?.charts ?? [];
  const accountCurves = display?.account_curves ?? [];
  const plannedOrders = display?.planned_orders ?? [];
  const table = display?.table;
  const tableRows = table?.rows ?? [];
  const [tableSearch, setTableSearch] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [exitFilter, setExitFilter] = useState("");
  const strategyRows = [
    ...(tracking?.selected_configs ?? []),
    ...(tracking?.baseline_configs ?? []),
  ];
  const strategyOptions = useMemo(() => uniquePaperOptions(tableRows, "strategy_text"), [tableRows]);
  const actionOptions = useMemo(() => uniquePaperOptions(tableRows, "action_text"), [tableRows]);
  const exitOptions = useMemo(() => uniquePaperOptions(tableRows, "exit_state_text"), [tableRows]);
  const filteredTableRows = useMemo(() => {
    const keyword = tableSearch.trim().toLowerCase();
    return tableRows.filter((row) => {
      if (strategyFilter && displayValue(row.strategy_text, "") !== strategyFilter) return false;
      if (actionFilter && displayValue(row.action_text, "") !== actionFilter) return false;
      if (exitFilter && displayValue(row.exit_state_text, "") !== exitFilter) return false;
      if (!keyword) return true;
      return paperRowSearchText(row).toLowerCase().includes(keyword);
    });
  }, [actionFilter, exitFilter, strategyFilter, tableRows, tableSearch]);
  const tableColumns = paperDisplayTableColumns(table?.columns ?? []);
  const baseSummaryCards = display?.summary_cards ?? [
    { label: "真实前向记录", value: numberField(tracking?.summary, "true_forward_record_count") ?? 0 },
    { label: "回放展示行", value: numberField(tracking?.summary, "replay_record_count") ?? 0 },
    { label: "追踪起点", value: stringField(display?.coverage, "coverage_start") || "2026-07-08" },
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
  return (
    <div className="panel-stack shortpick-strategy-lab-tab-body">
      <Card
        className="panel-card"
        title={display?.title || "v3模型纸面追踪"}
        extra={<Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>刷新</Button>}
      >
        {loading && !tracking ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          <>
            <div className="metric-strip shortpick-strategy-lab-metrics">
              {summaryCards.map((item) => (
                <div className="metric-strip-item" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{displayValue(item.value)}</strong>
                </div>
              ))}
            </div>
            <Space wrap className="inline-tags">
              <Tag color="blue">从今日起真实前向</Tag>
              <Tag color="red">不允许延迟买入</Tag>
              <Tag color="green">研究观察，不构成建议</Tag>
            </Space>
          </>
        )}
      </Card>

      <PlannedOrdersCard
        orders={plannedOrders}
        loading={loading && !tracking}
        emptyDescription={latestTrade?.summary || undefined}
      />

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
            <div className="metric-strip shortpick-strategy-lab-metrics">
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
              <div className="shortpick-strategy-lab-explanation-row" key={item.label}>
                <Text strong>{item.label}</Text>
                <Paragraph className="panel-description">{displayValue(item.value)}</Paragraph>
              </div>
            ))}
          </Space>
        )}
      </Card>

      <Card className="panel-card" title="策略观察组">
        {loading && !tracking ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : strategyRows.length ? (
          <PaperForwardStrategyTable rows={strategyRows} loading={loading} />
        ) : (
          <Empty description="暂无可展示的策略观察组。" />
        )}
      </Card>

      <PaperReturnCharts accountCurves={accountCurves} strategyFilter={strategyFilter} />

      <div className="shortpick-strategy-lab-chart-grid">
        {charts.length ? charts.map((chart) => <PaperDisplayChartCard key={chart.title || chart.kind} chart={chart} />) : (
          <Card className="panel-card" title="交易统计图表">
            <Empty description="首笔前向成交后显示交易动作、持仓和退出统计。" />
          </Card>
        )}
      </div>

      <Card className="panel-card" title={table?.title || "模拟交易明细"}>
        {tableRows.length ? (
          <Space direction="vertical" size="middle" className="full-width">
            <div className="shortpick-strategy-lab-filter-bar">
              <Input.Search
                className="shortpick-strategy-lab-filter-search"
                allowClear
                placeholder="搜索日期、标的、动作、原因"
                value={tableSearch}
                onChange={(event) => setTableSearch(event.target.value)}
              />
              <Select
                allowClear
                className="shortpick-strategy-lab-filter-select"
                options={strategyOptions}
                placeholder="策略"
                value={strategyFilter || undefined}
                onChange={(value) => setStrategyFilter(value ?? "")}
              />
              <Select
                allowClear
                className="shortpick-strategy-lab-filter-select"
                options={actionOptions}
                placeholder="动作"
                value={actionFilter || undefined}
                onChange={(value) => setActionFilter(value ?? "")}
              />
              <Select
                allowClear
                className="shortpick-strategy-lab-filter-select"
                options={exitOptions}
                placeholder="退出状态"
                value={exitFilter || undefined}
                onChange={(value) => setExitFilter(value ?? "")}
              />
              <Button
                onClick={() => {
                  setTableSearch("");
                  setStrategyFilter("");
                  setActionFilter("");
                  setExitFilter("");
                }}
              >
                重置
              </Button>
              <Text type="secondary">显示 {filteredTableRows.length} / {tableRows.length} 条</Text>
            </div>
            <Table
              rowKey={(_item, index) => `paper-display-row-${index ?? 0}`}
              size="small"
              columns={tableColumns}
              dataSource={filteredTableRows}
              pagination={{ pageSize: 20 }}
            />
          </Space>
        ) : (
          <Empty description={table?.empty_text || "暂无可展示的纸面追踪记录。"} />
        )}
      </Card>
    </div>
  );
}

function PaperReturnCharts({
  accountCurves,
  strategyFilter,
}: {
  accountCurves: ShortpickStrategyLabPaperDisplayAccountCurve[];
  strategyFilter: string;
}) {
  const cumulativeChartRef = useRef<HTMLDivElement | null>(null);
  const strategyChartRef = useRef<HTMLDivElement | null>(null);
  const visibleCurves = useMemo(() => accountCurves
    .filter((curve) => !strategyFilter || curve.strategy === strategyFilter)
    .filter((curve) => (curve.points ?? []).length > 0), [accountCurves, strategyFilter]);
  const chartDates = useMemo(() => Array.from(new Set(
    visibleCurves.flatMap((curve) => (curve.points ?? []).map((point) => point.date)),
  )).sort((left, right) => left.localeCompare(right)), [visibleCurves]);
  const drawdownRows = useMemo(() => visibleCurves
    .map((curve) => ({
      strategy: curve.strategy,
      maxDrawdown: typeof curve.max_drawdown === "number" ? curve.max_drawdown : 0,
      latestReturn: typeof curve.latest_return === "number" ? curve.latest_return : 0,
      completedTradeCount: typeof curve.completed_trade_count === "number" ? curve.completed_trade_count : 0,
    }))
    .sort((left, right) => right.maxDrawdown - left.maxDrawdown), [visibleCurves]);
  const latestReturn = visibleCurves.length
    ? Math.max(...visibleCurves.map((curve) => typeof curve.latest_return === "number" ? curve.latest_return : 0))
    : 0;
  const latestDrawdown = visibleCurves.length
    ? Math.min(...visibleCurves.map((curve) => typeof curve.max_drawdown === "number" ? curve.max_drawdown : 0))
    : 0;

  useEffect(() => {
    const container = cumulativeChartRef.current;
    if (!container || !visibleCurves.length || !chartDates.length) return undefined;
    const chart = init(container, undefined, { renderer: "canvas" });
    chart.setOption({
      grid: { top: 28, right: 16, bottom: 38, left: 56 },
      legend: { top: 0, right: 8, type: "scroll" },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: number) => formatPercent(value),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: chartDates,
        axisLabel: { hideOverlap: true },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: (value: number) => formatPercent(value) },
      },
      series: visibleCurves.map((curve) => {
        const pointByDate = new Map((curve.points ?? []).map((point) => [point.date, point.account_return]));
        return {
          name: curve.strategy,
          type: "line",
          smooth: true,
          showSymbol: false,
          data: chartDates.map((day) => pointByDate.get(day) ?? null),
          lineStyle: { width: 2 },
          areaStyle: { opacity: visibleCurves.length === 1 ? 0.08 : 0 },
        };
      }),
    });
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [chartDates, visibleCurves]);

  useEffect(() => {
    const container = strategyChartRef.current;
    if (!container || !drawdownRows.length) return undefined;
    const chart = init(container, undefined, { renderer: "canvas" });
    chart.setOption({
      grid: { top: 28, right: 18, bottom: 38, left: 120 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        valueFormatter: (value: number) => formatPercent(value),
      },
      xAxis: {
        type: "value",
        axisLabel: { formatter: (value: number) => formatPercent(value) },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: drawdownRows.map((item) => item.strategy),
        axisLabel: { width: 104, overflow: "truncate" },
      },
      series: [{
        name: "账户最大回撤",
        type: "bar",
        data: drawdownRows.map((item) => item.maxDrawdown),
        itemStyle: { borderRadius: [0, 4, 4, 0] },
      }],
    });
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [drawdownRows]);

  if (!visibleCurves.length) {
    return (
      <div className="shortpick-paper-effect-panel">
        <div className="shortpick-paper-effect-head">
          <Space direction="vertical" size={2}>
            <Text strong>账户净值走势</Text>
            <Text type="secondary">从 20 万本金开始，产生真实前向成交后显示折线和回撤。</Text>
          </Space>
          <Space wrap className="shortpick-paper-effect-summary-tags">
            <Tag color="blue">初始本金 200,000 元</Tag>
            <Tag color="green">纸面收益待生成</Tag>
            <Tag color="red">回撤待生成</Tag>
          </Space>
        </div>
        <div className="shortpick-strategy-lab-return-chart-grid">
          <div className="shortpick-paper-effect-chart-block">
            <div className="shortpick-paper-effect-chart-head">
              <Space direction="vertical" size={0} className="shortpick-paper-effect-chart-title">
                <Text strong>账户累计收益</Text>
                <Text type="secondary">第一笔买入成交后开始绘制。</Text>
              </Space>
            </div>
            <div className="shortpick-paper-effect-chart shortpick-paper-effect-chart-placeholder">
              <Empty description="等待前向成交数据。" />
            </div>
          </div>
          <div className="shortpick-paper-effect-chart-block">
            <div className="shortpick-paper-effect-chart-head">
              <Space direction="vertical" size={0} className="shortpick-paper-effect-chart-title">
                <Text strong>账户最大回撤对比</Text>
                <Text type="secondary">账户净值产生波动后开始统计。</Text>
              </Space>
            </div>
            <div className="shortpick-paper-effect-chart shortpick-paper-effect-chart-placeholder">
              <Empty description="等待回撤数据。" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="shortpick-paper-effect-panel">
      <div className="shortpick-paper-effect-head">
        <Space direction="vertical" size={2}>
          <Text strong>账户净值走势</Text>
          <Text type="secondary">按 20 万纸面账户、实际买入成本和持仓市值计算；产生真实成交后显示。</Text>
        </Space>
        <Space wrap className="shortpick-paper-effect-summary-tags">
          <Tag color="blue">策略 {formatNumber(visibleCurves.length)}</Tag>
          <Tag color="green">最好最新收益 {formatPercent(latestReturn)}</Tag>
          <Tag color="red">最大回撤 {formatPercent(latestDrawdown)}</Tag>
        </Space>
      </div>
      <div className="shortpick-strategy-lab-return-chart-grid">
        <div className="shortpick-paper-effect-chart-block">
          <div className="shortpick-paper-effect-chart-head">
            <Space direction="vertical" size={0} className="shortpick-paper-effect-chart-title">
              <Text strong>账户累计收益</Text>
              <Text type="secondary">按交易日滚动展示，不按单笔收益复利。</Text>
            </Space>
          </div>
          <div ref={cumulativeChartRef} className="shortpick-paper-effect-chart" />
        </div>
        <div className="shortpick-paper-effect-chart-block">
          <div className="shortpick-paper-effect-chart-head">
            <Space direction="vertical" size={0} className="shortpick-paper-effect-chart-title">
              <Text strong>账户最大回撤对比</Text>
              <Text type="secondary">按账户净值相对高点的最大跌幅统计。</Text>
            </Space>
          </div>
          <div ref={strategyChartRef} className="shortpick-paper-effect-chart" />
        </div>
      </div>
    </div>
  );
}

function PaperDisplayChartCard({ chart }: { chart: ShortpickStrategyLabPaperDisplayChart }) {
  const points = chart.data ?? [];
  const maxValue = Math.max(...points.map((item) => item.value), 0);
  return (
    <Card className="panel-card" title={chart.title || "图表"}>
      <Space direction="vertical" size="middle" className="full-width">
        {chart.subtitle ? <Text type="secondary">{chart.subtitle}</Text> : null}
        {points.length ? points.map((item) => (
          <div className="shortpick-strategy-lab-chart-row" key={item.name}>
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
  sourceColumns: ShortpickStrategyLabPaperDisplayTableColumn[],
): ColumnsType<ShortpickStrategyLabPaperDisplayTableRow> {
  const fallbackColumns: ShortpickStrategyLabPaperDisplayTableColumn[] = [
    { key: "signal_date_text", label: "信号日" },
    { key: "tracking_tag", label: "记录类型" },
    { key: "strategy_text", label: "策略" },
    { key: "action_text", label: "动作" },
    { key: "reason_text", label: "原因" },
    { key: "stock_text", label: "标的" },
    { key: "selected_rank_text", label: "入选位置" },
    { key: "quantity_text", label: "数量" },
    { key: "cash_after_text", label: "剩余现金" },
    { key: "exit_state_text", label: "退出状态" },
    { key: "exit_date_text", label: "退出日" },
    { key: "return_text", label: "收益" },
    { key: "note", label: "说明" },
  ];
  return (sourceColumns.length ? sourceColumns : fallbackColumns).map((column) => ({
    title: column.label,
    key: column.key,
    render: (_, item) => paperDisplayTableCell(column.key, item),
  }));
}

function paperDisplayTableCell(key: string, item: ShortpickStrategyLabPaperDisplayTableRow) {
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

function ShortpickStrategyLabReplayTab({
  replay,
  loading,
  onReload,
}: {
  replay: ShortpickStrategyLabHistoricalReplayResponse | null;
  loading: boolean;
  onReload: () => void;
}) {
  const selectedRows = replay?.selected_configs ?? [];
  const baselineRows = replay?.baseline_configs ?? [];
  const holdoutRows = replay?.holdout_configs ?? [];
  const rejectedRows = replay?.rejected_configs ?? [];
  return (
    <div className="panel-stack shortpick-strategy-lab-tab-body">
      <Card
        className="panel-card"
        title="历史回放核心读数"
        extra={<Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>刷新</Button>}
      >
        {loading && !replay ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          <>
            <div className="metric-strip shortpick-strategy-lab-metrics">
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

      {replay?.metric_groups?.length ? (
        <div className="shortpick-strategy-lab-chart-grid">
          {replay.metric_groups.map((group) => (
            <Card className="panel-card" title={group.title} key={group.title}>
              <div className="metric-strip shortpick-strategy-lab-metrics">
                {group.items.map((item) => (
                  <div className="metric-strip-item" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{metricDisplayValue(item)}</strong>
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </div>
      ) : null}

      <Card className="panel-card" title={selectedRows.length ? "推广配置与基线" : "合格配置与基线"}>
        <ConfigSummaryTable rows={[...selectedRows, ...baselineRows]} loading={loading} />
      </Card>

      <Card className="panel-card" title="留出与未采用配置统计">
        <ConfigSummaryTable rows={[...holdoutRows, ...rejectedRows]} loading={loading} />
      </Card>
    </div>
  );
}

export function ShortpickStrategyLabView() {
  const [activeTab, setActiveTab] = useState<ShortpickStrategyLabTab>(() => initialShortpickStrategyLabTab());
  const activeTabRef = useRef<ShortpickStrategyLabTab>(activeTab);
  const [paperTracking, setPaperTracking] = useState<ShortpickStrategyLabPaperTrackingResponse | null>(null);
  const [historicalReplay, setHistoricalReplay] = useState<ShortpickStrategyLabHistoricalReplayResponse | null>(null);
  const [paperLoading, setPaperLoading] = useState(false);
  const [replayLoading, setReplayLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPaperTracking(): Promise<void> {
    setPaperLoading(true);
    setError(null);
    try {
      const result = await api.getShortpickStrategyLabPaperTracking();
      setPaperTracking(result.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载 模型纸面追踪失败。");
    } finally {
      setPaperLoading(false);
    }
  }

  async function loadHistoricalReplay(): Promise<void> {
    setReplayLoading(true);
    setError(null);
    try {
      const result = await api.getShortpickStrategyLabHistoricalReplay();
      setHistoricalReplay(result.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载 v3 历史回放失败。");
    } finally {
      setReplayLoading(false);
    }
  }

  function loadActiveTab(tab: ShortpickStrategyLabTab): void {
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
      const nextTab = initialShortpickStrategyLabTab();
      if (activeTabRef.current === nextTab) return;
      activeTabRef.current = nextTab;
      setActiveTab(nextTab);
      loadActiveTab(nextTab);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    writeWorkbenchRoute({ view: "shortpick-strategy-lab", shortpickStrategyLabTab: activeTab }, "replace");
  }, [activeTab]);

  return (
    <section className="shortpick-strategy-lab panel-stack">
      <Card className="panel-card shortpick-strategy-lab-header">
        <div className="shortpick-header-main">
          <Space direction="vertical" size={4}>
            <Title level={3}>v3 模型策略</Title>
            <Text type="secondary">20 万资金池滚动纸面追踪与静态历史验证</Text>
          </Space>
          <Space wrap className="inline-tags">
            <Tag color="green">研究观察，不构成建议</Tag>
            <Tag color="blue">20万资金约束</Tag>
            <Tag color="purple">100股手数</Tag>
            <Tag color="red">不延迟买入</Tag>
          </Space>
        </div>
      </Card>

      {error ? <Alert type="error" showIcon message={error} /> : null}

      <Tabs
        className="shortpick-strategy-lab-tabs"
        activeKey={activeTab}
        onChange={(key) => {
          if (!SHORTPICK_STRATEGY_LAB_TABS.has(key as ShortpickStrategyLabTab)) return;
          const nextTab = key as ShortpickStrategyLabTab;
          activeTabRef.current = nextTab;
          writeWorkbenchRoute({ view: "shortpick-strategy-lab", shortpickStrategyLabTab: nextTab }, "push");
          setActiveTab(nextTab);
          loadActiveTab(nextTab);
        }}
        items={[
          {
            key: "paper-tracking",
            label: "纸面追踪",
            children: (
              <ShortpickStrategyLabPaperTab
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
              <ShortpickStrategyLabReplayTab
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
