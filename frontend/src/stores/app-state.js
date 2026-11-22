export const state={token:localStorage.getItem('manhole_token'),user:null,data:null,page:'atlas',notice:'',error:'',busy:false};
export function saveSession(result){state.token=result.access_token;state.user=result.user;localStorage.setItem('manhole_token',state.token);}
export function clearSession(){state.token=null;state.user=null;state.data=null;localStorage.removeItem('manhole_token');}
