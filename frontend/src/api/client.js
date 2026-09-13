const API_BASE = "http://localhost:8000";

export async function fetchPrograms() {
  const res = await fetch(`${API_BASE}/programs`);
  if (!res.ok) throw new Error("Failed to fetch programs");
  const data = await res.json();
  return data.programs;
}

export async function fetchTargets(programId) {
  const res = await fetch(`${API_BASE}/targets?program_id=${programId}`);
  if (!res.ok) throw new Error("Failed to fetch targets");
  const data = await res.json();
  return data.targets;
}

export async function fetchCrashes(targetId) {
  const res = await fetch(
    `${API_BASE}/crashes?visibility=private&target_id=${targetId}`
  );
  if (!res.ok) throw new Error("Failed to fetch crashes");
  const data = await res.json();
  return data.crashes;
}

export async function fetchCrashDetail(id) {
  const res = await fetch(`${API_BASE}/crashes/${id}?visibility=private`);
  if (!res.ok) throw new Error("Failed to fetch crash detail");
  return res.json();
}
