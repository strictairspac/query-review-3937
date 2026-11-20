import{sendBatch,batchDelivery}from'../api/delivery.js';import{session}from'../stores/session.js';import{notify}from'./feedback.js';import{deliveryBadge}from'../components/common/deliveryBadge.js';import{esc}from'../utils/html.js';
/** Renders the send control and current delivery state for a passed batch. */
export function sendControl(batchId,{eligible,reason,delivery,period}={}){
  if(session.get().role==='viewer')return delivery?deliveryBadge(delivery.status):'<span class="muted">观察员只读</span>';
  if(delivery&&['active','superseded','pending'].includes(delivery.status))return deliveryBadge(delivery.status);
  if(!eligible)return '<span class="muted" title="'+esc(reason||'')+'">不可送账</span>';
  return '<span class="sendwrap"><input class="period mono" data-batch="'+batchId+'" maxlength="40" placeholder="账期（可选）" value="'+esc(period||'')+'" aria-label="账期（可选）"><button type="button" class="send" data-batch="'+batchId+'">送入账务库 →</button></span>';
}
/** Delegated click handler; call once per page render. */
export function bindSend(el){
  el.addEventListener('click',async event=>{
    const button=event.target.closest('button.send');if(!button)return;
    event.preventDefault();button.disabled=true;
    const ident=Number(button.dataset.batch);const input=el.querySelector('input.period[data-batch="'+ident+'"]');
    const period=input&&input.value.trim();
    try{const result=await sendBatch(ident,period||null);notify('批次 #'+result.batch_id+' 已加入待送队列，账务库断开时恢复后自动续送');button.outerHTML=deliveryBadge(result.status)}
    catch(err){notify(err.message);button.disabled=false}
  });
}
export async function sendMeta(batchId){
  try{return await batchDelivery(batchId)}catch{return {eligible:false,reason:'状态读取失败'}}
}
