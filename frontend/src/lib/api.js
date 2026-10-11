import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const uploadPdf = (file, onProgress, pairWith) => {
  const fd = new FormData();
  fd.append("file", file);
  return axios
    .post(`${API}/jobs`, fd, {
      params: pairWith ? { pair_with: pairWith } : {},
      onUploadProgress: (e) => onProgress?.(e.total ? e.loaded / e.total : 0),
    })
    .then((r) => r.data);
};
export const getJob = (id) => axios.get(`${API}/jobs/${id}`).then((r) => r.data);
export const listJobs = () => axios.get(`${API}/jobs`).then((r) => r.data);
export const deleteJob = (id) => axios.delete(`${API}/jobs/${id}`);
export const retryJob = (id) => axios.post(`${API}/jobs/${id}/retry`);
export const updateMeta = (id, meta) => axios.patch(`${API}/jobs/${id}/meta`, meta).then((r) => r.data);
export const updateQuestion = (id, qid, body) => axios.put(`${API}/jobs/${id}/questions/${qid}`, body).then((r) => r.data);
export const mergeNext = (id, qid) => axios.post(`${API}/jobs/${id}/questions/${qid}/merge-next`).then((r) => r.data);
export const deleteQuestion = (id, qid) => axios.delete(`${API}/jobs/${id}/questions/${qid}`).then((r) => r.data);
export const imageUrl = (jobId, qid) => `${API}/jobs/${jobId}/images/${qid}`;
export const pageUrl = (jobId, page) => `${API}/jobs/${jobId}/pages/${page}`;
export const zipUrl = (jobId) => `${API}/jobs/${jobId}/zip`;
