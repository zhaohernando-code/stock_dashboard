import { Alert, Button, Card, Skeleton, Space, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { Phase5WorkbenchProjectionManifest } from "../types";

const { Text } = Typography;

interface WorkbenchProjectionPanelProps {
  projection: Phase5WorkbenchProjectionManifest | null;
  loading: boolean;
  error: string | null;
  isMobile?: boolean;
  onRefresh: () => void | Promise<void>;
}

export function WorkbenchProjectionPanel({
  projection,
  loading,
  error,
  isMobile = false,
  onRefresh,
}: WorkbenchProjectionPanelProps) {
  const content = (
    <>
      <div className="workbench-projection-head">
        <div>
          <Text type="secondary">自动化平台</Text>
          <h3>运行工作台</h3>
        </div>
        <Space wrap>
          <Tag color={statusColorFor(projection?.projection_status)}>{statusLabel(projection?.projection_status)}</Tag>
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => void onRefresh()}>
            刷新
          </Button>
        </Space>
      </div>

      {error ? (
        <Alert type="warning" showIcon message="运行工作台状态加载失败" description={error} />
      ) : null}

      {loading && !projection ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : (
        <div className="workbench-projection-grid">
          <Metric label="Cycle" value={projection?.cycle.cycle_id ?? "--"} subValue={projection?.cycle.cycle_status ?? "未发现"} />
          <Metric label="Auto Progress" value={String(projection?.auto_progress.total_runs ?? 0)} subValue={projection?.auto_progress.latest_phase ?? "暂无运行"} />
          <Metric label="Recovery" value={projection?.recovery.latest_ticket_id ?? "--"} subValue={projection?.recovery.final_status ?? "无恢复票"} />
          <Metric label="Next" value={projection?.recommended_next_action ?? "--"} subValue={projection?.auto_progress.latest_apply_status ?? "等待状态"} />
        </div>
      )}

      {projection?.blocking_reasons.length ? (
        <Alert
          type="error"
          showIcon
          message="需要处理的阻塞"
          description={projection.blocking_reasons.join("；")}
        />
      ) : projection?.missing_refs.length ? (
        <Alert
          type="warning"
          showIcon
          message="状态输入不完整"
          description={projection.missing_refs.join("；")}
        />
      ) : null}
    </>
  );

  if (isMobile) {
    return <section className="mobile-panel-card workbench-projection-card">{content}</section>;
  }
  return <Card className="panel-card workbench-projection-card">{content}</Card>;
}

function Metric({ label, value, subValue }: { label: string; value: string; subValue: string }) {
  return (
    <div className="workbench-projection-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{subValue}</em>
    </div>
  );
}

function statusLabel(status?: string | null): string {
  if (status === "current") return "正常";
  if (status === "degraded") return "降级";
  if (status === "blocked") return "阻塞";
  return "未加载";
}

function statusColorFor(status?: string | null): string {
  if (status === "current") return "green";
  if (status === "degraded") return "gold";
  if (status === "blocked") return "red";
  return "default";
}
