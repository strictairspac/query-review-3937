import{DELIVERY_STATUSES}from'../../constants/enums.js';import{esc}from'../../utils/html.js';export const deliveryBadge=s=>'<span class="badge '+esc(s)+'">'+esc(DELIVERY_STATUSES[s]||s)+'</span>';
