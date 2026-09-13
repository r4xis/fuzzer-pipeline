export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export async function fetchPrograms() {
  const data = await getJson("/programs");
  return data.programs;
}

export async function fetchTargets(programId) {
  const data = await getJson(`/targets?program_id=${programId}`);
  return data.targets;
}

export async function fetchProgramTree() {
  const programs = await fetchPrograms();
  const targetLists = await Promise.all(programs.map((p) => fetchTargets(p.id)));
  return programs.map((program, i) => ({ program, targets: targetLists[i] }));
}

export async function fetchCrashes(targetId, { status } = {}) {
  const params = new URLSearchParams({ visibility: "private", target_id: targetId });
  if (status) params.set("status", status);
  const data = await getJson(`/crashes?${params}`);
  return data.crashes;
}

export async function fetchCrashDetail(id) {
  return getJson(`/crashes/${id}?visibility=private`);
}

export async function fetchSessionHistory(sessionId) {
  const data = await getJson(`/sessions/${sessionId}/history`);
  return data.history;
}

export async function fetchSessionInstances(sessionId) {
  const data = await getJson(`/sessions/${sessionId}/instances`);
  return data.instances;
}

export function downloadUrl(id) {
  return `${API_BASE}/crashes/${id}/download`;
}
