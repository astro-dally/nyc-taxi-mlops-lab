# 003: Ingress scope

Stage: S0 · Date: 2026-11-21 · Author: (you) · Drafted by agent: yes

## Choice

Port 80 on the app host is restricted to a **named list of CIDRs** (`var.ingress_cidrs` in
`terraform.tfvars`): your own public IP and the grader's IP, each as a `/32`. This is the narrowest
practical scope: exactly the humans who need access, nothing else.

## Rejected alternative

Open port 80 to the world (`0.0.0.0/0`). This is the simplest option and the default for most
tutorials: it removes the operational step of updating `terraform.tfvars` when your IP changes, and
it matches what a real public-facing service would do.

## Why

| Dimension | Named /32s | 0.0.0.0/0 |
|---|---|---|
| Attack surface | Only your machines and the grader's reach port 80 | Any scanner, bot, or attacker on the internet |
| S0 requirement | Passes the grader's check (grader IP in the list) | Also passes, but over-permissive |
| Operational cost | Must update `terraform.tfvars` + re-apply if your IP changes | Zero friction |
| Principle of least privilege | ✅ | ❌ |

The app has no authentication in S0, so an open port is equivalent to a public endpoint serving
trip-duration quotes for free. That's low-risk for the data, but it invites abuse (crawler traffic,
denial-of-service) and fails the security review. The named-CIDR approach costs one `terraform apply`
when the IP changes, which is acceptable for a lab that resets every 4 hours anyway.

## What would show this was wrong

If the grader's IP is behind a NAT that rotates frequently, or if the lab requires the app to be
reachable from arbitrary IPs (e.g. a load-testing harness), the named-CIDR approach becomes
operationally painful. If we were adding authentication (S6 adds the assistant), opening to 0.0.0.0/0
at that point would be revisitable.
