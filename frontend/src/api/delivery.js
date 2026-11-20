import{api,post}from'./client.js';
export const listDeliveries=()=>api('/deliveries');
export const getDelivery=id=>api('/deliveries/'+id);
export const batchDelivery=id=>api('/batches/'+id+'/delivery');
export const sendBatch=(id,period)=>post('/batches/'+id+'/delivery',period?{period}:{});
