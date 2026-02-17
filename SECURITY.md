# Security Report

## Dependency Vulnerability Scan

Last updated: 2026-02-17

### Scanning Tool
- **Tool**: pip-audit >= 2.6.0
- **Command**: `pip-audit --desc`

### Current Vulnerabilities

#### 1. DiskCache CVE-2025-69872 (Transitive dependency from ChromaDB)
- **Package**: diskcache 5.6.3
- **Severity**: Medium
- **Fix Available**: No
- **Description**: Uses Python pickle for serialization. Exploitable only if attacker has write access to cache directory.
- **Risk Assessment**: **LOW** - Requires filesystem write access to `/data/chromadb/` which should be protected by OS permissions
- **Mitigation**: Ensure cache directory has proper filesystem permissions (owner-only write)
- **Status**: Monitoring for upstream fix

### Resolved Vulnerabilities

#### setuptools PYSEC-2025-49 (Fixed 2025-02-13)
- **Package**: setuptools 77.0.3 → 82.0.0
- **Vulnerability**: Path traversal in PackageIndex
- **Fix**: Upgraded to setuptools >= 78.1.1

## Static Analysis (Bandit)

### Scanning Tool
- **Tool**: bandit >= 1.9.3
- **Command**: `bandit -r src/ -ll -ii`

### Accepted Risks

#### 1. B104: Hardcoded bind to all interfaces (src/config.py:33)
- **Severity**: Medium
- **Confidence**: Medium
- **Description**: API server binds to 0.0.0.0 for Docker/network accessibility
- **Risk Assessment**: **ACCEPTED** - Required for containerized deployment. Production deployments should use proper firewall rules and reverse proxy configuration
- **Mitigation**: Deploy behind reverse proxy (nginx/traefik), configure firewall rules, use TLS

#### 2. B615: Hugging Face downloads without revision pinning (src/translator.py)
- **Severity**: Medium
- **Confidence**: High
- **Locations**: Lines 119, 120, 127, 128
- **Description**: Translation models downloaded without pinning specific revision commits
- **Risk Assessment**: **ACCEPTED** - Using well-known Helsinki-NLP Marian models. Benefits of auto-updates outweigh risks
- **Mitigation**: Models cached locally after first download, regular security audits
- **Models Used**:
  - `Helsinki-NLP/opus-mt-bg-en` (Bulgarian → English)
  - `Helsinki-NLP/opus-mt-en-bg` (English → Bulgarian)

## Continuous Monitoring

Add to CI/CD pipeline:

```bash
pip-audit --desc --strict
```

This will fail builds if high/critical vulnerabilities are detected.

## Reporting Security Issues

If you discover a security vulnerability, please email security@viapharma.us instead of using the issue tracker.
