import axios from "axios";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
});

api.interceptors.response.use(undefined, (e) => {
  const d = e?.response?.data?.detail;
  if (e?.response?.status === 403 && d?.code === "PASSWORD_CHANGE_REQUIRED" && window.location.pathname !== "/change-password") {
    window.location.assign("/change-password");
  }
  return Promise.reject(e);
});

export const errText = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x && typeof x.msg === "string" ? x.msg : JSON.stringify(x))).join(" ");
  if (d && typeof d.msg === "string") return d.msg;
  return e?.message || "Something went wrong";
};

export default api;
