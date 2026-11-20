/** @typedef {{id:number,name:string,description:string,original_sql:string}} Sample */
/** @typedef {{id:number,name:string,sample_id:number,candidate_sql:string,status:string,review_sequence:number}} Batch */
/** @typedef {{id:number,batch_id:number,result:Object}} Evidence */
/** @typedef {{id:number,batch_id:number,period:string|null,version:number,status:string,row_count:number,total_amount:string}} Delivery */
export const entityNames={sample:'SQL 样本',batch:'复核批次',evidence:'执行证据',delivery:'送账任务'};
