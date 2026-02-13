# Security Report

## Dependency Vulnerability Scan

Last updated: 2025-02-13

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

## Continuous Monitoring

Add to CI/CD pipeline:

```bash
pip-audit --desc --strict
```

This will fail builds if high/critical vulnerabilities are detected.

## Reporting Security Issues

If you discover a security vulnerability, please email security@viapharma.us instead of using the issue tracker.
