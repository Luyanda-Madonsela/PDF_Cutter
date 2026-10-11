import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const data = (r) => r.data;
axios.defaults.withCredentials = true;

export const getMe = () => axios.get(`${API}/auth/me`).then(data);
export const exchangeSession = (session_id) => axios.post(`${API}/auth/session`, { session_id }).then(data);
export const logout = () => axios.post(`${API}/auth/logout`);

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
export const stopJob = (id) => axios.post(`${API}/jobs/${id}/stop`);
export const deleteJob = (id) => axios.delete(`${API}/jobs/${id}`);
export const updateQuestion = (id, qid, body) => axios.put(`${API}/jobs/${id}/questions/${qid}`, body).then(data);
export const reviewQuestion = (id, qid) => axios.post(`${API}/jobs/${id}/questions/${qid}/review`).then(data);
export const mergeNext = (id, qid) => axios.post(`${API}/jobs/${id}/questions/${qid}/merge-next`).then(data);
export const deleteQuestion = (id, qid) => axios.delete(`${API}/jobs/${id}/questions/${qid}`).then(data);
export const imageUrl = (jobId, qid) => `${API}/jobs/${jobId}/images/${qid}`;
export const pageUrl = (jobId, page) => `${API}/jobs/${jobId}/pages/${page}`;

export const rateDifficulty = (setId) => axios.post(`${API}/sets/${setId}/rate-difficulty`).then(data);
export const rateAllStatus = () => axios.get(`${API}/sets/rate-difficulty-all`).then(data);
export const rateAll = () => axios.post(`${API}/sets/rate-difficulty-all`).then(data);
export const DIFFICULTY = { Easy: ["Easy/Beginner", "text-emerald-300 border-emerald-400/50"], Medium: ["Medium", "text-amber-300 border-amber-400/50"], Hard: ["Hard", "text-red-300 border-red-400/50"] };
export const DOC_LABEL = { question_paper: "Question paper", memo: "Memo", addendum: "Addendum", errata: "Errata" };
export const ACTIVE_DOC = ["queued", "classifying", "waiting", "ready", "processing"];
export const listCatalogues = () => axios.get(`${API}/catalogues`).then(data);
export const refreshTopics = () => axios.post(`${API}/catalogues/refresh-topics`).then(data);
export const driveStatus = () => axios.get(`${API}/drive/status`).then(data);
export const driveConnect = () => axios.get(`${API}/drive/connect`).then(data);
export const driveDisconnect = () => axios.post(`${API}/drive/disconnect`).then(data);
export const sendToDrive = (setId) => axios.post(`${API}/drive/sets/${setId}/send`).then(data);
export const saveDriveSettings = (root_link, root_path) => axios.put(`${API}/drive/settings`, { root_link, root_path }).then(data);
export const driveSearch = (q, page_token) => axios.get(`${API}/drive/search`, { params: { q, page_token } }).then(data);
export const driveImport = (file_ids) => axios.post(`${API}/drive/import`, { file_ids }).then(data);
export const driveScan = (limit) => axios.post(`${API}/drive/scan`, { limit }).then(data);
export const driveImportStatus = () => axios.get(`${API}/drive/import-status`).then(data);
export const recropPreview = () => axios.get(`${API}/sets/recrop-preview`).then(data);
export const recropAll = () => axios.post(`${API}/sets/recrop-all`).then(data);
export const getAiSettings = () => axios.get(`${API}/ai/settings`).then(data);
export const saveAiSettings = (body) => axios.put(`${API}/ai/settings`, body).then(data);
export const getAiUsage = (days) => axios.get(`${API}/ai/usage`, { params: { days } }).then(data);
export const setAiPrice = (model, input, output) => axios.put(`${API}/ai/prices`, { model, input, output }).then(data);
export const getBudget = () => axios.get(`${API}/ai/budget`).then(data);
export const setBudget = (monthly_limit) => axios.put(`${API}/ai/budget`, { monthly_limit }).then(data);
export const skeletonOptions = () => axios.get(`${API}/drive/skeleton/options`).then(data);
export const buildSkeleton = (qualifications, year_from, year_to) => axios.post(`${API}/drive/skeleton`, { qualifications, year_from, year_to }).then(data);
export const testAi = () => axios.post(`${API}/ai/test`).then(data);
export const undoCrop = (id, qid) => axios.post(`${API}/jobs/${id}/questions/${qid}/undo-crop`).then(data);
export const recropSet = (id) => axios.post(`${API}/sets/${id}/recrop`).then(data);
export const catalogueUrl = (key) => `${API}/catalogues/${key}/download`;
export const getErase = (id, qid) => axios.get(`${API}/jobs/${id}/questions/${qid}/erase`).then(data);
export const decideErase = (id, qid, boxes, manual = []) => axios.post(`${API}/jobs/${id}/questions/${qid}/erase`, { boxes, manual }).then(data);
export const approveAllErases = (setId) => axios.post(`${API}/sets/${setId}/erase-approve-all`).then(data);
