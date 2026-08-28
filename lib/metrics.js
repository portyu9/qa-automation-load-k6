import { Rate, Trend } from 'k6/metrics';

export const businessFailures = new Rate('business_failures');
export const businessDuration = new Trend('business_duration', true);
