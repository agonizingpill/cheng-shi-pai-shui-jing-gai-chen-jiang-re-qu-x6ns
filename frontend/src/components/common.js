export const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
export const fmt=value=>value?new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
export const pill=(value, kind='neutral')=>`<span class="pill ${kind}">${esc(value)}</span>`;
export const empty=(title,copy)=>`<div class="empty"><div class="empty-mark">＋</div><strong>${esc(title)}</strong><p>${esc(copy)}</p></div>`;
export function toast(state){return state.notice?`<div class="toast good">${esc(state.notice)}</div>`:state.error?`<div class="toast bad">${esc(state.error)}</div>`:'';}
