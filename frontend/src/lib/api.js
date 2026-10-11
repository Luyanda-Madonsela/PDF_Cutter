import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const uploadPdf = (file, onProgress) => {
  const fd = new FormData();
  fd.append("file", file);
  return axios
    .post(`${API}/jobs`, fd, { onUploadProgress: (e) => onProgress?.(e.total ? e.loaded / e.total : 0) })
    .then((r) => r.data);
};
export const getJob = (id) => axios.get(`${API}/jobs/${id}`).then((r) => r.data);
export const listJobs = () => axios.get(`${API}/jobs`).then((r) => r.data);
export const deleteJob = (id) => axios.delete(`${API}/jobs/${id}`);
export const imageUrl = (jobId, filename) => `${API}/jobs/${jobId}/images/${encodeURIComponent(filename)}`;
export const zipUrl = (jobId) => `${API}/jobs/${jobId}/zip`;
