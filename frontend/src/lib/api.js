const getToken = () => localStorage.getItem("api_token") || "";

export async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
  });
  if (res.status === 401) {
    localStorage.removeItem("api_token");
    throw new Error("unauthorized");
  }
  return res.json();
}

export const downloadUrl = (id) =>
  `/api/evidence/${id}/download${getToken() ? `?token=${encodeURIComponent(getToken())}` : ""}`;

export const exportUrl = (since) =>
  `/api/export?${since ? `since=${since}&` : ""}${getToken() ? `token=${encodeURIComponent(getToken())}` : ""}`;

export { getToken };
