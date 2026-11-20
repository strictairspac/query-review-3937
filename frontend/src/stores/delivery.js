import{listDeliveries}from'../api/delivery.js';export const deliveries={items:[],async load(){this.items=await listDeliveries();return this.items}};
