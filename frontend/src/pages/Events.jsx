import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import Topbar from "../components/Topbar";
import Input from "../components/Input";
import Select from "../components/Select";
import Table from "../components/Table";
import { RiskBadge } from "../components/Badge";
import LoadingSpinner from "../components/LoadingSpinner";
import { EVENT_TYPES, RISK_LEVELS } from "../utils/constants";
import { formatDate } from "../utils/formatDate";
import { formatAmount } from "../utils/formatRisk";
import { useLive } from "../context/LiveContext";
import Button from "../components/Button";
import toast from "react-hot-toast";

export default function Events() {
  const navigate = useNavigate();
  const { connection } = useLive();
  const [filters, setFilters] = useState({
    search: "",
    event_type: "",
    risk_level: "",
    user_id: "",
    ip: "",
    location: "",
  });
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [csvFile, setCsvFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const params = Object.fromEntries(
        Object.entries(filters).filter(([, v]) => v !== "" && v != null)
      );
      const res = await api.events({ ...params, page_size: 50 });
      setData(res.data);
    } catch {
      toast.error("Failed to load events");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [filters]);

  const columns = [
    { key: "event_id", label: "Event", render: (r) => <span className="font-mono text-xs">{r.event_id}</span> },
    { key: "event_type", label: "Type" },
    { key: "user_id", label: "User" },
    { key: "ip_address", label: "IP" },
    { key: "location", label: "Location" },
    { key: "amount", label: "Amount", render: (r) => formatAmount(r.amount) },
    {
      key: "risk",
      label: "Risk",
      render: (r) => (
        <div className="flex items-center gap-2">
          <span className="font-semibold">{r.risk_score}</span>
          <RiskBadge level={r.risk_level} />
        </div>
      ),
    },
    {
      key: "is_anomaly",
      label: "Detection",
      render: (r) => (
        <span className={r.is_anomaly ? "font-semibold text-danger" : "text-muted"}>
          {r.is_anomaly ? "Anomaly" : "Normal"}
        </span>
      ),
    },
    { key: "timestamp", label: "Time", render: (r) => formatDate(r.timestamp) },
  ];

  const uploadCsv = async (event) => {
    event.preventDefault();
    if (!csvFile || importing) return;
    const form = event.currentTarget;
    setImporting(true);
    setImportError("");
    setImportResult(null);
    try {
      const response = await api.importCsv(csvFile);
      setImportResult(response.data);
      setCsvFile(null);
      form.reset();
      await load();
      toast.success(`Analyzed ${response.data.analyzed_rows} transaction rows`);
    } catch (error) {
      const detail = error.response?.data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : !error.response
            ? "Could not reach the backend. Check that the API server is running, then retry the upload."
            : `CSV import failed (HTTP ${error.response.status}). Please retry or contact support.`;
      setImportError(message);
      toast.error(message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div>
      <Topbar
        title="Event Timeline"
        subtitle={`${data.total} events · filter, search, and inspect`}
        connection={connection}
      />
      <div className="p-4 md:p-6 space-y-4">
        <form onSubmit={uploadCsv} className="rounded-xl border border-border bg-card p-4 space-y-3">
          <div>
            <h2 className="font-semibold text-text">Import transactions from CSV</h2>
            <p className="mt-1 text-sm text-muted">
              Upload a Risk Radar transaction CSV or PaySim data. Rows are analyzed by the existing model; any
              dataset fraud labels are stored separately from predictions.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <Input
              label="CSV file (maximum 10 MB and 50,000 rows)"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setCsvFile(event.target.files?.[0] || null)}
              className="flex-1"
            />
            <Button type="submit" disabled={!csvFile || importing} variant="accent">
              {importing ? "Analyzing…" : "Upload and analyze"}
            </Button>
          </div>
          {importError ? <p className="text-sm text-danger" role="alert">{importError}</p> : null}
          {importResult ? (
            <div className="rounded-lg border border-border bg-primary p-3 text-sm text-text" role="status">
              <p className="font-medium">
                Import complete: {importResult.analyzed_rows} valid rows analyzed, {importResult.invalid_rows} invalid rows,{" "}
                {importResult.detected_anomalies} model-detected anomalies of {importResult.total_rows} total rows.
              </p>
              {importResult.invalid_rows > 0 && importResult.rejections.length ? (
                <ul className="mt-2 space-y-1 text-muted">
                  {importResult.rejections.slice(0, 5).map((rejection) => (
                    <li key={`${rejection.row}-${rejection.reason}`}>Row {rejection.row}: {rejection.reason}</li>
                  ))}
                </ul>
              ) : null}
              {importResult.invalid_rows > importResult.rejections.length ? (
                <p className="mt-1 text-muted">
                  Showing {Math.min(5, importResult.rejections.length)} of {importResult.invalid_rows} invalid rows.
                </p>
              ) : null}
              {importResult.rejections_truncated > 0 ? (
                <p className="mt-1 text-muted">{importResult.rejections_truncated} additional row errors omitted.</p>
              ) : null}
            </div>
          ) : null}
        </form>
        <div className="grid md:grid-cols-3 xl:grid-cols-6 gap-3 rounded-xl border border-border bg-card p-4">
          <Input
            label="Search"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            placeholder="Event, user, IP…"
          />
          <Select
            label="Event type"
            value={filters.event_type}
            onChange={(e) => setFilters((f) => ({ ...f, event_type: e.target.value }))}
            options={[{ value: "", label: "All types" }, ...EVENT_TYPES.map((t) => ({ value: t, label: t }))]}
          />
          <Select
            label="Risk level"
            value={filters.risk_level}
            onChange={(e) => setFilters((f) => ({ ...f, risk_level: e.target.value }))}
            options={[{ value: "", label: "All levels" }, ...RISK_LEVELS.map((t) => ({ value: t, label: t }))]}
          />
          <Input
            label="User ID"
            value={filters.user_id}
            onChange={(e) => setFilters((f) => ({ ...f, user_id: e.target.value }))}
          />
          <Input
            label="IP"
            value={filters.ip}
            onChange={(e) => setFilters((f) => ({ ...f, ip: e.target.value }))}
          />
          <Input
            label="Location"
            value={filters.location}
            onChange={(e) => setFilters((f) => ({ ...f, location: e.target.value }))}
          />
        </div>
        {loading ? (
          <LoadingSpinner />
        ) : (
          <Table columns={columns} rows={data.items} onRowClick={(r) => navigate(`/app/events/${r.id}`)} />
        )}
      </div>
    </div>
  );
}
