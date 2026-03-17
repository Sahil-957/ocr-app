import { useEffect, useState } from "react";

import { api, downloadFile } from "./api/client";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { Batch, Row, User } from "./types";


export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [uploadMessage, setUploadMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("access_token")) return;
    void api<User>("/auth/me")
      .then(setUser)
      .catch(() => localStorage.removeItem("access_token"));
  }, []);

  async function handleLogin(username: string, password: string) {
    const token = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    });
    localStorage.setItem("access_token", token.access_token);
    setUser(await api<User>("/auth/me"));
  }

  async function createBatch(name: string) {
    setBusy(true);
    const created = await api<Batch>("/batches", {
      method: "POST",
      body: JSON.stringify({ name })
    });
    setBatch(created);
    setRows([]);
    setUploadMessage("Batch created. Select a folder to upload images.");
    setBusy(false);
  }

  async function uploadFolder(files: FileList | null) {
    if (!batch) {
      setUploadMessage("Create a batch before uploading files.");
      return;
    }
    if (!files?.length) {
      setUploadMessage("No files were selected.");
      return;
    }

    setBusy(true);
    setUploadMessage(`Uploading ${files.length} file(s)...`);
    try {
      const chunkSize = 30;
      const fileArray = Array.from(files).filter((file) => /\.(png|jpg|jpeg|bmp)$/i.test(file.name));
      for (let index = 0; index < fileArray.length; index += chunkSize) {
        const formData = new FormData();
        fileArray.slice(index, index + chunkSize).forEach((file) => formData.append("files", file, file.name));
        const updated = await api<Batch>(`/batches/${batch.id}/files`, {
          method: "POST",
          body: formData
        });
        setBatch(updated);
        setUploadMessage(`Uploaded ${Math.min(index + chunkSize, fileArray.length)} of ${fileArray.length} file(s).`);
      }
      await refreshBatch(batch.id);
      setUploadMessage(`Upload complete. ${fileArray.length} file(s) are ready for extraction.`);
    } catch (error) {
      setUploadMessage(error instanceof Error ? `Upload failed: ${error.message}` : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function startBatch() {
    if (!batch) return;
    setBusy(true);
    const started = await api<Batch>(`/batches/${batch.id}/start`, { method: "POST" });
    setBatch(started);
    setUploadMessage("Extraction started. Refresh in a few seconds to see progress.");
    setBusy(false);
    setTimeout(() => void refreshBatch(started.id), 3000);
  }

  async function refreshBatch(batchId = batch?.id) {
    if (!batchId) return;
    const latestBatch = await api<Batch>(`/batches/${batchId}`);
    setBatch(latestBatch);
    setRows(await api<Row[]>(`/batches/${batchId}/rows`));
  }

  async function approveRow(row: Row, reviewedData: Record<string, unknown>) {
    const updated = await api<Row>(`/batches/rows/${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ reviewed_data: reviewedData, status: "approved" })
    });
    setRows((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  async function exportBatch() {
    if (!batch) return;
    const exportJob = await api<{ download_url: string | null }>("/batches/" + batch.id + "/export", {
      method: "POST"
    });
    if (exportJob.download_url) {
      await downloadFile(exportJob.download_url, `batch-${batch.id}.xlsx`);
    }
  }

  function logout() {
    localStorage.removeItem("access_token");
    setUser(null);
    setBatch(null);
    setRows([]);
  }

  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <Layout
      title="Operations Workspace"
      subtitle="Upload screenshot folders, monitor extraction jobs, review low-confidence rows, and export Excel."
      onLogout={logout}
    >
      <DashboardPage
        batch={batch}
        rows={rows}
        onCreateBatch={createBatch}
        onUploadFolder={uploadFolder}
        onStartBatch={startBatch}
        onRefresh={refreshBatch}
        onApproveRow={approveRow}
        onExport={exportBatch}
        uploadMessage={uploadMessage}
        busy={busy}
      />
    </Layout>
  );
}
