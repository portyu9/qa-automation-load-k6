import { Counter, Rate, Trend } from 'k6/metrics';

export const businessAttempts = new Counter('business_attempts');
export const businessSuccess = new Rate('business_success');
export const businessFailures = new Rate('business_failures');
export const businessDuration = new Trend('business_duration', true);
