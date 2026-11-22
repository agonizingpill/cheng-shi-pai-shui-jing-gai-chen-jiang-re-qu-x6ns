const getToken=()=>localStorage.getItem('manhole_token');
export async function api(path, options={}) {
  const headers={'Content-Type':'application/json', ...(getToken()?{Authorization:`Bearer ${getToken()}`}:{})};
  const response=await fetch(`/api${path}`, {...options, headers:{...headers,...(options.headers||{})}});
  const body=await response.json().catch(()=>({}));
  if(!response.ok){const message=typeof body.detail==='object'?body.detail.message:body.detail||'请求失败'; const error=new Error(message); error.body=body.detail; error.status=response.status; throw error;}
  return body;
}
export const auth=async(username,password)=>api('/auth/login',{method:'POST',body:JSON.stringify({username,password})});
export const loadDashboard=()=>api('/dashboard');
export const correctDatum=id=>api(`/survey-points/${id}/correct-datum`,{method:'POST'});
export const cluster=id=>api(`/survey-batches/${id}/cluster`,{method:'POST'});
export const job=id=>api(`/analysis-jobs/${id}`);
export const splitZone=id=>api(`/zones/${id}/split`,{method:'POST'});
export const createNotice=(id,payload)=>api(`/zones/${id}/work-notices`,{method:'POST',body:JSON.stringify(payload)});
export const acknowledgeNotice=id=>api(`/work-notices/${id}/acknowledge`,{method:'POST'});
export const startRepair=id=>api(`/zones/${id}/start-repair`,{method:'POST'});
export const submitResurvey=(id,payload)=>api(`/zones/${id}/resurvey`,{method:'POST',body:JSON.stringify(payload)});
export const verifyResurvey=id=>api(`/resurveys/${id}/verify`,{method:'POST'});
