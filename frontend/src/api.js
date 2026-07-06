const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `Request failed: ${response.status}`);
  }
  return response.json();
}

export function fetchPatients() {
  return request("/patients/");
}

export function fetchPatient(id) {
  return request(`/patients/${id}/`);
}

export function triggerMigration(limit = 20) {
  return request(`/migrate/?limit=${limit}`, { method: "POST" });
}

export function fetchMigrationStatus() {
  return request("/migrate/status/");
}

// When the backend runs Celery with a real broker, POST /migrate/ returns 202
// with a "running" run; poll the status endpoint until it resolves.
export async function waitForRun(runId, { intervalMs = 2000, timeoutMs = 300000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const runs = await fetchMigrationStatus();
    const run = runs.find((r) => r.id === runId);
    if (run && run.status !== "running") {
      return run;
    }
    if (Date.now() > deadline) {
      throw new Error("Timed out waiting for migration to finish.");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
