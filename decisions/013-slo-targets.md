# 013: Service Level Objective targets and alerting strategy

Stage: S5 · Date: 2026-11-22 · Author: dally · Drafted by agent: yes

## Choice

Define three SLOs for the ride app: (1) `/predict` availability >= 99.5% non-5xx responses with a 14.4x multi-window burn rate alert (1h and 5m), (2) `/predict` latency >= 95% of requests served under 250ms, and (3) model serving quality >= 95% of quotes served by the ML model rather than the static median fallback.

## Rejected alternative

A strict 99.9% availability target and p95 <= 150ms latency objective with instantaneous single-window alerting on any 5xx error.

## Why

Setting availability at 99.9% provides only 43 minutes of downtime per month. In an architecture where model containers perform atomic in-memory reloading and Traefik handles blue-green traffic cutovers across micro-instances (t4g.large), transient network blips and occasional cold model loads would burn through a 99.9% error budget immediately. A 99.5% target provides an error budget of ~3.6 hours/month, sufficient for routine deployments and retrains while maintaining an excellent rider experience. Multi-window burn rate alerts (14.4x over 1h and 5m) prevent alert fatigue by ignoring transient blips while rapidly paging on true outages that consume >2% of the monthly error budget in an hour.

## What would show this was wrong

If rider abandonment rates increase due to quote latency exceeding 250ms while the SLO remains green, or if repeated production incidents go unnoticed because the 14.4x burn rate threshold requires too long to trigger during lower-traffic periods.
