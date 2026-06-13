import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
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

function stringArrayField(source: Record<string, unknown> | undefined, key: string): string[] {
  const value = source?.[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function configRoleLabel(role?: string | null): string {
  if (role === "phase5_contract_candidate") return "候选配置";
  if (role === "baseline_control") return "基线";
  if (role === "holdout") return "留出观察";
  if (role === "rejected") return "未采用";
  return role || "未标注";
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
  return action || "未记录";
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
  if (artifactId) return artifactId.length > 24 ? `${artifactId.slice(0, 12)}…${artifactId.slice(-8)}` : artifactId;
  const path = stringField(source, "path");
  return path.split("/").pop() || "--";
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
          <Text strong>{item.config_id}</Text>
          <Space wrap size={4}>
            <Tag color={configRoleColor(item.role)}>{configRoleLabel(item.role)}</Tag>
            <Tag color={statusColor(item.gate_status)}>{item.gate_status || "未过闸"}</Tag>
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
      render: (value?: string | null) => <Text>{value || "--"}</Text>,
    },
  ];
  return (
    <Table
      className="shortpick-v2-config-table"
      rowKey={(item) => `${item.role}:${item.config_id}`}
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
  const summary = tracking?.summary ?? {};
  const selectedRows = tracking?.selected_configs ?? [];
  const baselineRows = tracking?.baseline_configs ?? [];
  const records = tracking?.records ?? [];
  const allowedActions = stringArrayField(tracking?.row_contract, "allowed_signal_actions");
  const forbiddenActions = stringArrayField(tracking?.row_contract, "forbidden_signal_actions");
  const recordColumns: ColumnsType<Record<string, unknown>> = [
    {
      title: "信号 / 配置",
      key: "signal",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{String(item.signal_date ?? "--")}</Text>
          <Text type="secondary">{String(item.config_id ?? "--")}</Text>
        </Space>
      ),
    },
    {
      title: "动作",
      key: "action",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Tag color={actionColor(String(item.decision_action ?? ""))}>
            {actionLabel(String(item.decision_action ?? ""))}
          </Tag>
          <Text type="secondary">{String(item.reason ?? "--")}</Text>
        </Space>
      ),
    },
    {
      title: "标的 / 数量",
      key: "symbol",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{String(item.symbol ?? "--")}</Text>
          <Text type="secondary">数量 {formatNumber(typeof item.quantity === "number" ? item.quantity : null)}</Text>
        </Space>
      ),
    },
    {
      title: "资金",
      key: "cash",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>前 {formatNumber(typeof item.cash_before === "number" ? item.cash_before : null)}</Text>
          <Text type="secondary">后 {formatNumber(typeof item.cash_after === "number" ? item.cash_after : null)}</Text>
        </Space>
      ),
    },
  ];
  return (
    <div className="panel-stack shortpick-v2-tab-body">
      <Card
        className="panel-card"
        title="纸面追踪状态"
        extra={<Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>刷新</Button>}
      >
        {loading && !tracking ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          <>
            <Alert
              showIcon
              type={
                tracking?.status === "blocked"
                  ? "warning"
                  : tracking?.status === "contract_ready" ? "info" : "success"
              }
              message={tracking?.current_status || "等待 v2 纸面追踪"}
              description={tracking?.current_message || tracking?.data_disclaimer || "暂无 v2 paper ledger rows。"}
            />
            <div className="metric-strip shortpick-v2-metrics">
              <div className="metric-strip-item">
                <span>起始窗口</span>
                <strong>{String(tracking?.tracking_window?.start_date ?? "2026-05-08")}</strong>
              </div>
              <div className="metric-strip-item">
                <span>记录数</span>
                <strong>{formatNumber(numberField(summary, "record_count"))}</strong>
              </div>
              <div className="metric-strip-item">
                <span>买入 / 跳过</span>
                <strong>
                  {formatNumber(numberField(summary, "buy_count"))}
                  {" / "}
                  {formatNumber(numberField(summary, "skip_count"))}
                </strong>
              </div>
              <div className="metric-strip-item">
                <span>证据上限</span>
                <strong>{tracking?.claim_ceiling || "research_observation"}</strong>
              </div>
            </div>
            <Space wrap className="inline-tags">
              {allowedActions.map((action) => (
                <Tag key={action} color={actionColor(action)}>{actionLabel(action)}</Tag>
              ))}
              {forbiddenActions.includes("delay_buy") ? <Tag color="red">不允许延迟买入</Tag> : null}
              <Tag color="green">{tracking?.evidence_basis || "true_forward_tracking"}</Tag>
            </Space>
          </>
        )}
      </Card>

      <Card className="panel-card" title={selectedRows.length ? "已固化配置" : "合格配置与基线"}>
        <ConfigSummaryTable rows={[...selectedRows, ...baselineRows]} loading={loading} />
      </Card>

      <Card className="panel-card" title="v2 Paper Ledger Rows">
        {records.length ? (
          <Table
            rowKey={(item) => String(item.record_id ?? `${item.signal_date}:${item.config_id}`)}
            size="small"
            columns={recordColumns}
            dataSource={records}
            pagination={{ pageSize: 20 }}
          />
        ) : (
          <Empty
            description={
              tracking?.status === "blocked"
                ? "blocked：暂无通过大盘超额和 30% 年化门槛的 v2 候选配置。"
                : "contract_ready：已固定配置，暂无真实前向 v2 纸面行。"
            }
          />
        )}
      </Card>
    </div>
  );
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
      render: (_, item) => <Text>{String(item.config_id ?? "--")}</Text>,
    },
    {
      title: "动作 / 原因",
      key: "action",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Tag color={actionColor(String(item.action ?? ""))}>{actionLabel(String(item.action ?? ""))}</Tag>
          <Text type="secondary">{String(item.reason ?? "--")}</Text>
        </Space>
      ),
    },
    {
      title: "标的 / 排名",
      key: "symbol",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{String(item.symbol ?? "--")}</Text>
          <Text type="secondary">rank {String(item.selected_rank ?? "--")}</Text>
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
                <strong>{String(replay?.summary?.coverage_status ?? "--")}</strong>
              </div>
            </div>
            <Space wrap className="inline-tags">
              <Tag color={statusColor(replay?.status)}>{replay?.status || "blocked"}</Tag>
              <Tag color="green">{replay?.claim_ceiling || "research_observation"}</Tag>
              <Tag color="blue">{replay?.evidence_basis || "historical_account_replay_selection"}</Tag>
              <Tag>生成 {formatDate(replay?.generated_at)}</Tag>
              <Tag>replay {artifactShortRef(replay?.source_artifacts?.replay)}</Tag>
            </Space>
            <Paragraph type="secondary" className="panel-description">
              {replay?.data_disclaimer || "历史回放读取固定 artifact，不构成投资建议。"}
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
                rowKey={(item, index) => `${item.config_id}:${item.signal_date}:${index}`}
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
            <Tag color="green">research_observation</Tag>
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
          description="页面只读取 v2 backend read APIs；不触发回放生成、行情刷新、模型调用、纸面行写入或参数搜索。"
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
