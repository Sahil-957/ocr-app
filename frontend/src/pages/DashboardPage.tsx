import { useMemo, useState } from "react";

import { Batch, Row } from "../types";

type Props = {
  batch: Batch | null;
  rows: Row[];
  onCreateBatch: (name: string) => Promise<void>;
  onUploadFolder: (files: FileList | null) => Promise<void>;
  onStartBatch: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onApproveRow: (row: Row, reviewedData: Record<string, unknown>) => Promise<void>;
  onExport: () => Promise<void>;
  uploadMessage: string;
  busy: boolean;
};

export function DashboardPage({
  batch,
  rows,
  onCreateBatch,
  onUploadFolder,
  onStartBatch,
  onRefresh,
  onApproveRow,
  onExport,
  uploadMessage,
  busy
}: Props) {
  const [batchName, setBatchName] = useState("March Costing Batch");
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? null;
  const editableData = useMemo(() => ({ ...(selectedRow?.reviewed_data ?? selectedRow?.data ?? {}) }), [selectedRow]);
  const [draftData, setDraftData] = useState<Record<string, unknown>>(editableData);

  const stats = {
    pendingReview: rows.filter((row) => row.status === "needs_review").length,
    completed: rows.filter((row) => row.status === "processed" || row.status === "approved").length
  };

  return (
    <div className="dashboard-grid">
      <section className="panel stack">
        <div className="panel-title">
          <h3>1. Create Batch</h3>
          <p>Start a company batch before uploading the folder.</p>
        </div>
        <div className="inline-form">
          <input value={batchName} onChange={(event) => setBatchName(event.target.value)} placeholder="Batch name" />
          <button onClick={() => onCreateBatch(batchName)}>Create Batch</button>
        </div>
        {batch ? <div className="badge-row">Active batch: <strong>{batch.name}</strong> #{batch.id}</div> : null}
      </section>

      <section className="panel stack">
        <div className="panel-title">
          <h3>2. Upload Folder</h3>
          <p>Choose a folder with same-layout screenshots.</p>
        </div>
        <input
          type="file"
          multiple
          webkitdirectory=""
          onChange={(event) => void onUploadFolder(event.target.files)}
          disabled={!batch}
        />
        {uploadMessage ? <div className="badge-row">{uploadMessage}</div> : null}
        <button onClick={() => void onStartBatch()} disabled={!batch || batch.total_files === 0 || busy}>
          {busy ? "Working..." : "Start Extraction"}
        </button>
      </section>

      <section className="panel stats-panel">
        <div className="stat-tile">
          <span>Status</span>
          <strong>{batch?.status ?? "No batch"}</strong>
        </div>
        <div className="stat-tile">
          <span>Files</span>
          <strong>{batch ? `${batch.processed_files}/${batch.total_files}` : "0/0"}</strong>
        </div>
        <div className="stat-tile">
          <span>Review</span>
          <strong>{stats.pendingReview}</strong>
        </div>
        <div className="stat-tile">
          <span>Failed</span>
          <strong>{batch?.failed_count ?? 0}</strong>
        </div>
        <div className="stats-actions">
          <button className="ghost-button" onClick={() => void onRefresh()} disabled={!batch || busy}>
            Refresh
          </button>
          <button onClick={() => void onExport()} disabled={!batch || stats.pendingReview > 0 || rows.length === 0 || busy}>
            Export Excel
          </button>
        </div>
      </section>

      <section className="panel rows-panel">
        <div className="panel-title">
          <h3>Review Queue</h3>
          <p>Rows below confidence threshold should be checked before export.</p>
        </div>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>Confidence</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} onClick={() => { setSelectedRowId(row.id); setDraftData({ ...(row.reviewed_data ?? row.data) }); }}>
                  <td>{row.source_file_name}</td>
                  <td>{row.status}</td>
                  <td>{row.confidence_summary.toFixed(2)}</td>
                  <td>{row.validation_issues.join(", ") || "None"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel detail-panel">
        <div className="panel-title">
          <h3>Selected Row</h3>
          <p>Correct flagged values and approve them for export.</p>
        </div>
        {selectedRow ? (
          <>
            <div className="field-grid">
              {Object.entries(draftData).slice(0, 18).map(([key, value]) => (
                <label key={key}>
                  {key}
                  <input
                    value={value == null ? "" : String(value)}
                    onChange={(event) => setDraftData((current) => ({ ...current, [key]: event.target.value }))}
                  />
                </label>
              ))}
            </div>
            <button onClick={() => void onApproveRow(selectedRow, draftData)}>Approve Row</button>
          </>
        ) : (
          <div className="empty-state">Select a row to inspect OCR output and corrections.</div>
        )}
      </section>
    </div>
  );
}
