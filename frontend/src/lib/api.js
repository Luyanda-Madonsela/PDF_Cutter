import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const data = (r) => r.data;

export const createSet = ({ qp, memo, addenda, errata }, onProgress) => {
  const fd = new FormData();
  fd.append("question_paper", qp);
  fd.append("memo", memo);
  addenda.forEach((f) => fd.append("addenda", f));
  errata.forEach((f) => fd.append("errata", f));
  return axios.post(`${API}/sets`, fd, { onUploadProgress: (e) => onProgress?.(e.total ? e.loaded / e.total : 0) }).then(data);
};
export const uploadDoc = (file, { setId, docType } = {}) => {
  const fd = new FormData();
  fd.append("file", file);
  const params = {};
  if (setId) params.set_id = setId;
  if (docType) params.doc_type = docType;
  return axios.post(`${API}/jobs`, fd, { params }).then(data);
};
export const listSets = () => axios.get(`${API}/sets`).then(data);
export const getSet = (id) => axios.get(`${API}/sets/${id}`).then(data);
export const updateSetMeta = (id, meta) => axios.patch(`${API}/sets/${id}/meta`, meta).then(data);
export const deleteSet = (id) => axios.delete(`${API}/sets/${id}`);
export const setZipUrl = (id) => `${API}/sets/${id}/zip`;

export const retryJob = (id) => axios.post(`${API}/jobs/${id}/retry`);
export const deleteJob = (id) => axios.delete(`${API}/jobs/${id}`);
export const updateQuestion = (id, qid, body) => axios.put(`${API}/jobs/${id}/questions/${qid}`, body).then(data);
export const reviewQuestion = (id, qid) => axios.post(`${API}/jobs/${id}/questions/${qid}/review`).then(data);
export const mergeNext = (id, qid) => axios.post(`${API}/jobs/${id}/questions/${qid}/merge-next`).then(data);
export const deleteQuestion = (id, qid) => axios.delete(`${API}/jobs/${id}/questions/${qid}`).then(data);
export const imageUrl = (jobId, qid) => `${API}/jobs/${jobId}/images/${qid}`;
export const pageUrl = (jobId, page) => `${API}/jobs/${jobId}/pages/${page}`;

export const DOC_LABEL = { question_paper: "Question paper", memo: "Memo", addendum: "Addendum", errata: "Errata" };
export const ACTIVE_DOC = ["queued", "classifying", "waiting", "ready", "processing"];
export const listCatalogues = () => axios.get(`${API}/catalogues`).then(data);
export const catalogueUrl = (key) => `${API}/catalogues/${key}/download`;
export const getErase = (id, qid) => axios.get(`${API}/jobs/${id}/questions/${qid}/erase`).then(data);
export const decideErase = (id, qid, boxes) => axios.post(`${API}/jobs/${id}/questions/${qid}/erase`, { boxes }).then(data);
export const approveAllErases = (setId) => axios.post(`${API}/sets/${setId}/erase-approve-all`).then(data);
