# Security checklist

The catalog the security pass works through systematically. Every category gets considered; categories the change cannot touch are noted as not applicable, not silently skipped. Findings carry the attack scenario as impact — who reaches the path, with what input, gaining what.

## Injection

- User input reaching queries, commands, or rendered output without parameterization or sanitization: SQL/NoSQL (string-built queries), OS command, LDAP, XSS (unsanitized template or DOM output).
- Dynamic code evaluation on user-influenced input; unsafe reflection.

## Authentication and sessions

- Weak password handling, missing lockout, session fixation, predictable or long-lived tokens.
- Missing authentication on new endpoints or routes; token expiration, revocation, and scope validation defects.
- Race conditions in auth flows; missing CSRF protection on state-changing operations.

## Sensitive-data exposure

- Passwords, tokens, PII, or financial data logged, stored in plaintext, sent unencrypted, exposed in URLs, or returned in responses and error messages.

## Access control

- Authorization checks missing or bypassable via parameter manipulation; insecure direct object references; missing ownership validation; privilege-escalation paths.

## Misconfiguration

- Overly permissive settings, default credentials, unnecessary features enabled, debug modes reachable in production.

## Deserialization and parsing

- Untrusted data deserialized without schema validation or constraints — object deserialization, and JSON/YAML/XML parsing with dangerous features enabled (external entities, arbitrary-type loading).

## Secrets in source

- Anything secret-shaped in the diff: API keys, passwords, tokens, connection strings, private keys, webhook URLs. Test-looking values are findings too.

## Input boundaries

- Every entry point for external data validated at the boundary: request bodies, query parameters, headers, file uploads (type, size, content), third-party responses, user-supplied URLs, paths, and regular expressions (ReDoS), environment and configuration inputs.

## Error paths and leakage

- Errors, logs, or stack traces exposing internal paths, schema or query structure, service topology, component versions, or sensitive variable values.

## Storage and transport

- Sensitive data encrypted at rest where required; TLS in transit; current primitives and key sizes — no MD5 or SHA-1 in security contexts, no ECB mode; keys managed, not inlined.

## Headers and browser policy

- Where web-facing surfaces change: CORS not wildcard-with-credentials; CSP present and restrictive; `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security` set; cookies `Secure`, `HttpOnly`, `SameSite` as appropriate.

## Dependencies

- Added or updated dependencies checked for known CVEs and advisories; unmaintained or typosquatting-adjacent packages flagged.
